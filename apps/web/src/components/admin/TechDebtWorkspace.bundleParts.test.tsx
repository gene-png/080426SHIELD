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

// for #935: the workspace's "Capabilities" card, "Annual cost" card and
// "Total cost" pill count source items only, as the client dashboard,
// the deliverable and `tech_debt/components.py` do. A split bundle's named
// parts (`parent_item_id` set) are not capabilities of their own, and a cost
// stored on a part before #927 refused one is not spend: the bundle row holds
// the licence value. The card says how many parts it leaves out (approved
// copy, #736). The table stand-in prints the rows, the positive state each
// check waits on.
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

// Four costed source tools totalling $514,120 (the #835 world), with the bundle
// split into two parts, one carrying a $20,000 cost stored before #927.
const SOURCE = [
  item("b", "Microsoft 365 E5", 294120),
  item("t1", "CrowdStrike Falcon", 120000),
  item("t2", "Okta", 60000),
  item("t3", "Slack", 40000),
];

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

describe("the workspace counts source items, not bundle parts (#935)", () => {
  afterEach(() => vi.clearAllMocks());

  it("Capabilities counts the four tools, not the two parts", async () => {
    await mount([
      ...SOURCE,
      item("p1", "Defender for Endpoint", null, "b"),
      item("p2", "Entra ID P2", 20000, "b"),
    ]);
    const cap = card("Capabilities");
    expect(within(cap).getByText("4")).toBeInTheDocument();
    expect(within(cap).queryByText("6")).toBeNull();
    expect(
      within(cap).getByText("2 bundle parts not counted"),
    ).toBeInTheDocument();
  });

  it("uses the singular for one part", async () => {
    await mount([...SOURCE, item("p1", "Defender for Endpoint", null, "b")]);
    expect(
      within(card("Capabilities")).getByText("1 bundle part not counted"),
    ).toBeInTheDocument();
  });

  it("says nothing about parts when there are none", async () => {
    await mount(SOURCE);
    const cap = card("Capabilities");
    expect(within(cap).getByText("4")).toBeInTheDocument();
    expect(within(cap).queryByText(/bundle part/)).toBeNull();
  });

  it("Annual cost and the Total cost pill leave out a part's stored cost", async () => {
    await mount([
      ...SOURCE,
      item("p1", "Defender for Endpoint", null, "b"),
      item("p2", "Entra ID P2", 20000, "b"),
    ]);
    expect(
      within(card("Annual cost")).getByText("$514,120"),
    ).toBeInTheDocument();
    expect(screen.queryByText("$534,120")).toBeNull();
    expect(screen.getByText("Total cost: $514,120")).toBeInTheDocument();
    expect(screen.queryByText("Total cost: $534,120")).toBeNull();
  });
});
