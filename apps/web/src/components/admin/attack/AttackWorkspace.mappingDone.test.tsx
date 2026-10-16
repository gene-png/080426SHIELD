import "@testing-library/jest-dom/vitest";

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as attackClient from "@/lib/attack/client";
import type { AttackRun } from "@/lib/attack/client";
import type { AiRunSummary } from "@/lib/aiRuns/types";
import type {
  AttackAssessment,
  AttackCatalog,
  AttackHeatmap,
  AttackRunAiResponse,
} from "@/lib/attack/types";

import { AttackWorkspace } from "./AttackWorkspace";

/**
 * #1182 (review B1): the workspace hands the "Mapping done" line the run's
 * APPLIED count and its failed-batch count, never the changed count. The
 * component's own test supplies its props; this pins the wiring. The setup
 * is `AttackWorkspace.runs.test.tsx`'s, copied rather than imported so that
 * file is unchanged. Expected lines are written from the counts each test
 * sets, and the total from the catalog it builds.
 */
vi.mock("@/lib/attack/client", () => ({
  AttackProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchHeatmap: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  discardAssessment: vi.fn(),
  patchCoverage: vi.fn(),
  confirmCoverageCitations: vi.fn(),
  runAttackAi: vi.fn(),
  fetchAttackRun: vi.fn(),
  fetchAttackRunSummary: vi.fn(),
}));
vi.mock("./AttackDeliverableCard", () => ({
  AttackDeliverableCard: () => null,
}));
vi.mock("./AttackHeatmapCard", () => ({ AttackHeatmapCard: () => null }));
vi.mock("./AttackMatrix", () => ({ AttackMatrix: () => null }));
// Renders what the workspace hands it: whether editing is locked.
vi.mock("./AttackTechniquePanel", () => ({
  AttackTechniquePanel: (props: { readOnly?: boolean }) => (
    <div data-testid="panel-read-only">{String(props.readOnly)}</div>
  ),
}));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));
// The guard decides WHAT was acknowledged; its own tests cover how. Here it
// proceeds as an admin who chose to continue offline.
// The REAL RunAiGuard (#645): its AI status is what each test sets here, so
// these tests reach the guard's fail-closed path through this surface.
const aiStatus = vi.hoisted(() => {
  const ok = {
    ready: false,
    serves: "offline",
    mode: "fixture",
    provider: "anthropic",
    model: "m",
    detail: "",
    can_configure: true,
    key_source: "database",
  };
  return {
    ok,
    current: { status: ok as unknown, phase: "loaded" as string },
    refresh: vi.fn(),
  };
});
vi.mock("@/lib/admin/aiStatus", () => ({
  useAiStatus: () => ({
    status: aiStatus.current.status,
    phase: aiStatus.current.phase,
    settled: async () => aiStatus.current.status,
    refresh: aiStatus.refresh,
  }),
  // An offline status counts as already acknowledged, so a click proceeds.
  hasAcknowledgedOffline: () => true,
  acknowledgeOffline: () => undefined,
}));
vi.mock("@/components/admin/AiPreviewButton", () => ({
  AiPreviewButton: () => null,
}));
vi.mock("./AttackAiInputsPanel", () => ({
  AttackAiInputsPanel: () => null,
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: "loading", stages: null }),
}));

const m = {
  fetchCatalog: vi.mocked(attackClient.fetchCatalog),
  fetchHeatmap: vi.mocked(attackClient.fetchHeatmap),
  fetchLatestAssessment: vi.mocked(attackClient.fetchLatestAssessment),
  runAttackAi: vi.mocked(attackClient.runAttackAi),
  fetchAttackRun: vi.mocked(attackClient.fetchAttackRun),
  fetchAttackRunSummary: vi.mocked(attackClient.fetchAttackRunSummary),
};

// One parent with two sub-techniques, plus four standalone techniques: six
// mappable (the parent is computed, so it is never asked about).
const TECH = (id: string, parent_id: string | null) => ({
  id,
  name: id,
  tactics: ["reconnaissance"],
  parent_id,
  is_sub_technique: parent_id !== null,
});
const CATALOG = {
  techniques: [
    TECH("T1001", null),
    TECH("T1001.001", "T1001"),
    TECH("T1001.002", "T1001"),
    TECH("T1002", null),
    TECH("T1003", null),
    TECH("T1004", null),
    TECH("T1005", null),
  ],
  coverage_definitions: [],
  reason_codes: [],
} as unknown as AttackCatalog;
const HEATMAP = { by_tactic: [] } as unknown as AttackHeatmap;

function draft(): AttackAssessment {
  return {
    id: "assess-1",
    status: "draft",
    version: 1,
    coverage: [{ id: "c1", technique_code: "T1595", status: "covered" }],
    documents_stale: false,
    // #646 (Batch F): required since; not under test here. A fresh
    // draft with no completed run on load: "none", its true state.
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

/** #646 (#778 review F3): the draft as the api returns it once a completed
 *  OFFLINE run is on it: its AI source is "fixture", never "none". */
function draftAfterOfflineRun(): AttackAssessment {
  return {
    ...draft(),
    ai_source: {
      state: "fixture",
      sentence:
        "OFFLINE TEST DATA: every AI suggestion in this assessment came from built-in test data, not a live AI model. Treat AI-drafted values as placeholders, not analysis.",
      live_runs: 0,
      fixture_runs: 1,
    },
  } as unknown as AttackAssessment;
}

function result(over: Partial<AttackRunAiResponse> = {}): AttackRunAiResponse {
  return {
    tools_available: 2,
    changed: [],
    coverage: [],
    batches_total: 26,
    batches_failed: 0,
    citations_confirmed: 4,
    citations_needs_review: 0,
    citations_rejected: 0,
    ...over,
  };
}

function run(over: Partial<AttackRun> = {}): AttackRun {
  return {
    id: "run-1",
    service_id: "svc-1",
    subject_id: "assess-1",
    purpose: "mitre_map",
    status: "running",
    serves: "offline",
    started_at: "2026-10-01T12:00:00Z",
    deadline_at: "2026-10-01T12:45:00Z",
    lock_until: "2026-10-01T12:50:00Z",
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

function summary(
  over: Partial<AiRunSummary<AttackRunAiResponse>> = {},
): AiRunSummary<AttackRunAiResponse> {
  return { running: null, latest: null, last_completed: null, ...over };
}

beforeEach(() => {
  vi.clearAllMocks();
  aiStatus.current = { status: aiStatus.ok, phase: "loaded" };
  m.fetchCatalog.mockResolvedValue(CATALOG);
  m.fetchHeatmap.mockResolvedValue(HEATMAP);
  m.fetchLatestAssessment.mockResolvedValue(draft());
  vi.mocked(attackClient.fetchLatestDeliverable).mockResolvedValue(null);
});

const TWO_CHANGED = [
  { technique_code: "T1002" },
  { technique_code: "T1003" },
] as unknown as AttackRunAiResponse["changed"];

function loadCompleted(appliedCount: number, batchesFailed: number) {
  const done = run({
    status: "completed",
    finished_at: "2026-10-01T12:10:00Z",
    applied_count: appliedCount,
    result: result({
      tools_available: 2,
      changed: TWO_CHANGED,
      batches_failed: batchesFailed,
    }),
  });
  m.fetchLatestAssessment.mockResolvedValue(draftAfterOfflineRun());
  m.fetchAttackRunSummary.mockResolvedValue(
    summary({ latest: done, last_completed: done }),
  );
  render(<AttackWorkspace serviceId="svc-1" serviceTitle="ATT&CK" />);
}

describe("AttackWorkspace: the Mapping done line's counts (#1182)", () => {
  it("reads the run's applied count, not the changed count", async () => {
    loadCompleted(5, 0);
    expect(await screen.findByTestId("attack-mapping-done")).toHaveTextContent(
      /^Mapping done for 2 tools across 5 ATT&CK techniques and sub-techniques\.$/,
    );
  });

  it("adds the mappable catalog total when a batch failed", async () => {
    loadCompleted(5, 1);
    expect(await screen.findByTestId("attack-mapping-done")).toHaveTextContent(
      /^Mapping done for 2 tools across 5 of 6 ATT&CK techniques and sub-techniques\.$/,
    );
  });
});
