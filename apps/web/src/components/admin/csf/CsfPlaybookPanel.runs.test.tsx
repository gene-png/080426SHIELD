import "@testing-library/jest-dom/vitest";

import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { CsfRun } from "@/lib/csf/client";
import type { CsfRunAiResponse, EnterpriseProfile } from "@/lib/csf/types";

import { CsfPlaybookPanel } from "./CsfPlaybookPanel";

/** #645 and #271 through the CSF panel. The client is mocked whole. */
vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class CsfProxyError extends Error {},
  fetchEnterpriseProfile: vi.fn(),
  seedProfiles: vi.fn(),
  runCsfAi: vi.fn(),
  exportPlaybook: vi.fn(),
  fetchCsfRun: vi.fn(),
  fetchCsfRunSummary: vi.fn(),
}));
vi.mock("../AiPreviewButton", () => ({ AiPreviewButton: () => null }));
// Renders what the panel hands it: whether editing is locked.
vi.mock("./CsfDimensionEditor", () => ({
  CsfDimensionEditor: (props: { readOnly?: boolean }) => (
    <div data-testid="editor-read-only">{String(props.readOnly)}</div>
  ),
}));
vi.mock("./CsfGapActionEditor", () => ({ CsfGapActionEditor: () => null }));
// The REAL RunAiGuard (#645): its AI status is what each test sets here, so
// these tests reach the guard's fail-closed path through this surface.
const aiStatus = vi.hoisted(() => {
  const ok = {
    ready: true,
    serves: "live",
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

const m = {
  ent: vi.mocked(csfClient.fetchEnterpriseProfile),
  run: vi.mocked(csfClient.runCsfAi),
  fetchRun: vi.mocked(csfClient.fetchCsfRun),
  summary: vi.mocked(csfClient.fetchCsfRunSummary),
};

function ent(): EnterpriseProfile {
  return {
    tiers_in_use: ["high"],
    subcategories: [
      {
        subcategory_code: "GV.OC-01",
        name: "GV.OC-01 outcome",
        function: "GV",
        tier_levels: { high: 2 },
        enterprise_level: 2,
        rollup_rule: 1,
        target_level: 3,
        gap: false,
        priority: null,
      },
    ],
  };
}

function run(over: Partial<CsfRun> = {}): CsfRun {
  return {
    id: "run-1",
    service_id: "svc-1",
    subject_id: "assess-1",
    purpose: "csf_score",
    status: "running",
    serves: "live",
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

function result(over: Partial<CsfRunAiResponse> = {}): CsfRunAiResponse {
  return {
    changed: [],
    rows: [],
    suggestions_received: 6,
    suggestions_applied: 5,
    dropped: [
      {
        reason: "edited",
        key: "high|GV.OC-01",
        field: null,
        values: 1,
        value: null,
      },
    ],
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  aiStatus.current = { status: aiStatus.ok, phase: "loaded" };
  m.ent.mockResolvedValue(ent());
  m.summary.mockResolvedValue({
    running: null,
    latest: null,
    last_completed: null,
  });
});

describe("CsfPlaybookPanel, Run-AI in the background (#645)", () => {
  it("shows the last completed run's accounting after a reload (#271)", async () => {
    const done = run({ status: "completed", result: result() });
    m.summary.mockResolvedValue({
      running: null,
      latest: done,
      last_completed: done,
    });
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    expect(await screen.findByText(/AI applied/)).toHaveTextContent(
      "AI applied 5 of 6 suggested score values",
    );
    // `edited` is a by-design skip, not a failure: no alert for it.
    expect(
      screen.getByText(
        /row was edited after this run started, so the run left it/,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("locks editing and Run AI while a run found on load is in progress", async () => {
    m.summary.mockResolvedValue({
      running: run(),
      latest: run(),
      last_completed: null,
    });
    m.fetchRun.mockReturnValue(new Promise(() => {}));
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    expect(await screen.findByTestId("ai-run-running")).toBeInTheDocument();
    expect(screen.getByTestId("editor-read-only")).toHaveTextContent("true");
    expect(screen.getByRole("button", { name: "Running…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Export XLSX" })).toBeDisabled();
  });

  it("starts a run with the acknowledged mode and re-reads the profile when it completes", async () => {
    m.run.mockResolvedValue({
      run_id: "run-1",
      status: "running",
      serves: "live",
      deadline_at: "2026-10-01T12:45:00Z",
      lock_until: "2026-10-01T12:50:00Z",
      joined: false,
    });
    m.fetchRun.mockResolvedValueOnce(
      run({ status: "completed", result: result() }),
    );
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Run AI (csf_score)" }),
    );
    await waitFor(() => expect(m.run).toHaveBeenCalledWith("svc-1", "live"));
    await waitFor(() => expect(m.ent).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/AI applied/)).toHaveTextContent(
      "AI applied 5 of 6 suggested score values",
    );
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

describe("CsfPlaybookPanel, a Run AI whose outcome is unknown, reconciled (#645)", () => {
  it("looks once, and follows a run that did start", async () => {
    m.summary
      .mockResolvedValueOnce({
        running: null,
        latest: null,
        last_completed: null,
      })
      .mockResolvedValueOnce({
        running: run(),
        latest: run(),
        last_completed: null,
      });
    m.fetchRun.mockReturnValue(new Promise(() => {}));
    m.run.mockRejectedValueOnce(outcomeUnknown());
    const onUnknown = vi.fn();
    render(
      <CsfPlaybookPanel serviceId="svc-1" onRunOutcomeUnknown={onUnknown} />,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Run AI (csf_score)" }),
    );
    expect(await screen.findByTestId("ai-run-running")).toBeInTheDocument();
    // The page-life lock and its copy belong to CsfWorkspace (#752); the
    // panel tells it, as before.
    expect(onUnknown).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Running…" })).toBeDisabled();
  });

  it("adds no message of its own when that look fails", async () => {
    m.summary
      .mockResolvedValueOnce({
        running: null,
        latest: null,
        last_completed: null,
      })
      .mockRejectedValueOnce(new Error("down"));
    m.run.mockRejectedValueOnce(outcomeUnknown());
    const onUnknown = vi.fn();
    render(
      <CsfPlaybookPanel serviceId="svc-1" onRunOutcomeUnknown={onUnknown} />,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Run AI (csf_score)" }),
    );
    await waitFor(() => expect(m.summary).toHaveBeenCalledTimes(2));
    expect(onUnknown).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("ai-run-load-failed")).toBeNull();
    expect(screen.queryByTestId("ai-run-running")).toBeNull();
  });
});

describe("CsfPlaybookPanel, an unreadable AI status (#645)", () => {
  it("disables Run AI while the status is unknown, and enables it after a later read succeeds", async () => {
    aiStatus.current = { status: null, phase: "error" };
    const { rerender } = render(<CsfPlaybookPanel serviceId="svc-1" />);
    expect(
      await screen.findByTestId("run-ai-status-unknown"),
    ).toHaveTextContent(/Reload the page/);
    expect(
      screen.getByRole("button", { name: "Run AI (csf_score)" }),
    ).toBeDisabled();

    aiStatus.current = { status: aiStatus.ok, phase: "loaded" };
    rerender(<CsfPlaybookPanel serviceId="svc-1" />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Run AI (csf_score)" }),
      ).toBeEnabled(),
    );
    expect(screen.queryByTestId("run-ai-status-unknown")).toBeNull();
  });
});

describe("CsfPlaybookPanel, a batched run that lost batches (#479)", () => {
  function showsLastRun(r: CsfRunAiResponse) {
    const done = run({ status: "completed", result: r });
    m.summary.mockResolvedValue({
      running: null,
      latest: done,
      last_completed: done,
    });
    render(<CsfPlaybookPanel serviceId="svc-1" />);
  }

  it("says how many batches failed and qualifies the headline", async () => {
    showsLastRun(result({ batches_total: 33, batches_failed: 2 }));
    expect(await screen.findByTestId("csf-run-incomplete")).toHaveTextContent(
      /2 of 33 batches failed, so their rows were not scored/,
    );
    expect(screen.getByText(/AI applied/)).toHaveTextContent(
      /from the batches that completed/,
    );
  });

  it("still says so when the batches that completed suggested nothing", async () => {
    showsLastRun(
      result({
        batches_total: 33,
        batches_failed: 32,
        suggestions_received: 0,
        suggestions_applied: 0,
        dropped: [],
      }),
    );
    expect(await screen.findByTestId("csf-run-incomplete")).toHaveTextContent(
      /32 of 33 batches failed/,
    );
    expect(
      screen.getByText(/The AI returned no suggestions at all/),
    ).toBeInTheDocument();
  });

  it("fails closed on a failure count with no total", async () => {
    showsLastRun(result({ batches_failed: 3 }));
    expect(await screen.findByTestId("csf-run-incomplete")).toHaveTextContent(
      /3 batches failed/,
    );
  });

  it("names a stray answer as one, in the could-not-apply alert", async () => {
    showsLastRun(
      result({
        batches_total: 33,
        batches_failed: 0,
        dropped: [
          {
            reason: "not_in_batch",
            key: "high|GV.OC-01",
            field: null,
            values: 6,
            value: null,
          },
        ],
      }),
    );
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      /answered for a row its batch was not asked about, so it was not applied/,
    );
  });

  it("says nothing about batches for a run that lost none", async () => {
    showsLastRun(result({ batches_total: 33, batches_failed: 0 }));
    expect(await screen.findByText(/AI applied/)).not.toHaveTextContent(
      /batches/,
    );
    expect(screen.queryByTestId("csf-run-incomplete")).toBeNull();
  });
});

describe("CsfPlaybookPanel, rows a batch left out (#836)", () => {
  function showsLastRun(r: CsfRunAiResponse) {
    const done = run({ status: "completed", result: r });
    m.summary.mockResolvedValue({
      running: null,
      latest: done,
      last_completed: done,
    });
    render(<CsfPlaybookPanel serviceId="svc-1" />);
  }

  const O1_PLURAL =
    "3 rows got no answer from the AI, so they keep the scores they had. On a Playbook that was not scored before, that is all zeros, which reads as Level 1. Re-run before relying on this draft:";
  const O1_SINGULAR =
    "1 row got no answer from the AI, so it keeps the scores it had. On a Playbook that was not scored before, that is all zeros, which reads as Level 1. Re-run before relying on this draft:";

  it("says how many rows got no answer, and names them", async () => {
    showsLastRun(
      result({
        rows_omitted: 3,
        omitted_rows: [
          { tier: "high", subcategory_code: "GV.OC-01" },
          { tier: "high", subcategory_code: "GV.OC-02" },
          { tier: "moderate", subcategory_code: "PR.AA-01" },
        ],
      }),
    );
    const block = await screen.findByTestId("csf-run-omitted");
    expect(block).toHaveAttribute("role", "alert");
    expect(block.querySelector("p")?.textContent).toBe(O1_PLURAL);
    const items = [...block.querySelectorAll("li")].map((li) => li.textContent);
    expect(items).toEqual([
      "High tier, GV.OC-01",
      "High tier, GV.OC-02",
      "Moderate tier, PR.AA-01",
    ]);
  });

  it("uses the singular for one row", async () => {
    showsLastRun(
      result({
        rows_omitted: 1,
        omitted_rows: [{ tier: "low", subcategory_code: "DE.CM-01" }],
      }),
    );
    const block = await screen.findByTestId("csf-run-omitted");
    expect(block.querySelector("p")?.textContent).toBe(O1_SINGULAR);
    expect(block).toHaveTextContent("Low tier, DE.CM-01");
  });

  it("lists ten rows and counts the rest", async () => {
    const rows = Array.from({ length: 12 }, (_, i) => ({
      tier: "high",
      subcategory_code: `GV.OC-${String(i + 1).padStart(2, "0")}`,
    }));
    showsLastRun(result({ rows_omitted: 12, omitted_rows: rows }));
    const block = await screen.findByTestId("csf-run-omitted");
    const items = [...block.querySelectorAll("li")].map((li) => li.textContent);
    expect(items).toHaveLength(11);
    expect(items[10]).toBe("and 2 more");
  });

  it("says so even when the run received no suggestions at all", async () => {
    // A batch that answered nothing left every row out, and that branch
    // returns before the main body.
    showsLastRun(
      result({
        suggestions_received: 0,
        suggestions_applied: 0,
        dropped: [],
        rows_omitted: 1,
        omitted_rows: [{ tier: "high", subcategory_code: "GV.OC-01" }],
      }),
    );
    expect(
      await screen.findByText(/The AI returned no suggestions at all/),
    ).toBeInTheDocument();
    expect(screen.getByTestId("csf-run-omitted")).toHaveTextContent(
      "High tier, GV.OC-01",
    );
  });

  it("says nothing for a run that left none out", async () => {
    showsLastRun(result({ rows_omitted: 0, omitted_rows: [] }));
    // The positive state first: the accounting has rendered.
    expect(await screen.findByText(/AI applied/)).toBeInTheDocument();
    expect(screen.queryByTestId("csf-run-omitted")).toBeNull();
  });

  it("says nothing for a stored result with no such field", async () => {
    showsLastRun(result());
    expect(await screen.findByText(/AI applied/)).toBeInTheDocument();
    expect(screen.queryByTestId("csf-run-omitted")).toBeNull();
  });
});
