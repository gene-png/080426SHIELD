import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as techDebtClient from "@/lib/tech_debt/client";
import type { TechDebtRun } from "@/lib/tech_debt/client";
import type { CapabilityList } from "@/lib/tech_debt/types";

import { TechDebtWorkspace } from "./TechDebtWorkspace";

/**
 * #645: a Tech Debt extraction is a background run. The client module is
 * mocked whole; the documents panel is a stand-in whose button extracts
 * offline, as an admin who acknowledged offline would.
 */
vi.mock("@/lib/tech_debt/client", () => ({
  TechDebtProxyError: class extends Error {},
  proxyMessage: (err: unknown, fallback: string) =>
    err instanceof Error ? err.message : fallback,
  addCapabilityComponents: vi.fn(),
  bulkSetDisposition: vi.fn(),
  confirmExcludedRow: vi.fn(),
  includeExcludedRow: vi.fn(),
  approveCapabilityList: vi.fn(),
  discardCapabilityList: vi.fn(),
  extractCapabilities: vi.fn(),
  fetchTechDebtRun: vi.fn(),
  fetchTechDebtRunSummary: vi.fn(),
  fetchConsolidationPlan: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  fetchLatestList: vi.fn(),
  fetchOverlapAnalysis: vi.fn(),
}));
vi.mock("@/lib/admin/aiStatus", () => ({
  useAiStatus: () => ({ status: null, settled: () => Promise.resolve(null) }),
  hasAcknowledgedOffline: () => true,
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: { kind: "loading" }, stages: null }),
}));
vi.mock("@/components/intake/Dropzone", () => ({ Dropzone: () => null }));
vi.mock("@/components/intake/RedactionDisclosure", () => ({
  RedactionDisclosure: () => null,
}));
vi.mock("./ConsolidationPlanCard", () => ({
  ConsolidationPlanCard: () => null,
}));
vi.mock("./DeliverableCard", () => ({ DeliverableCard: () => null }));
vi.mock("./DiscardDraftButton", () => ({ DiscardDraftButton: () => null }));
vi.mock("./IntakeDocumentsPanel", () => ({
  IntakeDocumentsPanel: (props: {
    onExtract: (id: string, serves: "live" | "offline") => void;
    extracting: boolean;
  }) => (
    <button
      type="button"
      disabled={props.extracting}
      onClick={() => props.onExtract("artifact-1", "offline")}
    >
      extract artifact-1
    </button>
  ),
}));
vi.mock("./OverlapDashboard", () => ({ OverlapDashboard: () => null }));
vi.mock("./ProgressStages", () => ({ ProgressStages: () => null }));
vi.mock("./SecurityClassificationQueue", () => ({
  SecurityClassificationQueue: () => null,
}));
vi.mock("./EditableCapabilityTable", () => ({
  EditableCapabilityTable: (props: { items: { name: string }[] }) => (
    <ul aria-label="rows">
      {props.items.map((i) => (
        <li key={i.name}>{i.name}</li>
      ))}
    </ul>
  ),
}));

const m = {
  extract: vi.mocked(techDebtClient.extractCapabilities),
  fetchRun: vi.mocked(techDebtClient.fetchTechDebtRun),
  fetchSummary: vi.mocked(techDebtClient.fetchTechDebtRunSummary),
  fetchLatestList: vi.mocked(techDebtClient.fetchLatestList),
};

function list(): CapabilityList {
  return {
    id: "list-1",
    status: "draft",
    version: 1,
    items: [{ id: "i1", name: "CrowdStrike Falcon" }],
    excluded_rows: [],
  } as unknown as CapabilityList;
}

function run(over: Partial<TechDebtRun> = {}): TechDebtRun {
  return {
    id: "run-1",
    service_id: "svc-1",
    subject_id: "artifact-1",
    purpose: "tech_debt_extract",
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

const STARTED = {
  run_id: "run-1",
  status: "running" as const,
  serves: "offline" as const,
  deadline_at: "2026-10-01T12:45:00Z",
  lock_until: "2026-10-01T12:50:00Z",
  joined: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  m.fetchSummary.mockResolvedValue({
    running: null,
    latest: null,
    last_completed: null,
  });
  m.fetchLatestList.mockResolvedValue(null as never);
  vi.mocked(techDebtClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(techDebtClient.fetchOverlapAnalysis).mockResolvedValue(
    null as never,
  );
  vi.mocked(techDebtClient.fetchConsolidationPlan).mockResolvedValue(
    null as never,
  );
});

describe("TechDebtWorkspace, extraction in the background (#645)", () => {
  it("follows the run it starts and shows the list once it completes", async () => {
    m.extract.mockResolvedValue(STARTED);
    m.fetchRun.mockResolvedValueOnce(
      run({ status: "completed", result: null }),
    );
    render(<TechDebtWorkspace serviceId="svc-1" serviceTitle="Atlas TD" />);
    m.fetchLatestList.mockResolvedValue(list());
    fireEvent.click(
      await screen.findByRole("button", { name: "extract artifact-1" }),
    );
    expect(m.extract).toHaveBeenCalledWith("svc-1", "artifact-1", "offline");
    expect(await screen.findByText("CrowdStrike Falcon")).toBeInTheDocument();
    expect(m.fetchRun).toHaveBeenCalledWith("run-1");
  });

  it("shows an open draft returned as it stands without following a run", async () => {
    m.extract.mockResolvedValue(list());
    render(<TechDebtWorkspace serviceId="svc-1" serviceTitle="Atlas TD" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "extract artifact-1" }),
    );
    expect(await screen.findByText("CrowdStrike Falcon")).toBeInTheDocument();
    expect(m.fetchRun).not.toHaveBeenCalled();
  });

  it("holds extraction while a run found on load is in progress", async () => {
    m.fetchSummary.mockResolvedValue({
      running: run(),
      latest: run(),
      last_completed: null,
    });
    m.fetchRun.mockReturnValue(new Promise(() => {}));
    render(<TechDebtWorkspace serviceId="svc-1" serviceTitle="Atlas TD" />);
    expect(await screen.findByTestId("ai-run-running")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "extract artifact-1" }),
    ).toBeDisabled();
  });

  it("says why a run failed and loads no list", async () => {
    m.extract.mockResolvedValue(STARTED);
    m.fetchRun.mockResolvedValueOnce(
      run({
        status: "failed",
        error_reason: "ai_call_failed",
        error_message: "The AI call failed and nothing was applied.",
        charged_likely: false,
      }),
    );
    render(<TechDebtWorkspace serviceId="svc-1" serviceTitle="Atlas TD" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "extract artifact-1" }),
    );
    expect(await screen.findByTestId("ai-run-failed")).toHaveTextContent(
      /nothing was applied/,
    );
    await waitFor(() => expect(m.fetchLatestList).toHaveBeenCalledTimes(1));
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

describe("TechDebtWorkspace, an extraction whose outcome is unknown, reconciled (#645)", () => {
  it("looks once, and follows an extraction that did start", async () => {
    m.fetchSummary
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
    m.extract.mockRejectedValueOnce(outcomeUnknown());
    render(<TechDebtWorkspace serviceId="svc-1" serviceTitle="Atlas TD" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "extract artifact-1" }),
    );
    expect(await screen.findByTestId("ai-run-running")).toBeInTheDocument();
    expect(
      screen.getByText(/couldn't confirm whether the extraction finished/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "extract artifact-1" }),
    ).toBeDisabled();
  });

  it("keeps extraction locked after the reconciled run COMPLETES (#756 round 2)", async () => {
    m.fetchSummary
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
    m.fetchRun.mockResolvedValue(run({ status: "completed", result: null }));
    m.extract.mockRejectedValueOnce(outcomeUnknown());
    render(<TechDebtWorkspace serviceId="svc-1" serviceTitle="Atlas TD" />);
    const button = await screen.findByRole("button", {
      name: "extract artifact-1",
    });
    fireEvent.click(button);
    await waitFor(() => expect(m.fetchRun).toHaveBeenCalledWith("run-1"));
    await waitFor(() =>
      expect(screen.queryByTestId("ai-run-running")).toBeNull(),
    );
    expect(
      screen.getByText(/couldn't confirm whether the extraction finished/),
    ).toBeInTheDocument();
    await waitFor(() => expect(button).not.toBeDisabled());
    fireEvent.click(button);
    await new Promise((r) => setTimeout(r, 20));
    expect(m.extract).toHaveBeenCalledTimes(1);
  });

  it("stays outcome-unknown, with no second message, when that look fails", async () => {
    m.fetchSummary
      .mockResolvedValueOnce({
        running: null,
        latest: null,
        last_completed: null,
      })
      .mockRejectedValueOnce(new Error("down"));
    m.extract.mockRejectedValueOnce(outcomeUnknown());
    render(<TechDebtWorkspace serviceId="svc-1" serviceTitle="Atlas TD" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "extract artifact-1" }),
    );
    expect(
      await screen.findByText(
        /couldn't confirm whether the extraction finished/,
      ),
    ).toBeInTheDocument();
    await waitFor(() => expect(m.fetchSummary).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId("ai-run-load-failed")).toBeNull();
  });
});

describe("TechDebtWorkspace, a re-read failing after a completed run (#645, #752's rule)", () => {
  it("says the list could not be loaded, and does NOT lock extraction", async () => {
    // The worst case for the rule: the list re-read itself comes back as an
    // outcome-unknown 504. Only the POST's own rejection may lock (#752).
    m.fetchLatestList
      .mockResolvedValueOnce(null as never)
      .mockRejectedValueOnce(outcomeUnknown());
    m.extract.mockResolvedValue(STARTED);
    m.fetchRun.mockResolvedValue(run({ status: "completed", result: null }));
    render(<TechDebtWorkspace serviceId="svc-1" serviceTitle="Atlas TD" />);
    const button = await screen.findByRole("button", {
      name: "extract artifact-1",
    });
    fireEvent.click(button);
    expect(
      // The read's own error, through this file's proxyMessage mock (which
      // returns err.message) -- not the outcome-unknown lock's copy.
      await screen.findByText("proxy 504"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/couldn't confirm whether the extraction finished/),
    ).toBeNull();
    await waitFor(() => expect(button).not.toBeDisabled());
    fireEvent.click(button);
    await waitFor(() => expect(m.extract).toHaveBeenCalledTimes(2));
  });
});

describe("TechDebtWorkspace, the list's AI source (#646)", () => {
  it("states the API's sentence for the capability list", async () => {
    m.fetchLatestList.mockResolvedValue({
      ...list(),
      ai_source: {
        state: "fixture",
        sentence:
          "OFFLINE TEST DATA: every AI suggestion in this capability list came from built-in test data, not a live AI model. Treat AI-drafted values as placeholders, not analysis.",
        live_runs: 0,
        fixture_runs: 1,
      },
    } as unknown as CapabilityList);
    render(<TechDebtWorkspace serviceId="svc-1" serviceTitle="Atlas TD" />);
    const note = await screen.findByTestId("ai-source");
    expect(note).toHaveTextContent(
      /in this capability list came from built-in test data/,
    );
    expect(note).toHaveAttribute("role", "alert");
  });
});
