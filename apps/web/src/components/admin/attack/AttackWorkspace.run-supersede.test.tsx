import "@testing-library/jest-dom/vitest";

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import * as attackClient from "@/lib/attack/client";
import type { AttackAssessment, AttackCatalog } from "@/lib/attack/types";

import type * as React from "react";

import { AttackWorkspace } from "./AttackWorkspace";

/**
 * #756 round 2, finding 1: Run AI, then Discard while the run's poll sits in
 * its timer. The Run-AI write awaits `follow()`; if that never settles, the
 * write never ends, and every later edit's parent re-read waits for it
 * forever (#620, #554), with nothing on screen saying so.
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
vi.mock("./AttackMatrix", () => ({
  AttackMatrix: (props: { onSelectTechnique: (code: string) => void }) => (
    <button type="button" onClick={() => props.onSelectTechnique("T1001.001")}>
      select sub-technique
    </button>
  ),
}));
vi.mock("./AttackTechniquePanel", () => ({
  AttackTechniquePanel: (props: {
    onPatch: (patch: Record<string, unknown>) => void;
  }) => (
    <button type="button" onClick={() => void props.onPatch({ status: "gap" })}>
      set gap
    </button>
  ),
}));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));
vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: (props: {
    onProceed: (serves: string) => void;
    children: (p: { onClick: () => void }) => React.ReactNode;
  }) => props.children({ onClick: () => props.onProceed("offline") }),
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

const m = vi.mocked(attackClient);

const FAMILY_CATALOG = {
  techniques: [
    {
      id: "T1001",
      name: "P",
      tactics: [],
      parent_id: null,
      is_sub_technique: false,
    },
    {
      id: "T1001.001",
      name: "C1",
      tactics: [],
      parent_id: "T1001",
      is_sub_technique: true,
    },
  ],
  coverage_definitions: [],
  reason_codes: [],
} as unknown as AttackCatalog;

function assessment(id: string): AttackAssessment {
  const row = {
    id: `${id}-child`,
    technique_code: "T1001.001",
    status: "covered",
    pending_review: false,
    notes: null,
  };
  return {
    id,
    status: "draft",
    version: 1,
    coverage: [row, { ...row, id: `${id}-parent`, technique_code: "T1001" }],
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

type Run = Awaited<ReturnType<typeof attackClient.fetchAttackRun>>;

// jsdom has no <dialog>.showModal()/.close(); DiscardDraftButton opens one.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(): void {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(): void {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});

beforeEach(() => {
  vi.clearAllMocks();
  m.fetchCatalog.mockResolvedValue(FAMILY_CATALOG);
  m.fetchHeatmap.mockResolvedValue({ by_tactic: [] } as never);
  m.fetchLatestDeliverable.mockResolvedValue(null);
  m.fetchAttackRunSummary.mockResolvedValue({
    running: null,
    latest: null,
    last_completed: null,
  });
});

describe("AttackWorkspace, a run superseded by Discard (#756 round 2)", () => {
  it("ends the Run-AI write, so a later edit's parent re-read still happens", async () => {
    m.fetchLatestAssessment
      .mockResolvedValueOnce(assessment("assess-1")) // load
      .mockResolvedValueOnce(null); // after the discard
    m.runAttackAi.mockResolvedValue({
      run_id: "run-1",
      status: "running",
      serves: "offline",
      deadline_at: "2099-01-01T00:00:00Z",
      lock_until: "2099-01-01T00:05:00Z",
      joined: false,
    });
    // The first poll answers RUNNING at once: the loop then sits in its timer.
    m.fetchAttackRun.mockResolvedValue({
      id: "run-1",
      service_id: "svc-1",
      subject_id: "assess-1",
      status: "running",
      serves: "offline",
      deadline_at: "2099-01-01T00:00:00Z",
      lock_until: "2099-01-01T00:05:00Z",
      result: null,
    } as unknown as Run);
    m.discardAssessment.mockResolvedValue(undefined as never);
    m.createAssessment.mockResolvedValue(assessment("assess-2"));
    // The PATCH answers with the child alone; its parent is recomputed on
    // the server, which is what the re-read is for.
    m.patchCoverage.mockResolvedValue({
      ...assessment("assess-2").coverage[0],
      status: "gap",
    } as never);

    render(<AttackWorkspace serviceId="svc-1" serviceTitle="ATT&CK" />);
    fireEvent.click(await screen.findByRole("button", { name: "Run AI" }));
    await waitFor(() => expect(m.fetchAttackRun).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Yes, discard" }),
    );
    // Start is disabled while any action is busy, Run AI included: it
    // enabling is the Run-AI write having ended.
    const start = await screen.findByRole("button", {
      name: "Start assessment",
    });
    await waitFor(() => expect(start).not.toBeDisabled());
    fireEvent.click(start);
    expect(m.fetchAttackRun).toHaveBeenCalledTimes(1); // the old loop stopped

    fireEvent.click(await screen.findByText("select sub-technique"));
    const reads = m.fetchLatestAssessment.mock.calls.length;
    m.fetchLatestAssessment.mockResolvedValue(assessment("assess-2"));
    await act(async () => {
      fireEvent.click(screen.getByText("set gap"));
    });
    await waitFor(() =>
      expect(m.fetchLatestAssessment.mock.calls.length).toBe(reads + 1),
    );
  });
});
