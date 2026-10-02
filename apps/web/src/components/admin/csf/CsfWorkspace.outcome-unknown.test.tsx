import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type {
  CsfAssessment,
  CsfCatalog,
  CsfRunAiResponse,
  CsfScoreSummary,
  EnterpriseProfile,
  GapAnalysis,
} from "@/lib/csf/types";

import type * as React from "react";

import { CsfWorkspace } from "./CsfWorkspace";

/**
 * #550 on the CSF page: a Run AI whose answer the proxy never saw is not a
 * failed run. The page says the outcome is unknown, names where to check, and
 * keeps Run AI off for the rest of the page's life.
 *
 * Through the WORKSPACE, with the real `CsfPlaybookPanel`, because the lock's
 * lifetime is the workspace's: the panel is mounted only while an assessment
 * exists, so a lock held in the panel was cleared by Discard then Start
 * assessment (review of #752, finding 2).
 */

vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class CsfProxyError extends Error {},
  fetchCatalog: vi.fn(),
  fetchInterviewQuestionnaire: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  fetchScore: vi.fn(),
  fetchGapAnalysis: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  discardAssessment: vi.fn(),
  patchAnswer: vi.fn(),
  fetchEnterpriseProfile: vi.fn(),
  seedProfiles: vi.fn(),
  runCsfAi: vi.fn(),
  // #645: the page reads the service's runs on load and polls one it
  // follows. No run, by default.
  fetchCsfRun: vi.fn(),
  fetchCsfRunSummary: vi.fn(() =>
    Promise.resolve({ running: null, latest: null, last_completed: null }),
  ),
  exportPlaybook: vi.fn(),
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: "ready", stages: null }),
}));
vi.mock("./CsfScoreCard", () => ({ CsfScoreCard: () => null }));
vi.mock("./CsfGapList", () => ({ CsfGapList: () => null }));
vi.mock("./CsfDeliverableCard", () => ({ CsfDeliverableCard: () => null }));
vi.mock("./CsfQuestionnaire", () => ({ CsfQuestionnaire: () => null }));
vi.mock("./CsfDimensionEditor", () => ({ CsfDimensionEditor: () => null }));
vi.mock("./CsfGapActionEditor", () => ({ CsfGapActionEditor: () => null }));
vi.mock("@/components/admin/AiPreviewButton", () => ({
  AiPreviewButton: () => null,
}));
vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: ({
    onProceed,
    children,
  }: {
    onProceed: () => void;
    children: (props: { onClick: () => void }) => React.ReactNode;
  }) => children({ onClick: onProceed }),
}));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));

/** What `lib/csf/client.ts` throws: its error class, envelope on `.payload`. */
function proxyRefusal(status: number, reason: string, message: string): Error {
  const ProxyError = csfClient.CsfProxyError as unknown as new (
    m: string,
  ) => Error;
  return Object.assign(new ProxyError(`CSF proxy ${status}`), {
    status,
    payload: { error: { code: status, reason, message } },
  });
}

/** The proxy's own sentence: what a re-read that got no answer shows. */
const REREAD_MESSAGE =
  "We couldn't confirm whether this finished. It may still complete; check before trying again.";

const OUTCOME_UNKNOWN = proxyRefusal(
  504,
  "upstream_outcome_unknown",
  REREAD_MESSAGE,
);

const COPY =
  "We couldn't confirm whether the AI run finished. It may still complete and fill in dimension scores. Reload the page later and check the dimension scores in Full Playbook — Working Profiles before running it again. Run AI stays off on this page until you reload.";

const RUN = "Run AI (csf_score)";

const ENTERPRISE = {
  tiers_in_use: ["moderate"],
  subcategories: [
    {
      subcategory_code: "GV.OC-01",
      name: "GV.OC-01 outcome",
      function: "GV",
      tier_levels: { moderate: 2 },
      enterprise_level: 2,
      rollup_rule: 1,
      target_level: 3,
      gap: false,
      priority: null,
    },
  ],
} as EnterpriseProfile;

function draft(): CsfAssessment {
  return {
    id: "assess-550",
    status: "draft",
    version: 1,
    answers: [],
    client_target_tier: 3,
    documents_stale: false,
  } as unknown as CsfAssessment;
}

const RUN_RESULT: CsfRunAiResponse = {
  changed: [],
  rows: [],
  suggestions_received: 0,
  suggestions_applied: 0,
  dropped: [],
};

// jsdom has no <dialog>.showModal()/.close(); DiscardDraftButton opens one.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(): void {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(): void {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});

beforeEach(() => {
  vi.mocked(csfClient.fetchCatalog).mockResolvedValue(
    {} as unknown as CsfCatalog,
  );
  vi.mocked(csfClient.fetchInterviewQuestionnaire).mockResolvedValue(null);
  vi.mocked(csfClient.fetchLatestAssessment).mockReset();
  vi.mocked(csfClient.fetchLatestAssessment).mockResolvedValue(draft());
  vi.mocked(csfClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(csfClient.fetchScore).mockResolvedValue(
    {} as unknown as CsfScoreSummary,
  );
  vi.mocked(csfClient.fetchGapAnalysis).mockResolvedValue(
    {} as unknown as GapAnalysis,
  );
  vi.mocked(csfClient.fetchEnterpriseProfile).mockReset();
  vi.mocked(csfClient.fetchEnterpriseProfile).mockResolvedValue(ENTERPRISE);
  vi.mocked(csfClient.runCsfAi).mockReset();
});

async function mountAndRunRejectingWith(err: Error): Promise<HTMLElement> {
  vi.mocked(csfClient.runCsfAi).mockRejectedValueOnce(err);
  const { container } = render(
    <CsfWorkspace serviceId="svc-550-csf" serviceTitle="Atlas CSF" />,
  );
  const button = await screen.findByRole("button", { name: RUN });
  expect(button).toBeEnabled();
  fireEvent.click(button);
  return container;
}

describe("CsfWorkspace, a Run AI whose outcome is unknown (#550)", () => {
  it("says where to check rather than that the run failed, and keeps Run AI off", async () => {
    await mountAndRunRejectingWith(OUTCOME_UNKNOWN);

    expect(await screen.findByText(COPY)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: RUN })).toBeDisabled();
  });

  it("names a section the panel renders, by its title", async () => {
    // The copy sends the reader to a section. Read its name out of the alert
    // the page rendered and require the page to render that title, so
    // renaming the section turns this red.
    await mountAndRunRejectingWith(OUTCOME_UNKNOWN);
    const alert = await screen.findByText(COPY);
    const named = /check the dimension scores in (.+?) before/.exec(
      alert.textContent ?? "",
    );
    expect(named, "the copy names no section").not.toBeNull();
    const [, section] = named as RegExpExecArray;
    expect(screen.getByText(section, { exact: true })).toBeInTheDocument();
  });

  it("keeps Run AI off after Discard then Start assessment remounts the panel", async () => {
    // Review of #752, finding 2: the panel is mounted only while an
    // assessment exists. Discard (the latest comes back null) unmounts it;
    // Start assessment mounts a fresh one. The lock must survive that.
    vi.mocked(csfClient.fetchLatestAssessment)
      .mockResolvedValueOnce(draft())
      .mockResolvedValue(null);
    vi.mocked(csfClient.discardAssessment).mockResolvedValue({
      ...draft(),
      status: "discarded",
    } as unknown as CsfAssessment);
    vi.mocked(csfClient.createAssessment).mockResolvedValue(draft());
    const container = await mountAndRunRejectingWith(OUTCOME_UNKNOWN);
    await screen.findByText(COPY);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));
    });
    const dialog = container.querySelector("dialog") as HTMLDialogElement;
    await act(async () => {
      fireEvent.click(
        within(dialog).getByRole("button", { name: "Yes, discard" }),
      );
    });
    expect(
      await screen.findByText("No CSF assessment yet"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: RUN })).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Start assessment" }));
    });

    expect(await screen.findByRole("button", { name: RUN })).toBeDisabled();
    expect(screen.getByText(COPY)).toBeInTheDocument();
  });

  it("does not lock Run AI when the RUN succeeded and only the re-read after it got no answer", async () => {
    // Review of #752, finding 1: `runCsfAi` answered; the panel's reload of
    // the enterprise profile after it did not. That is the reload's error.
    // #645: the POST answered with a run, and the run completed.
    vi.mocked(csfClient.runCsfAi).mockResolvedValueOnce({
      run_id: "run-550",
      status: "running",
      serves: "offline",
      deadline_at: "2026-10-01T12:45:00Z",
      lock_until: "2026-10-01T12:50:00Z",
      joined: false,
    });
    vi.mocked(csfClient.fetchCsfRun).mockResolvedValueOnce({
      id: "run-550",
      status: "completed",
      result: RUN_RESULT,
    } as unknown as Awaited<ReturnType<typeof csfClient.fetchCsfRun>>);
    vi.mocked(csfClient.fetchEnterpriseProfile)
      .mockResolvedValueOnce(ENTERPRISE)
      .mockRejectedValueOnce(OUTCOME_UNKNOWN);
    render(
      <CsfWorkspace serviceId="svc-550-csf-r1" serviceTitle="Atlas CSF" />,
    );
    fireEvent.click(await screen.findByRole("button", { name: RUN }));

    expect(await screen.findByText(REREAD_MESSAGE)).toBeInTheDocument();
    expect(screen.queryByText(COPY)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: RUN })).toBeEnabled();
  });

  it("leaves Run AI on after a refusal the api DID send", async () => {
    await mountAndRunRejectingWith(
      proxyRefusal(409, "assessment_not_draft", "Not a draft."),
    );

    expect(await screen.findByText("Not a draft.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: RUN })).toBeEnabled();
    expect(screen.queryByText(COPY)).not.toBeInTheDocument();
  });
});
