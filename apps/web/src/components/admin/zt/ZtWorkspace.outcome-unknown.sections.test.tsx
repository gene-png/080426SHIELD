import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as ztClient from "@/lib/zt/client";
import type {
  GapAnalysis,
  ZtAssessment,
  ZtCatalog,
  ZtScoreSummary,
} from "@/lib/zt/types";

import type * as React from "react";

import { ZtWorkspace } from "./ZtWorkspace";

/**
 * #1379: the same unknown-outcome Run AI, in the AI draft section. The whole
 * page names "step 2, Review every capability and adjust"; a section has no
 * steps, so it names the Review section (placeholder copy, pending the
 * advisor's verbatim approval).
 */

vi.mock("@/lib/zt/client", () => ({
  ZtProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  fetchScore: vi.fn(),
  fetchGapAnalysis: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  discardAssessment: vi.fn(),
  patchAnswer: vi.fn(),
  runZtAi: vi.fn(),
  // #645: the page reads the service's runs on load and polls one it
  // follows. No run, by default.
  fetchZtRun: vi.fn(),
  fetchZtRunSummary: vi.fn(() =>
    Promise.resolve({ running: null, latest: null, last_completed: null }),
  ),
  finalizeZtDeliverable: vi.fn(),
  releaseZtDeliverable: vi.fn(),
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: "ready", stages: null }),
}));
vi.mock("./ZtScoreCard", () => ({ ZtScoreCard: () => null }));
vi.mock("./ZtGapList", () => ({ ZtGapList: () => null }));
vi.mock("./ZtRoadmapCard", () => ({ ZtRoadmapCard: () => null }));
vi.mock("./ZtQuestionnaire", () => ({ ZtQuestionnaire: () => null }));
vi.mock("./ZtDeliverableCard", () => ({ ZtDeliverableCard: () => null }));
vi.mock("./ZtRunAiAccounting", () => ({
  ZtRunAiAccounting: () => null,
  lostValueCount: () => 0,
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

/** What `lib/zt/client.ts` throws: its error class, envelope on `.payload`. */
function proxyRefusal(status: number, reason: string, message: string): Error {
  const ProxyError = ztClient.ZtProxyError as unknown as new (
    m: string,
  ) => Error;
  return Object.assign(new ProxyError(`ZT proxy ${status}`), {
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
  "We couldn't confirm whether the AI run finished. It may still complete and fill in capability rows. Reload the page later and check Review before running it again. Run AI stays off on this page until you reload.";

beforeEach(() => {
  vi.mocked(ztClient.fetchCatalog).mockResolvedValue({
    pillars: [],
    stages: [],
  } as unknown as ZtCatalog);
  vi.mocked(ztClient.fetchLatestAssessment).mockResolvedValue({
    id: "zt-assess-1",
    status: "draft",
    version: 1,
    answers: [],
    client_target_stage: 3,
    documents_stale: false,
    // #646 (Batch F): required since; not under test here. A fresh
    // draft with no completed run on load: "none", its true state.
    ai_source: {
      state: "none",
      sentence: "No AI suggestions were used in this assessment.",
      live_runs: 0,
      fixture_runs: 0,
    },
  } as unknown as ZtAssessment);
  vi.mocked(ztClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(ztClient.fetchScore).mockResolvedValue(
    {} as unknown as ZtScoreSummary,
  );
  vi.mocked(ztClient.fetchGapAnalysis).mockResolvedValue(
    {} as unknown as GapAnalysis,
  );
  vi.mocked(ztClient.runZtAi).mockReset();
});

async function runAiRejectingWith(err: Error): Promise<void> {
  vi.mocked(ztClient.runZtAi).mockRejectedValueOnce(err);
  render(
    <ZtWorkspace
      serviceId="svc-550-zt"
      framework="dod_ztra"
      serviceTitle="Atlas Zero Trust"
      section="ai-draft"
    />,
  );
  const button = await screen.findByRole("button", { name: "Run AI" });
  expect(button).toBeEnabled();
  fireEvent.click(button);
}

describe("ZtWorkspace AI draft, a Run AI whose outcome is unknown (#1379)", () => {
  it("names the Review section, not a numbered step, and keeps Run AI off", async () => {
    await runAiRejectingWith(OUTCOME_UNKNOWN);

    expect(await screen.findByText(COPY)).toBeInTheDocument();
    expect(screen.queryByText(/check step 2/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run AI" })).toBeDisabled();
  });
});
