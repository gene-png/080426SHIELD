import "@testing-library/jest-dom/vitest";

import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { CsfRun } from "@/lib/csf/client";
import type { CsfRunAiResponse, EnterpriseProfile } from "@/lib/csf/types";

import { CsfPlaybookPanel } from "./CsfPlaybookPanel";

/** #1000 through the CSF panel: the no-notes count line and the row label.
 * The client is mocked whole (harness from CsfPlaybookPanel.runs.test.tsx). */
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
        no_notes: false,
      },
      {
        subcategory_code: "GV.OC-02",
        name: "GV.OC-02 outcome",
        function: "GV",
        tier_levels: { high: 1 },
        enterprise_level: 1,
        rollup_rule: 1,
        target_level: 3,
        gap: false,
        priority: null,
        no_notes: true,
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

function showCompleted(r: CsfRunAiResponse): void {
  const done = run({ status: "completed", result: r });
  m.summary.mockResolvedValue({
    running: null,
    latest: done,
    last_completed: done,
  });
}

describe("CsfPlaybookPanel, rows a live run did not assess (#1000)", () => {
  it("states the count of rows with no notes", async () => {
    showCompleted(result({ no_notes_count: 7 }));
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    expect(await screen.findByText(/AI applied/)).toBeInTheDocument();
    expect(screen.getByTestId("csf-run-no-notes")).toHaveTextContent(
      "Not assessed by AI (no notes): 7 rows. They keep the scores they had.",
    );
  });

  it("uses the singular for one row", async () => {
    showCompleted(result({ no_notes_count: 1 }));
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    expect(await screen.findByText(/AI applied/)).toBeInTheDocument();
    expect(screen.getByTestId("csf-run-no-notes")).toHaveTextContent(
      "Not assessed by AI (no notes): 1 row. It keeps the score it had.",
    );
  });

  it("states zero, which is a count and not an absence", async () => {
    showCompleted(result({ no_notes_count: 0 }));
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    expect(await screen.findByText(/AI applied/)).toBeInTheDocument();
    expect(screen.getByTestId("csf-run-no-notes")).toHaveTextContent(
      "Not assessed by AI (no notes): 0 rows. They keep the scores they had.",
    );
  });

  it("says nothing when the run counted nothing (an offline run)", async () => {
    showCompleted(result({ no_notes_count: null }));
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    expect(await screen.findByText(/AI applied/)).toBeInTheDocument();
    expect(screen.queryByTestId("csf-run-no-notes")).toBeNull();
    expect(screen.queryByText(/Not assessed by AI/)).toBeNull();
  });

  it("states the count when the AI returned nothing at all", async () => {
    showCompleted(
      result({
        suggestions_received: 0,
        suggestions_applied: 0,
        dropped: [],
        no_notes_count: 12,
      }),
    );
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    expect(
      await screen.findByText(/The AI returned no suggestions at all/),
    ).toBeInTheDocument();
    expect(screen.getByTestId("csf-run-no-notes")).toHaveTextContent(
      "Not assessed by AI (no notes): 12 rows. They keep the scores they had.",
    );
  });

  it("lists a no_notes drop as a by-design skip, not a failure", async () => {
    showCompleted(
      result({
        suggestions_received: 2,
        suggestions_applied: 0,
        dropped: [
          {
            reason: "no_notes",
            key: "high|GV.OC-02",
            field: null,
            values: 2,
            value: null,
          },
        ],
        no_notes_count: 1,
      }),
    );
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    expect(
      await screen.findByText(/row has no notes, so the AI does not assess it/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("labels only the Enterprise rows whose answer has no notes", async () => {
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    expect(await screen.findByText("GV.OC-01")).toBeInTheDocument();
    const labels = screen.getAllByTestId("csf-row-no-notes");
    expect(labels).toHaveLength(1);
    expect(labels[0]).toHaveTextContent(
      "No notes: a live AI run does not assess this row.",
    );
    expect(labels[0].closest("td")).toHaveTextContent("GV.OC-02");
  });
});
