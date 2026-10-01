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
vi.mock("../RunAiGuard", () => ({
  RunAiGuard: (props: {
    onProceed: (serves: "live" | "offline") => void;
    children: (p: { onClick: () => void }) => React.ReactNode;
  }) => props.children({ onClick: () => props.onProceed("live") }),
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
    purpose: "csf_score",
    status: "running",
    serves: "live",
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

function result(over: Partial<CsfRunAiResponse> = {}): CsfRunAiResponse {
  return {
    changed: [],
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
