import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as ztClient from "@/lib/zt/client";
import type {
  GapAnalysis,
  ZtAssessment,
  ZtCatalog,
  ZtScoreSummary,
} from "@/lib/zt/types";

import { ZtWorkspace } from "./ZtWorkspace";

// #1083: Step 1 says, before anyone runs it, that the AI scores only
// capabilities with notes. The sentence is Z-1083-2 as proposed at #736
// comment 6205228372: PENDING the advisor's ruling.
const Z_1083_2 =
  "It scores only capabilities with notes recorded. A capability with no notes is not sent to the AI and keeps any stage it already has.";

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
  fetchZtRun: vi.fn(),
  fetchZtRunSummary: vi.fn(),
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
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));
vi.mock("@/components/admin/AiPreviewButton", () => ({
  AiPreviewButton: () => null,
}));
vi.mock("@/lib/admin/aiStatus", () => ({
  useAiStatus: () => ({
    status: {
      ready: false,
      serves: "offline",
      mode: "fixture",
      provider: "anthropic",
      model: "m",
      detail: "",
      can_configure: true,
      key_source: "database",
    },
    phase: "loaded",
    settled: async () => undefined,
    refresh: vi.fn(),
  }),
  hasAcknowledgedOffline: () => true,
  acknowledgeOffline: () => undefined,
}));

beforeEach(() => {
  vi.clearAllMocks();
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
    ai_source: {
      state: "none",
      sentence: "No AI suggestions were used in this assessment.",
      live_runs: 0,
      fixture_runs: 0,
    },
  } as unknown as ZtAssessment);
  vi.mocked(ztClient.fetchScore).mockResolvedValue(
    {} as unknown as ZtScoreSummary,
  );
  vi.mocked(ztClient.fetchGapAnalysis).mockResolvedValue(
    {} as unknown as GapAnalysis,
  );
  vi.mocked(ztClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(ztClient.fetchZtRunSummary).mockResolvedValue({
    running: null,
    latest: null,
    last_completed: null,
  });
});

describe("ZtWorkspace Step 1 names the notes rule (#1083)", () => {
  it("says only capabilities with notes are scored, after the targets sentence", async () => {
    render(
      <ZtWorkspace
        serviceId="svc-1"
        framework="dod_ztra"
        serviceTitle="Atlas Zero Trust"
      />,
    );
    const heading = await screen.findByRole("heading", {
      name: /^Step 1: Draft the maturity scoring with AI/,
    });
    // WorkflowStep renders its description as the heading's next sibling.
    const description = heading.nextElementSibling?.textContent ?? "";
    expect(description).toContain("It does not suggest targets.");
    expect(description).toContain(`It does not suggest targets. ${Z_1083_2}`);
  });
});
