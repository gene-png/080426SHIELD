import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as techDebtClient from "@/lib/tech_debt/client";
import type {
  CapabilityList,
  ConsolidationPlanSummary,
  OverlapAnalysis,
} from "@/lib/tech_debt/types";

import { TechDebtWorkspace } from "./TechDebtWorkspace";

// TD-5 (for #1060): the workspace's "no cost" prompt counts exactly the rows
// "Let AI estimate" would ask about (the API's `estimate_targets`: uncosted,
// unlocked source rows), and "Enter costs" ends once none is left. The table
// is a stand-in that prints the rows it was given and can cost one of them.
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
  startCostEstimate: vi.fn(),
  fetchCategories: vi.fn(),
  fetchTechDebtRun: vi.fn(),
  fetchTechDebtRunSummary: vi.fn(() =>
    Promise.resolve({ running: null, latest: null, last_completed: null }),
  ),
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
    onItemUpdate,
  }: {
    items: { id: string; name: string; annual_cost_usd: number | null }[];
    onItemUpdate: (next: unknown) => void;
  }) => (
    <div>
      <p>{`table rows: ${items.map((i) => i.name).join(", ")}`}</p>
      {items
        .filter((i) => i.annual_cost_usd === null)
        .map((i) => (
          <button
            key={i.id}
            type="button"
            onClick={() => onItemUpdate({ ...i, annual_cost_usd: 500 })}
          >{`cost ${i.name}`}</button>
        ))}
      {items
        .filter((i) => i.annual_cost_usd !== null)
        .map((i) => (
          <button
            key={`un-${i.id}`}
            type="button"
            onClick={() => onItemUpdate({ ...i, annual_cost_usd: null })}
          >{`uncost ${i.name}`}</button>
        ))}
    </div>
  ),
}));

const m = vi.mocked(techDebtClient);

function row(id: string, cost: number | null, locked = false): unknown {
  return {
    id,
    capability_list_id: "list-1",
    name: id,
    vendor: null,
    category: null,
    function: null,
    annual_cost_usd: cost,
    license_count: null,
    notes: null,
    confidence_pct: 90,
    source_artifact_id: null,
    disposition: null,
    disposition_rationale: null,
    consolidation_target_id: null,
    parent_item_id: null,
    locked,
  };
}

function mount(items: unknown[]): void {
  m.fetchCategories.mockResolvedValue({
    categories: [],
    uncategorized_label: "Uncategorized",
  });
  m.fetchLatestList.mockResolvedValue({
    id: "list-1",
    status: "draft",
    version: 1,
    items,
    excluded_rows: [],
  } as unknown as CapabilityList);
  m.fetchOverlapAnalysis.mockResolvedValue({
    groups: [],
  } as unknown as OverlapAnalysis);
  m.fetchConsolidationPlan.mockResolvedValue({
    items: [],
  } as unknown as ConsolidationPlanSummary);
  m.fetchLatestDeliverable.mockResolvedValue(null);
  render(<TechDebtWorkspace serviceId="svc-1060" serviceTitle="TD" />);
}

describe("the workspace's cost-estimate prompt (TD-5)", () => {
  afterEach(() => vi.clearAllMocks());

  it("counts only the rows the estimate would ask about, never a locked one", async () => {
    mount([
      row("a", null),
      row("b", null),
      row("held", null, true),
      row("c", 100),
    ]);
    // E1, typed from the approved copy (#736 6205600298).
    expect(
      await screen.findByText(
        "These 2 tools have no cost, or none was provided. Enter costs, or let AI estimate?",
      ),
    ).toBeInTheDocument();
  });

  it("offers no estimate when every uncosted row is locked", async () => {
    mount([row("held", null, true), row("c", 100)]);
    // POSITIVE CONTROL: the list has loaded.
    expect(await screen.findByText("table rows: held, c")).toBeInTheDocument();
    expect(screen.queryByTestId("cost-estimate-prompt")).toBeNull();
  });

  it("ends 'Enter costs' once the last uncosted row has a cost", async () => {
    mount([row("a", null), row("c", 100)]);
    fireEvent.click(await screen.findByRole("button", { name: "Enter costs" }));
    expect(await screen.findByText("table rows: a")).toBeInTheDocument();
    expect(screen.getByText("Showing 1 of 2 rows")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "cost a" }));
    // Every row again, and no count over an empty table.
    expect(await screen.findByText("table rows: a, c")).toBeInTheDocument();
    expect(screen.queryByText(/^Showing \d+ of \d+ rows$/)).toBeNull();
    // A row that later loses its cost does not switch the ended view back on.
    fireEvent.click(screen.getByRole("button", { name: "uncost c" }));
    expect(
      await screen.findByText(
        "This tool has no cost, or none was provided. Enter a cost, or let AI estimate?",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("table rows: a, c")).toBeInTheDocument();
    expect(screen.queryByText(/^Showing \d+ of \d+ rows$/)).toBeNull();
  });
});
