import "@testing-library/jest-dom/vitest";

import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as ztClient from "@/lib/zt/client";
import type { ZtRun } from "@/lib/zt/client";
import type {
  GapAnalysis,
  ZtAssessment,
  ZtCatalog,
  ZtRunAiResponse,
  ZtScoreSummary,
} from "@/lib/zt/types";

import { ZtWorkspace } from "./ZtWorkspace";

/** #645 and #271 through the ZT workspace. The client is mocked whole. */
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
// Renders what the workspace hands it: whether editing is locked.
vi.mock("./ZtQuestionnaire", () => ({
  ZtQuestionnaire: (props: { readOnly?: boolean }) => (
    <div data-testid="questionnaire-read-only">{String(props.readOnly)}</div>
  ),
}));
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
vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: (props: {
    onProceed: (serves: "live" | "offline") => void;
    children: (p: { onClick: () => void }) => React.ReactNode;
  }) => props.children({ onClick: () => props.onProceed("offline") }),
}));

const m = {
  catalog: vi.mocked(ztClient.fetchCatalog),
  latest: vi.mocked(ztClient.fetchLatestAssessment),
  score: vi.mocked(ztClient.fetchScore),
  gap: vi.mocked(ztClient.fetchGapAnalysis),
  run: vi.mocked(ztClient.runZtAi),
  fetchRun: vi.mocked(ztClient.fetchZtRun),
  summary: vi.mocked(ztClient.fetchZtRunSummary),
};

function draft(): ZtAssessment {
  return {
    id: "zt-assess-1",
    status: "draft",
    version: 1,
    answers: [],
    client_target_stage: 3,
    documents_stale: false,
  } as unknown as ZtAssessment;
}

function result(over: Partial<ZtRunAiResponse> = {}): ZtRunAiResponse {
  return {
    changed: [],
    answers: [],
    suggestions_received: 3,
    suggestions_applied: 2,
    dropped: [{ reason: "edited", key: "ID.1", field: null, values: 1 }],
    ...over,
  };
}

function run(over: Partial<ZtRun> = {}): ZtRun {
  return {
    id: "run-1",
    service_id: "svc-1",
    purpose: "zt_score",
    status: "running",
    serves: "offline",
    started_at: "2026-10-01T12:00:00Z",
    deadline_at: "2026-10-01T12:45:00Z",
    finished_at: null,
    batches_total: null,
    batches_failed: null,
    applied_count: null,
    result: null,
    error_reason: null,
    error_message: null,
    charged_likely: null,
    ...over,
  };
}

function renderWorkspace(): void {
  render(
    <ZtWorkspace
      serviceId="svc-1"
      framework="dod_ztra"
      serviceTitle="Atlas Zero Trust"
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  m.catalog.mockResolvedValue({
    pillars: [],
    stages: [],
  } as unknown as ZtCatalog);
  m.latest.mockResolvedValue(draft());
  m.score.mockResolvedValue({} as unknown as ZtScoreSummary);
  m.gap.mockResolvedValue({} as unknown as GapAnalysis);
  vi.mocked(ztClient.fetchLatestDeliverable).mockResolvedValue(null);
  m.summary.mockResolvedValue({
    running: null,
    latest: null,
    last_completed: null,
  });
});

describe("ZtWorkspace, Run-AI in the background (#645)", () => {
  it("shows the last completed run's accounting after a reload (#271)", async () => {
    const done = run({ status: "completed", result: result() });
    m.summary.mockResolvedValue({
      running: null,
      latest: done,
      last_completed: done,
    });
    renderWorkspace();
    expect(
      await screen.findByText(/answer was edited after this run started/),
    ).toBeInTheDocument();
  });

  it("locks the questionnaire, approve and Run AI while a run found on load is in progress, and leaves discard open", async () => {
    m.summary.mockResolvedValue({
      running: run(),
      latest: run(),
      last_completed: null,
    });
    m.fetchRun.mockReturnValue(new Promise(() => {}));
    renderWorkspace();
    expect(await screen.findByTestId("ai-run-running")).toBeInTheDocument();
    expect(screen.getByTestId("questionnaire-read-only")).toHaveTextContent(
      "true",
    );
    expect(screen.getByRole("button", { name: "Running…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Discard draft" }),
    ).not.toBeDisabled();
  });

  it("starts a run with the acknowledged mode and re-reads the assessment when it completes", async () => {
    m.run.mockResolvedValue({
      run_id: "run-1",
      status: "running",
      serves: "offline",
      deadline_at: "2026-10-01T12:45:00Z",
      joined: false,
    });
    m.fetchRun.mockResolvedValueOnce(
      run({ status: "completed", result: result() }),
    );
    renderWorkspace();
    fireEvent.click(await screen.findByRole("button", { name: "Run AI" }));
    await waitFor(() => expect(m.run).toHaveBeenCalledWith("svc-1", "offline"));
    await waitFor(() => expect(m.latest).toHaveBeenCalledTimes(2));
  });
});
