import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as techDebtClient from "@/lib/tech_debt/client";
import type {
  CapabilityDisposition,
  CapabilityItem,
  CapabilityList,
  ConsolidationPlanSummary,
  OverlapAnalysis,
} from "@/lib/tech_debt/types";

import { TechDebtWorkspace } from "./TechDebtWorkspace";

// #641's wiring: the workspace hands the table a bulk handler that writes
// through the API and replaces the list with what the API returned. The table's
// own behaviour is covered in EditableCapabilityTable.bulk.test.tsx; this
// stand-in exposes the handler as a button and prints the rows it is given.
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
vi.mock("./SecurityClassificationQueue", () => ({
  SecurityClassificationQueue: () => null,
}));
vi.mock("./EditableCapabilityTable", () => ({
  EditableCapabilityTable: ({
    items,
    onBulkDisposition,
  }: {
    items: CapabilityItem[];
    onBulkDisposition?: (
      ids: string[],
      d: CapabilityDisposition | null,
    ) => Promise<void>;
  }) => (
    <div>
      <ul aria-label="rows">
        {items.map((i) => (
          <li key={i.id}>{`${i.name}: ${i.disposition ?? "undecided"}`}</li>
        ))}
      </ul>
      {onBulkDisposition ? (
        <button
          type="button"
          onClick={() =>
            onBulkDisposition(["item-1", "item-2"], "cut").catch(
              (err: Error) => {
                document.title = `rejected: ${err.message}`;
              },
            )
          }
        >
          bulk cut
        </button>
      ) : (
        <span>no bulk handler</span>
      )}
    </div>
  ),
}));

const fetchLatestList = vi.mocked(techDebtClient.fetchLatestList);
const fetchOverlapAnalysis = vi.mocked(techDebtClient.fetchOverlapAnalysis);
const fetchConsolidationPlan = vi.mocked(techDebtClient.fetchConsolidationPlan);
const fetchLatestDeliverable = vi.mocked(techDebtClient.fetchLatestDeliverable);
const bulkSetDisposition = vi.mocked(techDebtClient.bulkSetDisposition);

const OVERLAP = { groups: [] } as unknown as OverlapAnalysis;
const PLAN = { items: [] } as unknown as ConsolidationPlanSummary;

function listWith(
  status: string,
  disposition: CapabilityDisposition | null,
): CapabilityList {
  return {
    id: "list-1",
    status,
    version: 1,
    items: [
      { id: "item-1", name: "One", disposition },
      { id: "item-2", name: "Two", disposition },
    ],
    excluded_rows: [],
  } as unknown as CapabilityList;
}

function mount(list: CapabilityList): void {
  fetchLatestList.mockResolvedValue(list);
  fetchOverlapAnalysis.mockResolvedValue(OVERLAP);
  fetchConsolidationPlan.mockResolvedValue(PLAN);
  fetchLatestDeliverable.mockResolvedValue(null);
  render(<TechDebtWorkspace serviceId="svc-641" serviceTitle="TD" />);
}

describe("TechDebtWorkspace bulk disposition (#641)", () => {
  afterEach(() => vi.clearAllMocks());

  it("writes the selection through the API and shows the list it returns", async () => {
    bulkSetDisposition.mockResolvedValue(listWith("draft", "cut"));
    mount(listWith("draft", null));
    await screen.findByText("One: undecided");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "bulk cut" }));
    });

    expect(bulkSetDisposition).toHaveBeenCalledWith(
      "list-1",
      ["item-1", "item-2"],
      "cut",
    );
    expect(screen.getByText("One: cut")).toBeInTheDocument();
    expect(screen.getByText("Two: cut")).toBeInTheDocument();
    // The consolidation plan counts dispositions, so it is refreshed too.
    expect(fetchConsolidationPlan.mock.calls.length).toBeGreaterThan(1);
  });

  it("passes a refusal back to the table and leaves the list as it was", async () => {
    bulkSetDisposition.mockRejectedValue(new Error("Nothing was changed."));
    mount(listWith("draft", null));
    await screen.findByText("One: undecided");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "bulk cut" }));
    });

    expect(document.title).toBe("rejected: Nothing was changed.");
    expect(screen.getByText("One: undecided")).toBeInTheDocument();
    expect(screen.getByText("Two: undecided")).toBeInTheDocument();
  });

  it("offers no bulk handler on a released list", async () => {
    mount(listWith("released", "keep"));
    await screen.findByText("One: keep");
    expect(screen.getByText("no bulk handler")).toBeInTheDocument();
  });
});
