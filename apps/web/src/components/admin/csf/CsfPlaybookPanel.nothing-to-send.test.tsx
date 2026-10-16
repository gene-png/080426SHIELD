import "@testing-library/jest-dom/vitest";

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { CsfRun } from "@/lib/csf/client";
import type { CsfRunAiResponse, EnterpriseProfile } from "@/lib/csf/types";

import { CsfPlaybookPanel } from "./CsfPlaybookPanel";

/** #1203 review, finding 1: a Run AI with no subcategory's notes to send
 * makes no call (`batches_total` 0, CSF Option 1). That is not a lost
 * response, so the panel must not raise "the AI returned no suggestions" or
 * blame the parser; C4's count (approved, #736 6205956728) says why nothing
 * was scored. A run that WAS sent and got nothing still raises it (positive
 * control). Harness from CsfPlaybookPanel.no-notes.test.tsx. */
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

const LOST = /The AI returned no suggestions at all/;

describe("CsfPlaybookPanel, a run with nothing to send", () => {
  it("states the C4 count and raises no alert when nothing was sent", async () => {
    showCompleted(
      result({
        suggestions_received: 0,
        suggestions_applied: 0,
        dropped: [],
        batches_total: 0,
        batches_failed: 0,
        no_notes_count: 106,
      }),
    );
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    expect(await screen.findByTestId("csf-run-no-notes")).toHaveTextContent(
      "106 rows have no notes, so the AI did not score them. Rows a consultant scored keep their scores.",
    );
    expect(screen.queryByText(LOST)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("still raises the alert when batches were sent and nothing came back", async () => {
    showCompleted(
      result({
        suggestions_received: 0,
        suggestions_applied: 0,
        dropped: [],
        batches_total: 3,
        batches_failed: 0,
        no_notes_count: 0,
      }),
    );
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    expect(await screen.findByText(LOST)).toBeInTheDocument();
  });
});
