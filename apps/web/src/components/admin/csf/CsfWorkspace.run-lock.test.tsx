import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type {
  CsfAssessment,
  CsfCatalog,
  CsfScoreSummary,
  EnterpriseProfile,
  GapAnalysis,
} from "@/lib/csf/types";

import type * as React from "react";

import { CsfWorkspace } from "./CsfWorkspace";

/**
 * #645, review W2: CSF's Approve lives in CsfWorkspace, outside the Playbook
 * panel that follows a run, and must lock while a run is in progress, as
 * ATT&CK's and ZT's do. Mocks are #752's CsfWorkspace.outcome-unknown setup.
 */
vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class CsfProxyError extends Error {},
  fetchCatalog: vi.fn(),
  fetchInterviewQuestionnaire: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  fetchScore: vi.fn(),
  fetchGapAnalysis: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  discardAssessment: vi.fn(),
  patchAnswer: vi.fn(),
  fetchEnterpriseProfile: vi.fn(),
  seedProfiles: vi.fn(),
  runCsfAi: vi.fn(),
  // #645: the page reads the service's runs on load and polls one it
  // follows. No run, by default.
  fetchCsfRun: vi.fn(),
  fetchCsfRunSummary: vi.fn(() =>
    Promise.resolve({ running: null, latest: null, last_completed: null }),
  ),
  exportPlaybook: vi.fn(),
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: "ready", stages: null }),
}));
vi.mock("./CsfScoreCard", () => ({ CsfScoreCard: () => null }));
vi.mock("./CsfGapList", () => ({ CsfGapList: () => null }));
vi.mock("./CsfDeliverableCard", () => ({ CsfDeliverableCard: () => null }));
vi.mock("./CsfQuestionnaire", () => ({ CsfQuestionnaire: () => null }));
vi.mock("./CsfDimensionEditor", () => ({ CsfDimensionEditor: () => null }));
vi.mock("./CsfGapActionEditor", () => ({ CsfGapActionEditor: () => null }));
vi.mock("@/components/admin/AiPreviewButton", () => ({
  AiPreviewButton: () => null,
}));
vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: ({
    onProceed,
    children,
  }: {
    onProceed: () => void;
    children: (props: { onClick: () => void }) => React.ReactNode;
  }) => children({ onClick: onProceed }),
}));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));

/** What `lib/csf/client.ts` throws: its error class, envelope on `.payload`. */
const ENTERPRISE = {
  tiers_in_use: ["moderate"],
  subcategories: [
    {
      subcategory_code: "GV.OC-01",
      name: "GV.OC-01 outcome",
      function: "GV",
      tier_levels: { moderate: 2 },
      enterprise_level: 2,
      rollup_rule: 1,
      target_level: 3,
      gap: false,
      priority: null,
    },
  ],
} as EnterpriseProfile;

function draft(): CsfAssessment {
  return {
    id: "assess-550",
    status: "draft",
    version: 1,
    answers: [],
    client_target_tier: 3,
    documents_stale: false,
    // #646 (Batch F): required since; not under test here. A fresh
    // draft with no completed run on load: "none", its true state.
    ai_source: {
      state: "none",
      sentence: "No AI suggestions were used in this assessment.",
      live_runs: 0,
      fixture_runs: 0,
    },
  } as unknown as CsfAssessment;
}

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
  vi.mocked(csfClient.fetchCatalog).mockResolvedValue(
    {} as unknown as CsfCatalog,
  );
  vi.mocked(csfClient.fetchInterviewQuestionnaire).mockResolvedValue(null);
  vi.mocked(csfClient.fetchLatestAssessment).mockReset();
  vi.mocked(csfClient.fetchLatestAssessment).mockResolvedValue(draft());
  vi.mocked(csfClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(csfClient.fetchScore).mockResolvedValue(
    {} as unknown as CsfScoreSummary,
  );
  vi.mocked(csfClient.fetchGapAnalysis).mockResolvedValue(
    {} as unknown as GapAnalysis,
  );
  vi.mocked(csfClient.fetchEnterpriseProfile).mockReset();
  vi.mocked(csfClient.fetchEnterpriseProfile).mockResolvedValue(ENTERPRISE);
  vi.mocked(csfClient.runCsfAi).mockReset();
});

const RUNNING = {
  id: "run-csf",
  service_id: "svc-645-csf",
  subject_id: "assess-550",
  purpose: "csf_score",
  status: "running",
  serves: "offline",
  started_at: "2026-10-01T12:00:00Z",
  deadline_at: "2099-01-01T00:00:00Z",
  lock_until: "2099-01-01T00:05:00Z",
  finished_at: null,
  batches_total: null,
  batches_failed: null,
  applied_count: null,
  result: null,
  error_reason: null,
  error_message: null,
  charged_likely: null,
} as const;

describe("CsfWorkspace locks Approve while a Run AI is in progress (#645)", () => {
  it("disables Approve while the panel's run is in progress", async () => {
    vi.mocked(csfClient.fetchCsfRunSummary).mockResolvedValue({
      running: RUNNING,
      latest: RUNNING,
      last_completed: null,
    } as never);
    vi.mocked(csfClient.fetchCsfRun).mockReturnValue(new Promise(() => {}));
    render(<CsfWorkspace serviceId="svc-645-csf" serviceTitle="Atlas CSF" />);
    expect(await screen.findByTestId("ai-run-running")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled(),
    );
  });

  it("leaves Approve on when no run is in progress", async () => {
    vi.mocked(csfClient.fetchCsfRunSummary).mockResolvedValue({
      running: null,
      latest: null,
      last_completed: null,
    });
    render(<CsfWorkspace serviceId="svc-645-csf" serviceTitle="Atlas CSF" />);
    expect(
      await screen.findByRole("button", { name: "Approve" }),
    ).toBeEnabled();
  });
});

describe("CsfWorkspace re-reads the assessment's AI source when a run ends (#646)", () => {
  it("shows the source the run left, not the one read on load", async () => {
    const fixture = {
      ...draft(),
      ai_source: {
        state: "fixture",
        sentence:
          "OFFLINE TEST DATA: every AI suggestion in this assessment came from built-in test data, not a live AI model. Treat AI-drafted values as placeholders, not analysis.",
        live_runs: 0,
        fixture_runs: 1,
      },
    } as unknown as CsfAssessment;
    vi.mocked(csfClient.fetchLatestAssessment)
      .mockResolvedValueOnce(draft())
      .mockResolvedValue(fixture);
    vi.mocked(csfClient.fetchCsfRunSummary).mockResolvedValue({
      running: RUNNING,
      latest: RUNNING,
      last_completed: null,
    } as never);
    vi.mocked(csfClient.fetchCsfRun).mockResolvedValue({
      ...RUNNING,
      status: "completed",
      finished_at: "2026-10-01T12:05:00Z",
      result: {
        changed: [],
        rows: [],
        suggestions_received: 0,
        suggestions_applied: 0,
        dropped: [],
      },
    } as never);
    render(<CsfWorkspace serviceId="svc-645-csf" serviceTitle="Atlas CSF" />);
    expect(await screen.findByTestId("ai-source")).toHaveAttribute(
      "data-state",
      "none",
    );
    await waitFor(() =>
      expect(screen.getByTestId("ai-source")).toHaveAttribute(
        "data-state",
        "fixture",
      ),
    );
  });
});
