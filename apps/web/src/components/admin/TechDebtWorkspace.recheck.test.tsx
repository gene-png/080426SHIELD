import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as techDebtClient from "@/lib/tech_debt/client";

import { TechDebtWorkspace } from "./TechDebtWorkspace";

/**
 * #1376: after an inline edit to an APPROVED list the workspace re-reads the
 * list to see whether the approval went stale. When that re-read fails, a
 * section says so with `approvalRecheckFailed(why)`. `why` is typed, friendly
 * copy: the API's own typed message when it sent one, otherwise one fixed
 * phrase. It is never a raw error string such as a browser's "Failed to fetch".
 */

// The REAL `proxyMessage` and error class: a stand-in that never returns a plain
// Error's message would hide exactly the raw text this file is about.
vi.mock("@/lib/tech_debt/client", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/lib/tech_debt/client")>();
  return {
    TechDebtProxyError: actual.TechDebtProxyError,
    proxyMessage: actual.proxyMessage,
    addCapabilityComponents: vi.fn(),
    confirmExcludedRow: vi.fn(),
    includeExcludedRow: vi.fn(),
    approveCapabilityList: vi.fn(),
    discardCapabilityList: vi.fn(),
    extractCapabilities: vi.fn(),
    // #645: the page reads the service's runs on load and polls one it
    // follows. No run, by default.
    fetchTechDebtRun: vi.fn(),
    fetchTechDebtRunSummary: vi.fn(() =>
      Promise.resolve({ running: null, latest: null, last_completed: null }),
    ),
    fetchConsolidationPlan: vi.fn(),
    fetchLatestDeliverable: vi.fn(),
    fetchLatestList: vi.fn(),
    fetchOverlapAnalysis: vi.fn(),
  };
});
// AI is live, so an upload extracts on its own (the path #509 gates).
vi.mock("@/lib/admin/aiStatus", () => ({
  useAiStatus: () => ({
    status: null,
    phase: "ready",
    settled: async () => ({ ready: true }),
  }),
  hasAcknowledgedOffline: () => false,
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: { kind: "loading" }, stages: null }),
}));
// The Dropzone stands in as a button that reports a finished upload.
vi.mock("@/components/intake/Dropzone", () => ({
  Dropzone: ({ onUploaded }: { onUploaded: (a: { id: string }) => void }) => (
    <button type="button" onClick={() => onUploaded({ id: "artifact-2" })}>
      finish upload
    </button>
  ),
}));
vi.mock("@/components/intake/RedactionDisclosure", () => ({
  RedactionDisclosure: () => null,
}));
vi.mock("./ConsolidationPlanCard", () => ({
  ConsolidationPlanCard: () => null,
}));
vi.mock("./DeliverableCard", () => ({ DeliverableCard: () => null }));
vi.mock("./DiscardDraftButton", () => ({ DiscardDraftButton: () => null }));
// Stands in for the "Extract from this" button, carrying the prop that
// disables the real one (pinned in IntakeDocumentsPanel.test.tsx).
vi.mock("./IntakeDocumentsPanel", () => ({
  IntakeDocumentsPanel: ({
    onExtract,
    extractBlocked,
  }: {
    onExtract: (artifactId: string) => void;
    extractBlocked?: boolean;
  }) => (
    <button
      type="button"
      disabled={extractBlocked === true}
      onClick={() => onExtract("artifact-1")}
    >
      extract by hand
    </button>
  ),
}));
vi.mock("./OverlapDashboard", () => ({ OverlapDashboard: () => null }));
vi.mock("./ProgressStages", () => ({ ProgressStages: () => null }));
vi.mock("./SecurityClassificationQueue", () => ({
  SecurityClassificationQueue: () => null,
}));
vi.mock("./EditableCapabilityTable", () => ({
  EditableCapabilityTable: ({
    onItemUpdate,
  }: {
    onItemUpdate: (item: unknown) => void;
  }) => (
    <button
      type="button"
      onClick={() =>
        onItemUpdate({ id: "item-1", name: "Edited", parent_item_id: null })
      }
    >
      save an edit
    </button>
  ),
}));

const fetchLatestList = vi.mocked(techDebtClient.fetchLatestList);

function approvedList() {
  return {
    id: "list-1",
    status: "approved",
    version: 1,
    approval_current: true,
    items: [{ id: "item-1", name: "Tool", parent_item_id: null }],
    source_rows_total: 1,
    exclusion_count_state: "exact",
    excluded_rows: [],
    extraction_findings: [],
    ai_source: "live",
  } as never;
}

const FIXED =
  "Your edit was saved, but the approval state could not be re-checked (the list could not be reloaded). Reload the page before generating the deliverable.";

async function editThenFailReread(err: Error): Promise<void> {
  vi.mocked(techDebtClient.fetchOverlapAnalysis).mockResolvedValue({
    groups: [],
  } as never);
  vi.mocked(techDebtClient.fetchConsolidationPlan).mockResolvedValue(
    null as never,
  );
  fetchLatestList.mockReset();
  fetchLatestList.mockResolvedValueOnce(approvedList());
  render(
    <TechDebtWorkspace
      serviceId={"svc-recheck-" + Math.random()}
      serviceTitle="TD"
      section="review"
    />,
  );
  const button = await screen.findByRole("button", { name: "save an edit" });
  fetchLatestList.mockRejectedValueOnce(err);
  await act(async () => {
    fireEvent.click(button);
  });
}

function proxyError(payload: unknown): Error {
  return new techDebtClient.TechDebtProxyError(502, payload);
}

describe("approvalRecheckFailed names a typed reason, never a raw error (#1376)", () => {
  it("a network failure says the fixed phrase, not the browser's text", async () => {
    await editThenFailReread(new TypeError("Failed to fetch"));
    expect(await screen.findByText(FIXED)).toBeInTheDocument();
    expect(screen.queryByText(/Failed to fetch/)).toBeNull();
  });

  it("an API refusal with a typed message shows that message", async () => {
    await editThenFailReread(
      proxyError({
        error: {
          reason: "list_busy",
          message: "The list is being saved by someone else.",
        },
      }),
    );
    expect(
      await screen.findByText(
        "Your edit was saved, but the approval state could not be re-checked (The list is being saved by someone else.). Reload the page before generating the deliverable.",
      ),
    ).toBeInTheDocument();
  });

  it("a bare string detail is not typed copy: the fixed phrase stands", async () => {
    await editThenFailReread(proxyError({ detail: "Traceback: KeyError 'x'" }));
    expect(await screen.findByText(FIXED)).toBeInTheDocument();
    expect(screen.queryByText(/Traceback/)).toBeNull();
  });
});
