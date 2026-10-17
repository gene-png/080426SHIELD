import "@testing-library/jest-dom/vitest";

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as attackClient from "@/lib/attack/client";
import type {
  AttackAssessment,
  AttackCatalog,
  AttackHeatmap,
} from "@/lib/attack/types";

import type * as React from "react";

import { AttackWorkspace } from "./AttackWorkspace";

/**
 * #1377 / #550: a section is a URL segment, so moving between sections
 * remounts the workspace and a component flag is lost. A Run AI whose outcome
 * is unknown must keep Run AI off, and keep saying why, in the SECTIONED
 * workspace after it remounts (until a reload, as the copy says). The whole
 * page is unchanged: its flag is still per mount.
 */

vi.mock("@/lib/attack/client", () => ({
  AttackProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchHeatmap: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  reviewComputedStatuses: vi.fn(),
  patchCoverage: vi.fn(),
  confirmCoverageCitations: vi.fn(),
  runAttackAi: vi.fn(),
  fetchAttackRun: vi.fn(),
  fetchAttackRunSummary: vi.fn(() =>
    Promise.resolve({ running: null, latest: null, last_completed: null }),
  ),
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: "loading", stages: null }),
}));
vi.mock("./AttackDeliverableCard", () => ({
  AttackDeliverableCard: () => null,
}));
vi.mock("./AttackHeatmapCard", () => ({ AttackHeatmapCard: () => null }));
vi.mock("./AttackMatrix", () => ({ AttackMatrix: () => null }));
vi.mock("./AttackTechniquePanel", () => ({
  AttackTechniquePanel: () => null,
}));
vi.mock("./AttackAiInputsPanel", () => ({
  AttackAiInputsPanel: () => null,
}));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));
vi.mock("@/components/admin/AiPreviewButton", () => ({
  AiPreviewButton: () => null,
}));
vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: (props: {
    onProceed: () => void;
    children: (p: {
      onClick: () => void;
      statusUnknown: boolean;
    }) => React.ReactNode;
  }) => props.children({ onClick: props.onProceed, statusUnknown: false }),
}));

/** What `lib/attack/client.ts` throws: its error class, with the envelope on
 *  `.payload` (the class here is the module mock's). */
function unknownOutcome(): Error {
  const ProxyError = attackClient.AttackProxyError as unknown as new (
    m: string,
  ) => Error;
  return Object.assign(new ProxyError("ATT&CK proxy 504"), {
    status: 504,
    payload: {
      error: {
        code: 504,
        reason: "upstream_outcome_unknown",
        message: "We couldn't confirm whether this finished.",
      },
    },
  });
}

// The alert's wording is the existing #550 copy; only its presence is pinned.
const ALERT = /We couldn't confirm whether the AI run finished/;

function draft(): AttackAssessment {
  return {
    id: "assess-1",
    status: "draft",
    version: 1,
    coverage: [],
    documents_stale: false,
    ai_source: {
      state: "none",
      sentence: "No AI suggestions were used in this assessment.",
      live_runs: 0,
      fixture_runs: 0,
    },
    catalog_version: "19.2",
    catalog_current: true,
  } as unknown as AttackAssessment;
}

beforeEach(() => {
  vi.mocked(attackClient.fetchCatalog).mockResolvedValue({
    techniques: [],
    coverage_definitions: [],
    reason_codes: [],
  } as unknown as AttackCatalog);
  vi.mocked(attackClient.fetchHeatmap).mockResolvedValue({
    by_tactic: [],
  } as unknown as AttackHeatmap);
  vi.mocked(attackClient.fetchLatestAssessment).mockResolvedValue(draft());
  vi.mocked(attackClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(attackClient.runAttackAi).mockReset();
});
afterEach(cleanup);

async function runAndLoseTheOutcome(serviceId: string): Promise<void> {
  vi.mocked(attackClient.runAttackAi).mockRejectedValueOnce(unknownOutcome());
  render(
    <AttackWorkspace
      serviceId={serviceId}
      serviceTitle="ATT&CK"
      section="ai-draft"
    />,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Run AI" }));
  expect(await screen.findByText(ALERT)).toBeInTheDocument();
}

describe("an unknown Run AI outcome survives a section change (#1377)", () => {
  it("keeps Run AI off and the alert up after the section remounts", async () => {
    await runAndLoseTheOutcome("svc-1377-lock");
    cleanup(); // the reader moves to another section and back

    render(
      <AttackWorkspace
        serviceId="svc-1377-lock"
        serviceTitle="ATT&CK"
        section="ai-draft"
      />,
    );
    const button = await screen.findByRole("button", { name: "Run AI" });
    await waitFor(() => expect(button).toBeDisabled());
    expect(screen.getByText(ALERT)).toBeInTheDocument();
    expect(attackClient.runAttackAi).toHaveBeenCalledTimes(1);
  });

  it("does not lock another service", async () => {
    await runAndLoseTheOutcome("svc-1377-a");
    cleanup();

    render(
      <AttackWorkspace
        serviceId="svc-1377-b"
        serviceTitle="ATT&CK"
        section="ai-draft"
      />,
    );
    expect(await screen.findByRole("button", { name: "Run AI" })).toBeEnabled();
    expect(screen.queryByText(ALERT)).not.toBeInTheDocument();
  });

  it("the whole page still forgets it on remount, as before", async () => {
    vi.mocked(attackClient.runAttackAi).mockRejectedValueOnce(unknownOutcome());
    render(
      <AttackWorkspace serviceId="svc-1377-whole" serviceTitle="ATT&CK" />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Run AI" }));
    expect(await screen.findByText(ALERT)).toBeInTheDocument();
    cleanup();

    render(
      <AttackWorkspace serviceId="svc-1377-whole" serviceTitle="ATT&CK" />,
    );
    expect(await screen.findByRole("button", { name: "Run AI" })).toBeEnabled();
  });
});
