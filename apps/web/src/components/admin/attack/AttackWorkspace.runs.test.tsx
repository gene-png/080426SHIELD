import "@testing-library/jest-dom/vitest";

import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
 * #645 and #271, through the workspace a consultant uses. The ATT&CK client
 * is mocked whole, so the only requests in play are the workspace's own; the
 * run's polling interval is the real one, so each test resolves the poll it
 * is waiting for rather than racing a timer.
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

const CATALOG = {
  techniques: [],
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
    // #646 (Batch F): required since; not under test here.
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    catalog_version: "19.2",
    catalog_current: true,
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

describe("AttackWorkspace, Run-AI in the background (#645)", () => {
  it("shows a partial run's disclosure after a reload, read from the run (#271)", async () => {
    const partial = run({
      status: "completed",
      finished_at: "2026-10-01T12:10:00Z",
      result: result({ batches_failed: 3, citations_rejected: 1 }),
    });
    m.fetchAttackRunSummary.mockResolvedValue(
      summary({ latest: partial, last_completed: partial }),
    );
    render(<AttackWorkspace serviceId="svc-1" serviceTitle="ATT&CK" />);
    expect(
      await screen.findByTestId("attack-run-incomplete"),
    ).toHaveTextContent("3 of 26 batches failed");
    expect(screen.getByTestId("attack-citations-rejected")).toBeInTheDocument();
    expect(screen.getByTestId("ai-run-from")).toBeInTheDocument();
  });

  it("shows the run's date, and no disclosure from a discarded assessment's run (#271, W1)", async () => {
    // The draft a partial run filled was discarded; this page's assessment is
    // a new one. The api is asked for THIS assessment's runs, and a run on
    // another one, should one come back, describes nothing here.
    m.fetchLatestAssessment.mockResolvedValue({ ...draft(), id: "assess-2" });
    const partial = run({
      status: "completed",
      subject_id: "assess-1",
      finished_at: "2026-10-01T12:10:00Z",
      result: result({ batches_failed: 3, citations_rejected: 1 }),
    });
    m.fetchAttackRunSummary.mockResolvedValue(
      summary({ latest: partial, last_completed: partial }),
    );
    render(<AttackWorkspace serviceId="svc-1" serviceTitle="ATT&CK" />);
    await waitFor(() =>
      expect(m.fetchAttackRunSummary).toHaveBeenCalledWith("svc-1", "assess-2"),
    );
    await screen.findByRole("button", { name: /Run AI/ });
    expect(screen.queryByTestId("attack-run-incomplete")).toBeNull();
    expect(screen.queryByTestId("attack-citations-rejected")).toBeNull();
    expect(screen.queryByTestId("ai-run-from")).toBeNull();
  });

  it("names the date of the run its disclosures come from", async () => {
    const done = run({
      status: "completed",
      finished_at: "2026-10-01T12:10:00Z",
      result: result({ batches_failed: 3 }),
    });
    m.fetchAttackRunSummary.mockResolvedValue(
      summary({ latest: done, last_completed: done }),
    );
    render(<AttackWorkspace serviceId="svc-1" serviceTitle="ATT&CK" />);
    expect(await screen.findByTestId("ai-run-from")).toHaveTextContent(
      /on Oct 1, 2026/,
    );
  });

  it("states rows the run left as a consultant edited them", async () => {
    const done = run({
      status: "completed",
      finished_at: "2026-10-01T12:10:00Z",
      result: result({ rows_skipped_edited: 2 }),
    });
    m.fetchAttackRunSummary.mockResolvedValue(
      summary({ latest: done, last_completed: done }),
    );
    render(<AttackWorkspace serviceId="svc-1" serviceTitle="ATT&CK" />);
    expect(
      await screen.findByTestId("attack-rows-skipped-edited"),
    ).toHaveTextContent("2 techniques were edited after this run started");
  });

  it("locks editing, approve and Run AI while a run found on load is in progress, and leaves discard open", async () => {
    m.fetchAttackRunSummary.mockResolvedValue(
      summary({ running: run(), latest: run() }),
    );
    m.fetchAttackRun.mockReturnValue(new Promise(() => {})); // still running
    render(<AttackWorkspace serviceId="svc-1" serviceTitle="ATT&CK" />);
    expect(await screen.findByTestId("ai-run-running")).toHaveTextContent(
      /locked until it finishes/,
    );
    expect(screen.getByTestId("panel-read-only")).toHaveTextContent("true");
    expect(screen.getByRole("button", { name: "Running…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Discard draft" }),
    ).not.toBeDisabled();
  });

  it("starts a run with the acknowledged mode, follows it, and re-reads the assessment when it completes", async () => {
    m.fetchAttackRunSummary.mockResolvedValue(summary());
    m.runAttackAi.mockResolvedValue({
      run_id: "run-1",
      status: "running",
      serves: "offline",
      deadline_at: "2026-10-01T12:45:00Z",
      lock_until: "2026-10-01T12:50:00Z",
      joined: false,
    });
    m.fetchAttackRun.mockResolvedValueOnce(
      run({
        status: "completed",
        finished_at: "2026-10-01T12:05:00Z",
        result: result({ changed: [] }),
      }),
    );
    render(<AttackWorkspace serviceId="svc-1" serviceTitle="ATT&CK" />);
    fireEvent.click(await screen.findByRole("button", { name: "Run AI" }));
    await waitFor(() =>
      expect(m.runAttackAi).toHaveBeenCalledWith("svc-1", "offline"),
    );
    await waitFor(() =>
      expect(m.fetchLatestAssessment).toHaveBeenCalledTimes(2),
    );
    expect(
      await screen.findByTestId("attack-citation-accounting"),
    ).toBeInTheDocument();
  });

  it("says why a run failed, and does not re-read an assessment it did not change", async () => {
    m.fetchAttackRunSummary.mockResolvedValue(summary());
    m.runAttackAi.mockResolvedValue({
      run_id: "run-1",
      status: "running",
      serves: "offline",
      deadline_at: "2026-10-01T12:45:00Z",
      lock_until: "2026-10-01T12:50:00Z",
      joined: false,
    });
    m.fetchAttackRun.mockResolvedValueOnce(
      run({
        status: "failed",
        error_reason: "assessment_not_editable",
        error_message:
          "This assessment was discarded or locked during the run.",
        charged_likely: false,
      }),
    );
    render(<AttackWorkspace serviceId="svc-1" serviceTitle="ATT&CK" />);
    fireEvent.click(await screen.findByRole("button", { name: "Run AI" }));
    expect(await screen.findByTestId("ai-run-failed")).toHaveTextContent(
      /discarded or locked during the run/,
    );
    expect(m.fetchLatestAssessment).toHaveBeenCalledTimes(1);
  });
});

function outcomeUnknown(): Error {
  return Object.assign(new Error("proxy 504"), {
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

describe("AttackWorkspace, a Run AI whose outcome is unknown, reconciled (#645)", () => {
  it("looks once, and follows a run that did start, keeping the page-life lock", async () => {
    m.fetchAttackRunSummary
      .mockResolvedValueOnce(summary())
      .mockResolvedValueOnce(summary({ running: run(), latest: run() }));
    m.fetchAttackRun.mockReturnValue(new Promise(() => {}));
    m.runAttackAi.mockRejectedValueOnce(outcomeUnknown());
    render(<AttackWorkspace serviceId="svc-1" serviceTitle="ATT&CK" />);
    fireEvent.click(await screen.findByRole("button", { name: "Run AI" }));
    expect(await screen.findByTestId("ai-run-running")).toBeInTheDocument();
    expect(
      screen.getByText(/couldn't confirm whether the AI run finished/),
    ).toBeInTheDocument();
    expect(m.fetchAttackRun).toHaveBeenCalledWith("run-1");
    expect(screen.getByRole("button", { name: "Running…" })).toBeDisabled();
  });

  it("keeps the page-life lock after the reconciled run COMPLETES (#756 round 2)", async () => {
    m.fetchAttackRunSummary
      .mockResolvedValueOnce(summary())
      .mockResolvedValueOnce(summary({ running: run(), latest: run() }));
    m.fetchAttackRun.mockResolvedValue(
      run({
        status: "completed",
        finished_at: "2026-10-01T12:05:00Z",
        result: result(),
      }),
    );
    m.runAttackAi.mockRejectedValueOnce(outcomeUnknown());
    render(<AttackWorkspace serviceId="svc-1" serviceTitle="ATT&CK" />);
    fireEvent.click(await screen.findByRole("button", { name: "Run AI" }));
    // The run ended, and the page re-read what it applied...
    await waitFor(() =>
      expect(m.fetchLatestAssessment).toHaveBeenCalledTimes(2),
    );
    expect(screen.queryByTestId("ai-run-running")).toBeNull();
    // ...but the POST's own outcome is still unknown, so the lock stands.
    expect(
      screen.getByText(/couldn't confirm whether the AI run finished/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run AI" })).toBeDisabled();
  });

  it("stays outcome-unknown, with no second message, when that look fails", async () => {
    m.fetchAttackRunSummary
      .mockResolvedValueOnce(summary())
      .mockRejectedValueOnce(new Error("down"));
    m.runAttackAi.mockRejectedValueOnce(outcomeUnknown());
    render(<AttackWorkspace serviceId="svc-1" serviceTitle="ATT&CK" />);
    fireEvent.click(await screen.findByRole("button", { name: "Run AI" }));
    expect(
      await screen.findByText(/couldn't confirm whether the AI run finished/),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(m.fetchAttackRunSummary).toHaveBeenCalledTimes(2),
    );
    expect(screen.queryByTestId("ai-run-load-failed")).toBeNull();
    expect(screen.queryByTestId("ai-run-running")).toBeNull();
    expect(screen.getByRole("button", { name: "Run AI" })).toBeDisabled();
  });
});

describe("AttackWorkspace, an unreadable AI status (#645)", () => {
  it("disables Run AI while the status is unknown, and enables it after a later read succeeds", async () => {
    m.fetchAttackRunSummary.mockResolvedValue(summary());
    aiStatus.current = { status: null, phase: "error" };
    const { rerender } = render(
      <AttackWorkspace serviceId="svc-1" serviceTitle="ATT&CK" />,
    );
    expect(
      await screen.findByTestId("run-ai-status-unknown"),
    ).toHaveTextContent(/Reload the page/);
    expect(screen.getByRole("button", { name: "Run AI" })).toBeDisabled();

    aiStatus.current = { status: aiStatus.ok, phase: "loaded" };
    rerender(<AttackWorkspace serviceId="svc-1" serviceTitle="ATT&CK" />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Run AI" })).toBeEnabled(),
    );
    expect(screen.queryByTestId("run-ai-status-unknown")).toBeNull();
  });
});

describe("AttackWorkspace, the assessment's AI source (#646)", () => {
  it("states the API's sentence for the assessment, warning-toned when not all live", async () => {
    m.fetchAttackRunSummary.mockResolvedValue(summary());
    m.fetchLatestAssessment.mockResolvedValue({
      ...draft(),
      ai_source: {
        state: "mixed",
        sentence:
          "OFFLINE TEST DATA: 1 of the 3 AI runs on this assessment used built-in test data, not a live AI model. Values they drafted are placeholders, not analysis.",
        live_runs: 2,
        fixture_runs: 1,
      },
    } as unknown as AttackAssessment);
    render(<AttackWorkspace serviceId="svc-1" serviceTitle="ATT&CK" />);
    const note = await screen.findByTestId("ai-source");
    expect(note).toHaveTextContent(/1 of the 3 AI runs on this assessment/);
    expect(note).toHaveAttribute("role", "alert");
  });
});
