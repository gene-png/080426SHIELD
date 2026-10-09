import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as techDebtClient from "@/lib/tech_debt/client";
import type {
  CapabilityItem,
  CapabilityList,
  ConsolidationPlanSummary,
  ExtractionFlagCounts,
  OverlapAnalysis,
} from "@/lib/tech_debt/types";

import { TechDebtWorkspace } from "./TechDebtWorkspace";

// C6, for #806: the E1 lines reach the screen the consultant reads. The
// workspace is mounted over a list response carrying `extraction_flags`, and
// ExtractionFlags itself is NOT mocked, so this goes red if the workspace stops
// rendering it. The table stand-in prints the rows, which is the positive state
// the absence check waits on.
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
  // #645: the workspace reads the service's runs on load. No run, by default.
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

const OVERLAP = { groups: [] } as unknown as OverlapAnalysis;
const PLAN = { items: [] } as unknown as ConsolidationPlanSummary;

function listWith(flags: ExtractionFlagCounts | null): CapabilityList {
  return {
    id: "list-1",
    status: "draft",
    version: 1,
    items: [{ id: "item-1", name: "EDR tool", disposition: null }],
    excluded_rows: [],
    extraction_flags: flags,
  } as unknown as CapabilityList;
}

function mount(list: CapabilityList): void {
  fetchLatestList.mockResolvedValue(list);
  fetchOverlapAnalysis.mockResolvedValue(OVERLAP);
  fetchConsolidationPlan.mockResolvedValue(PLAN);
  fetchLatestDeliverable.mockResolvedValue(null);
  render(<TechDebtWorkspace serviceId="svc-806" serviceTitle="TD" />);
}

describe("TechDebtWorkspace shows E1 from the list response (#806)", () => {
  afterEach(() => vi.clearAllMocks());

  it("renders an approved E1 line when the list carries a non-zero flag", async () => {
    mount(
      listWith({
        name_missing: 0,
        confidence_off_scale: 0,
        category_off_list: 2,
        source_row_duplicated: 0,
      }),
    );
    await screen.findByText("row: EDR tool");
    expect(
      screen.getByText(
        "2 rows came back with a category outside the standard list, and it was kept.",
      ),
    ).toBeVisible();
  });

  it("renders no E1 when the flags are null (not measured)", async () => {
    mount(listWith(null));
    // Positive state first, so the absence below is not vacuous.
    await screen.findByText("row: EDR tool");
    expect(screen.queryByTestId("extraction-flags")).toBeNull();
    expect(screen.queryByText(/came back/)).toBeNull();
  });
});
