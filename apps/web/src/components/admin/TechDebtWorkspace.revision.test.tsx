import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as techDebtClient from "@/lib/tech_debt/client";
import type {
  CapabilityList,
  ConsolidationPlanSummary,
  OverlapAnalysis,
} from "@/lib/tech_debt/types";

import { TechDebtWorkspace } from "./TechDebtWorkspace";

// #640: an approved list edited afterwards is not approved any more. Step 3
// offers "Approve again", step 4 says why it is blocked, and the classification
// queue stays editable until release.
vi.mock("@/lib/tech_debt/client", () => ({
  TechDebtProxyError: class extends Error {},
  proxyMessage: (err: unknown, fallback: string) =>
    err instanceof Error ? err.message : fallback,
  addCapabilityComponents: vi.fn(),
  confirmExcludedRow: vi.fn(),
  includeExcludedRow: vi.fn(),
  approveCapabilityList: vi.fn(),
  discardCapabilityList: vi.fn(),
  extractCapabilities: vi.fn(),
  fetchConsolidationPlan: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  fetchLatestList: vi.fn(),
  fetchOverlapAnalysis: vi.fn(),
}));
vi.mock("@/lib/admin/aiStatus", () => ({
  useAiStatus: () => ({ status: null }),
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
vi.mock("./IntakeDocumentsPanel", () => ({ IntakeDocumentsPanel: () => null }));
vi.mock("./OverlapDashboard", () => ({ OverlapDashboard: () => null }));
vi.mock("./ProgressStages", () => ({ ProgressStages: () => null }));
vi.mock("./EditableCapabilityTable", () => ({
  EditableCapabilityTable: () => <p>table</p>,
}));
vi.mock("./SecurityClassificationQueue", () => ({
  SecurityClassificationQueue: ({ editable }: { editable: boolean }) => (
    <p>{editable ? "queue editable" : "queue read-only"}</p>
  ),
}));

const fetchLatestList = vi.mocked(techDebtClient.fetchLatestList);

function list(status: string, approvalCurrent: boolean): CapabilityList {
  return {
    id: "list-1",
    status,
    version: 1,
    items: [{ id: "item-1", name: "One", disposition: "keep" }],
    excluded_rows: [],
    approval_current: approvalCurrent,
  } as unknown as CapabilityList;
}

function mount(l: CapabilityList): void {
  fetchLatestList.mockResolvedValue(l);
  vi.mocked(techDebtClient.fetchOverlapAnalysis).mockResolvedValue({
    groups: [],
  } as unknown as OverlapAnalysis);
  vi.mocked(techDebtClient.fetchConsolidationPlan).mockResolvedValue({
    items: [],
  } as unknown as ConsolidationPlanSummary);
  vi.mocked(techDebtClient.fetchLatestDeliverable).mockResolvedValue(null);
  render(<TechDebtWorkspace serviceId="svc-640" serviceTitle="TD" />);
}

describe("TechDebtWorkspace after an edit to an approved list (#640)", () => {
  afterEach(() => vi.clearAllMocks());

  it("offers Approve again, and says why step 4 is blocked", async () => {
    mount(list("approved", false));
    const button = await screen.findByRole("button", { name: "Approve again" });
    expect(button).toBeEnabled();
    expect(
      screen.getByText(
        "The list was edited after it was approved. Approve it again in step 3 before generating a deliverable from it.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Edited since approval v1")).toBeInTheDocument();
    expect(screen.getByText("queue editable")).toBeInTheDocument();
  });

  it("shows a current approval as done, with nothing to press", async () => {
    mount(list("approved", true));
    const button = await screen.findByRole("button", { name: "Approved" });
    expect(button).toBeDisabled();
    expect(screen.getByText("Approved v1")).toBeInTheDocument();
    expect(
      screen.queryByText(/edited after it was approved/),
    ).not.toBeInTheDocument();
    // Still editable: an edit is what makes the approval stale.
    expect(screen.getByText("queue editable")).toBeInTheDocument();
  });

  it("keeps a released list read-only", async () => {
    mount(list("released", true));
    await screen.findByRole("button", { name: "Released" });
    expect(screen.getByText("queue read-only")).toBeInTheDocument();
  });
});
