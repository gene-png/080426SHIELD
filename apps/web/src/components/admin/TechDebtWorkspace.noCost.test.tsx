import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as techDebtClient from "@/lib/tech_debt/client";
import type {
  CapabilityItem,
  CapabilityList,
  ConsolidationPlanSummary,
  OverlapAnalysis,
} from "@/lib/tech_debt/types";

import { TechDebtWorkspace } from "./TechDebtWorkspace";

// TD-10 (for #1048): the workspace "Annual cost" card and the "Total cost"
// pill say how many tools have no cost and are left out of the total. Copy
// approved verbatim on #736 (6115773247; strings in 6115177462). The rule is the API's
// `no_cost_items`: source items whose cost is null. A recorded $0 is a cost,
// and a split bundle's part carries none of its own.
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
  EditableCapabilityTable: ({ items }: { items: CapabilityItem[] }) => (
    <ul aria-label="rows">
      {items.map((i) => (
        <li key={i.id}>{`row: ${i.name}`}</li>
      ))}
    </ul>
  ),
}));

const fetchLatestList = vi.mocked(techDebtClient.fetchLatestList);
const fetchOverlapAnalysis = vi.mocked(techDebtClient.fetchOverlapAnalysis);
const fetchConsolidationPlan = vi.mocked(techDebtClient.fetchConsolidationPlan);
const fetchLatestDeliverable = vi.mocked(techDebtClient.fetchLatestDeliverable);

function item(
  id: string,
  name: string,
  cost: number | null,
  parent: string | null = null,
): CapabilityItem {
  return {
    id,
    name,
    category: "EDR",
    annual_cost_usd: cost,
    confidence_pct: 90,
    disposition: null,
    parent_item_id: parent,
  } as unknown as CapabilityItem;
}

const PLURAL = "2 tools have no cost; total excludes them";
const SINGULAR = "1 tool has no cost; total excludes it";

function listWith(items: CapabilityItem[]): CapabilityList {
  return {
    id: "list-1",
    status: "draft",
    version: 1,
    items,
    excluded_rows: [],
  } as unknown as CapabilityList;
}

async function mount(items: CapabilityItem[]): Promise<void> {
  fetchLatestList.mockResolvedValue(listWith(items));
  fetchOverlapAnalysis.mockResolvedValue({
    groups: [],
  } as unknown as OverlapAnalysis);
  fetchConsolidationPlan.mockResolvedValue({
    items: [],
  } as unknown as ConsolidationPlanSummary);
  fetchLatestDeliverable.mockResolvedValue(null);
  render(<TechDebtWorkspace serviceId="svc-935" serviceTitle="TD" />);
  await screen.findByText(`row: ${items[0].name}`);
}

function card(label: string): HTMLElement {
  const el = screen.getByText(label, { exact: true }).parentElement;
  if (!el) throw new Error(`no card for ${label}`);
  return el;
}

describe("the workspace says how many tools the total leaves out (TD-10)", () => {
  afterEach(() => vi.clearAllMocks());

  it("states the plural count on the card and beside the Total cost pill", async () => {
    await mount([
      item("t1", "Costed Tool", 120000),
      item("t2", "Cloud Host A", null),
      item("t3", "Hypervisor C", null),
      item("t4", "Free Tool", 0),
    ]);
    // POSITIVE CONTROL: the total rendered.
    expect(screen.getByText("Total cost: $120,000")).toBeInTheDocument();
    expect(within(card("Annual cost")).getByText(PLURAL)).toBeInTheDocument();
    // Once on the card, once as the pill.
    expect(screen.getAllByText(PLURAL)).toHaveLength(2);
  });

  it("uses the singular for one tool", async () => {
    await mount([
      item("t1", "Costed Tool", 120000),
      item("t2", "Suite D", null),
    ]);
    expect(within(card("Annual cost")).getByText(SINGULAR)).toBeInTheDocument();
    expect(screen.getAllByText(SINGULAR)).toHaveLength(2);
  });

  it("counts neither a recorded $0 nor a bundle part", async () => {
    await mount([
      item("b", "Suite Bundle", 294120),
      item("t1", "Free Tool", 0),
      item("p1", "Bundle Part", null, "b"),
    ]);
    expect(screen.getByText("Total cost: $294,120")).toBeInTheDocument();
    expect(screen.queryByText(/no cost/)).toBeNull();
  });
});
