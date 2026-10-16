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

// #1176's wiring: the workspace reads the category list once and hands it to
// the table. The dropdown itself is covered in
// EditableCapabilityTable.category.test.tsx; this stand-in prints what the
// table was given, so replacing the wiring with `null` goes red here.
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
    categories,
  }: {
    categories?: { categories: string[] } | null;
  }) => (
    <p>{`table categories: ${categories ? categories.categories.join(", ") : "none"}`}</p>
  ),
}));

const m = vi.mocked(techDebtClient);

function mount(): void {
  m.fetchLatestList.mockResolvedValue({
    id: "list-1",
    status: "draft",
    version: 1,
    items: [],
    excluded_rows: [],
  } as unknown as CapabilityList);
  m.fetchOverlapAnalysis.mockResolvedValue({
    groups: [],
  } as unknown as OverlapAnalysis);
  m.fetchConsolidationPlan.mockResolvedValue({
    items: [],
  } as unknown as ConsolidationPlanSummary);
  m.fetchLatestDeliverable.mockResolvedValue(null);
  render(<TechDebtWorkspace serviceId="svc-1176" serviceTitle="TD" />);
}

describe("the workspace hands the category list to the table (#1176)", () => {
  afterEach(() => vi.clearAllMocks());

  it("passes the loaded list, with no failure shown", async () => {
    m.fetchCategories.mockResolvedValue({
      categories: ["EDR/XDR", "SIEM/SOAR"],
      uncategorized_label: "Uncategorized",
    });
    mount();
    expect(
      await screen.findByText("table categories: EDR/XDR, SIEM/SOAR"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Categories could not be loaded.")).toBeNull();
    expect(m.fetchCategories).toHaveBeenCalledTimes(1);
  });

  it("says a failed load is a failure, and gives the table no list", async () => {
    m.fetchCategories.mockRejectedValue(new Error("502"));
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Categories could not be loaded.",
    );
    expect(screen.getByText("table categories: none")).toBeInTheDocument();
  });
});
