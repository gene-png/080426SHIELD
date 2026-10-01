import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as attackClient from "@/lib/attack/client";
import type {
  AttackAssessment,
  AttackCatalog,
  AttackHeatmap,
} from "@/lib/attack/types";

import type * as React from "react";

import { AttackWorkspace } from "./AttackWorkspace";

/**
 * #550: a Run AI whose answer the proxy never saw is not a failed run. The api
 * may have finished and written the rows, and "failed" invites the retry that
 * sends the client's data out again. The page says the outcome is unknown,
 * says where to check, and keeps Run AI off for the rest of its life.
 */

vi.mock("@/lib/attack/client", () => ({
  AttackProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchHeatmap: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  patchCoverage: vi.fn(),
  confirmCoverageCitations: vi.fn(),
  runAttackAi: vi.fn(),
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
vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: (props: {
    onProceed: () => void;
    children: (p: { onClick: () => void }) => React.ReactNode;
  }) => props.children({ onClick: props.onProceed }),
}));
vi.mock("@/components/admin/AiPreviewButton", () => ({
  AiPreviewButton: () => null,
}));

/** What `lib/attack/client.ts` throws: its error class, with the envelope on
 *  `.payload` (the class here is the module mock's). */
function proxyRefusal(status: number, reason: string, message: string): Error {
  const ProxyError = attackClient.AttackProxyError as unknown as new (
    m: string,
  ) => Error;
  return Object.assign(new ProxyError(`ATT&CK proxy ${status}`), {
    status,
    payload: { error: { code: status, reason, message } },
  });
}

const OUTCOME_UNKNOWN = proxyRefusal(
  504,
  "upstream_outcome_unknown",
  "We couldn't confirm whether this finished. It may still complete; check before trying again.",
);

const COPY =
  "We couldn't confirm whether the AI run finished. It may still complete and fill in technique rows. Reload the page later and check step 2, Review every technique and adjust, before running it again. Run AI stays off on this page until you reload.";

function draft(): AttackAssessment {
  return {
    id: "assess-1",
    status: "draft",
    version: 1,
    coverage: [],
    documents_stale: false,
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

async function runAiRejectingWith(err: Error): Promise<HTMLElement> {
  vi.mocked(attackClient.runAttackAi).mockRejectedValueOnce(err);
  render(<AttackWorkspace serviceId="svc-550" serviceTitle="ATT&CK" />);
  const button = await screen.findByRole("button", { name: "Run AI" });
  expect(button).toBeEnabled();
  fireEvent.click(button);
  return button;
}

describe("AttackWorkspace, a Run AI whose outcome is unknown (#550)", () => {
  it("says where to check rather than that the run failed, and keeps Run AI off", async () => {
    await runAiRejectingWith(OUTCOME_UNKNOWN);

    expect(await screen.findByText(COPY)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run AI" })).toBeDisabled();
    expect(screen.queryByText(/failed/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText("That didn't go through"),
    ).not.toBeInTheDocument();
  });

  it("names a step the page renders, by its number and its title", async () => {
    // The copy sends the reader to a step. Read the number and title out of
    // the alert the page rendered, and require the page to render that step's
    // heading, so renaming or renumbering the step turns this red.
    await runAiRejectingWith(OUTCOME_UNKNOWN);
    const alert = await screen.findByText(COPY);
    const named = /check step (\d+), ([^,]+), before/.exec(
      alert.textContent ?? "",
    );
    expect(named, "the copy names no step").not.toBeNull();
    const [, number, title] = named as RegExpExecArray;
    expect(
      screen.getByRole("heading", { name: `Step ${number}: ${title}` }),
    ).toBeInTheDocument();
  });

  it("leaves Run AI on after a refusal the api DID send", async () => {
    // The control: only the unknown outcome locks the button.
    await runAiRejectingWith(
      proxyRefusal(409, "assessment_not_draft", "Not a draft."),
    );

    expect(await screen.findByText("Not a draft.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run AI" })).toBeEnabled();
    expect(screen.queryByText(COPY)).not.toBeInTheDocument();
  });
});
