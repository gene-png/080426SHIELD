import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as ztClient from "@/lib/zt/client";
import type {
  GapAnalysis,
  ZtAssessment,
  ZtCatalog,
  ZtScoreSummary,
} from "@/lib/zt/types";

import { ZtWorkspace } from "./ZtWorkspace";

/**
 * #838: answers migration 0063 kept on rows CISA ZTMM 2.0 does not have are
 * not scored, and the workspace says how many. The sentence is the API's own
 * (`retired_answers_note`, from `zt/retired.py`), written here exactly as that
 * module builds it for one answer, and rendered as given, never rebuilt.
 *
 * The mocks below are copied from `ZtWorkspace.test.tsx`, which says why they
 * are duplicated rather than shared.
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
  // #645: the workspace reads the service's runs on load and polls one it
  // follows. No run, by default.
  fetchZtRun: vi.fn(),
  fetchZtRunSummary: vi.fn(() =>
    Promise.resolve({ running: null, latest: null, last_completed: null }),
  ),
  finalizeZtDeliverable: vi.fn(),
  releaseZtDeliverable: vi.fn(),
}));

// The six-stage progress strip fetches on its own; stub it to a settled state
// so the only requests in play are the workspace's own.
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: "ready", stages: null }),
}));

// Children that fetch or render heavy trees. Stubbed so a failure inside one
// cannot be mistaken for the banner assertions below passing or failing.
// NOT `() => null`, and the difference is the whole of finding F3.
//
// Stubbed to null, `setScore`'s effect is UNOBSERVABLE: the only assertions
// available are on the banner text, so an implementation that reports the gap
// correctly and drops `setScore(scoreOutcome.value)` entirely passed all four
// tests in this file. Measured, not deduced -- the call was deleted and the
// suite stayed green. That is the #72 shape in the very test named for
// "keeps the maturity score", in the PR that exists to keep it.
//
// Rendering the prop makes the stored value observable, so "fulfilled but not
// stored" -- the half #185 was actually filed about -- is now pinned.
vi.mock("./ZtScoreCard", () => ({
  ZtScoreCard: ({ score }: { score: unknown }) => (
    <div data-testid="zt-score-card">
      {score ? "score-present" : "no-score"}
    </div>
  ),
}));
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

const ONE =
  "1 recorded answer belongs to a row that CISA ZTMM 2.0 does not have, so it is not scored.";

function draft(note: string | null, count: number): ZtAssessment {
  return {
    id: "zt-assess-838",
    status: "draft",
    version: 1,
    answers: [],
    client_target_stage: 3,
    documents_stale: false,
    ai_source: {
      state: "none",
      sentence: "No AI suggestions were used in this assessment.",
      live_runs: 0,
      fixture_runs: 0,
    },
    retired_answers: count,
    retired_answers_note: note,
  } as unknown as ZtAssessment;
}

function load(assessment: ZtAssessment, serviceId: string): void {
  vi.mocked(ztClient.fetchCatalog).mockResolvedValue({
    pillars: [],
    stages: [],
  } as unknown as ZtCatalog);
  vi.mocked(ztClient.fetchLatestAssessment).mockResolvedValue(assessment);
  vi.mocked(ztClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(ztClient.fetchScore).mockResolvedValue(
    {} as unknown as ZtScoreSummary,
  );
  vi.mocked(ztClient.fetchGapAnalysis).mockResolvedValue(
    {} as unknown as GapAnalysis,
  );
  render(
    <ZtWorkspace
      serviceId={serviceId}
      framework="cisa_ztmm_2_0"
      serviceTitle="Atlas Zero Trust"
    />,
  );
}

describe("ZtWorkspace discloses answers on rows CISA does not have (#838)", () => {
  it("shows the API's sentence", async () => {
    load(draft(ONE, 1), "svc-838-a");
    expect(await screen.findByTestId("zt-retired-answers")).toHaveTextContent(
      ONE,
    );
  });

  it("shows nothing when there is nothing to disclose", async () => {
    load(draft(null, 0), "svc-838-b");
    // What must appear, before what must not: the AI source line renders from
    // the same assessment, so the assessment has loaded.
    await screen.findByText("No AI suggestions were used in this assessment.");
    expect(screen.queryByTestId("zt-retired-answers")).toBeNull();
  });
});
