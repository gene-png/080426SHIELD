import "@testing-library/jest-dom/vitest";

import { act, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as techDebtClient from "@/lib/tech_debt/client";
import type {
  CapabilityList,
  ConsolidationPlanSummary,
  Deliverable,
} from "@/lib/tech_debt/types";
import type { SectionKey } from "@/components/service-shell/SectionBar";

import { TechDebtWorkspace } from "./TechDebtWorkspace";
import { TD_BLOCK_SECTIONS } from "./techDebtSections";

/**
 * #1376, the Tech Debt pilot of the UI section split. Each section of the
 * client frame shows only its own blocks, and no block of the old page is
 * lost. The expected placement below is written from the issue's section map
 * (plan v2) and the component map posted on #1376, NOT read from
 * `TD_BLOCK_SECTIONS`, so the test can disagree with the table.
 *
 * Children are stand-ins that render a marker; the workspace's own reads are
 * mocked, so the only thing under test is where each block lands.
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
  fetchCategories: vi.fn(() => Promise.resolve({ categories: [] })),
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
  useAiStatus: () => ({ status: null, settled: () => Promise.resolve(null) }),
  hasAcknowledgedOffline: () => true,
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({
    phase: "ready",
    stages: { stages: [], kind: "tech_debt", version: 1 },
  }),
}));

const { marker } = vi.hoisted(() => ({
  marker: (id: string) =>
    function Marker() {
      return <div data-testid={id} />;
    },
}));
vi.mock("@/components/intake/Dropzone", () => ({
  Dropzone: marker("blk-upload"),
}));
vi.mock("@/components/intake/RedactionDisclosure", () => ({
  RedactionDisclosure: () => null,
}));
vi.mock("@/components/admin/AiRunStatus", () => ({
  AiRunStatus: marker("blk-run-status"),
}));
vi.mock("@/components/AiSourceNote", () => ({
  AiSourceNote: marker("blk-ai-source"),
}));
vi.mock("./ProgressStages", () => ({ ProgressStages: marker("blk-stages") }));
vi.mock("./IntakeDocumentsPanel", () => ({
  IntakeDocumentsPanel: (p: { inSection?: boolean }) => (
    <div data-testid="blk-documents" data-in-section={String(p.inSection)} />
  ),
}));
vi.mock("./DiscardDraftButton", () => ({
  DiscardDraftButton: marker("blk-discard"),
}));
vi.mock("./SecurityClassificationQueue", () => ({
  SecurityClassificationQueue: marker("blk-security-queue"),
}));
vi.mock("./ExtractionFlags", () => ({
  ExtractionFlags: marker("blk-flags"),
}));
vi.mock("./ExtractionFindings", () => ({
  ExtractionFindings: marker("blk-findings"),
}));
vi.mock("./DispositionHelp", () => ({
  DispositionHelp: marker("blk-disposition-help"),
}));
vi.mock("./BulkKeepUndecided", () => ({
  BulkKeepUndecided: marker("blk-bulk-keep"),
}));
vi.mock("./EditableCapabilityTable", () => ({
  EditableCapabilityTable: marker("blk-table"),
}));
vi.mock("./ConsolidationPlanCard", () => ({
  ConsolidationPlanCard: (p: { inSection?: boolean }) => (
    <div data-testid="blk-plan" data-in-section={String(p.inSection)} />
  ),
}));
vi.mock("./SavingsWhatIf", () => ({ SavingsWhatIf: marker("blk-what-if") }));
vi.mock("./OverlapDashboard", () => ({
  OverlapDashboard: marker("blk-overlap"),
}));
vi.mock("./DeliverableCard", () => ({
  DeliverableCard: (p: { part?: string }) => (
    <div data-testid={`blk-deliverable-${p.part ?? "whole"}`} />
  ),
}));

const fetchLatestList = vi.mocked(techDebtClient.fetchLatestList);
const fetchOverlapAnalysis = vi.mocked(techDebtClient.fetchOverlapAnalysis);
const fetchConsolidationPlan = vi.mocked(techDebtClient.fetchConsolidationPlan);
const fetchLatestDeliverable = vi.mocked(techDebtClient.fetchLatestDeliverable);

function item(n: number) {
  return {
    id: `item-${n}`,
    capability_list_id: "list-1",
    name: `Tool ${n}`,
    category: "Endpoint",
    annual_cost_usd: 100,
    confidence_pct: 90,
    disposition: null,
    parent_item_id: null,
  };
}

/** Five rows uploaded, four became capabilities, one was left out. */
function list(over: Partial<CapabilityList> = {}): CapabilityList {
  return {
    id: "list-1",
    status: "draft",
    version: 1,
    approval_current: false,
    items: [1, 2, 3, 4].map(item),
    source_rows_total: 5,
    exclusion_count_state: "exact",
    excluded_rows: [{ index: 4, summary: "a note row" }],
    extraction_findings: [],
    ai_source: "live",
    ...over,
  } as unknown as CapabilityList;
}

const PLAN = {
  capability_list_id: "list-1",
  capability_list_version: 1,
  total_items: 4,
  keep_count: 0,
  consolidate_count: 0,
  cut_count: 0,
  undecided_count: 4,
  estimated_annual_savings: 0,
  savings_cost_known: true,
} satisfies ConsolidationPlanSummary;

/** How each block is found on screen. */
const FIND: Record<string, () => HTMLElement | null> = {
  status: () => screen.queryByText("Draft v1"),
  stages: () => screen.queryByTestId("blk-stages"),
  figures: () => screen.queryByText("Low-confidence rows"),
  upload: () => screen.queryByTestId("blk-upload"),
  documents: () => screen.queryByTestId("blk-documents"),
  reconciliation: () =>
    screen.queryByRole("status", { name: "Extraction reconciliation" }),
  totalsNote: () =>
    screen.queryByRole("status", { name: "Totals cover included rows only" }),
  runStatus: () => screen.queryByTestId("blk-run-status"),
  aiSource: () => screen.queryByTestId("blk-ai-source"),
  resultCard: () => screen.queryByTestId("ai-result-card"),
  discard: () => screen.queryByTestId("blk-discard"),
  securityQueue: () => screen.queryByTestId("blk-security-queue"),
  flags: () => screen.queryByTestId("blk-flags"),
  findings: () => screen.queryByTestId("blk-findings"),
  dispositionHelp: () => screen.queryByTestId("blk-disposition-help"),
  bulkKeep: () => screen.queryByTestId("blk-bulk-keep"),
  table: () => screen.queryByTestId("blk-table"),
  approve: () => screen.queryByRole("button", { name: "Approve list" }),
  plan: () => screen.queryByTestId("blk-plan"),
  whatIf: () => screen.queryByTestId("blk-what-if"),
  overlap: () => screen.queryByTestId("blk-overlap"),
  deliverableWhole: () => screen.queryByTestId("blk-deliverable-whole"),
  deliverableGenerate: () => screen.queryByTestId("blk-deliverable-generate"),
  deliverablePreview: () => screen.queryByTestId("blk-deliverable-preview"),
  deliverableRelease: () => screen.queryByTestId("blk-deliverable-release"),
};

/** The spec: what each section shows, from the #1376 map. */
const EXPECTED: Record<SectionKey, readonly string[]> = {
  overview: ["status", "stages", "figures", "totalsNote"],
  inputs: ["status", "upload", "documents", "reconciliation", "runStatus"],
  "ai-draft": ["status", "runStatus", "aiSource", "resultCard"],
  review: [
    "status",
    "totalsNote",
    "discard",
    "securityQueue",
    "flags",
    "findings",
    "dispositionHelp",
    "bulkKeep",
    "table",
    "approve",
  ],
  analysis: ["status", "plan", "whatIf", "overlap"],
  generate: ["status", "deliverableGenerate"],
  "quality-check": ["status", "deliverablePreview"],
  "approve-and-release": ["status", "deliverableRelease"],
  recommendations: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  fetchLatestList.mockResolvedValue(list());
  fetchOverlapAnalysis.mockResolvedValue({ groups: [] } as never);
  fetchConsolidationPlan.mockResolvedValue(PLAN);
  fetchLatestDeliverable.mockResolvedValue(null as never);
});

async function renderSettled(section?: SectionKey): Promise<void> {
  render(
    <TechDebtWorkspace
      serviceId="svc-1376"
      serviceTitle="TD"
      section={section}
    />,
  );
  await waitFor(() => expect(fetchLatestDeliverable).toHaveBeenCalled());
  await act(async () => {
    await Promise.resolve();
  });
}

function shown(): string[] {
  return Object.keys(FIND).filter((key) => FIND[key]() !== null);
}

describe("Tech Debt sections show only their own blocks (#1376)", () => {
  it.each(Object.keys(EXPECTED) as SectionKey[])(
    "%s shows exactly its blocks",
    async (section) => {
      await renderSettled(section);
      expect(shown().sort()).toEqual([...EXPECTED[section]].sort());
    },
  );

  it("nothing on the whole page is lost: every block shows in some section", async () => {
    await renderSettled();
    const whole = shown();
    // The page still shows everything it did; the result card is new.
    expect(whole).not.toContain("resultCard");
    const inSomeSection = new Set(Object.values(EXPECTED).flat());
    const lost = whole.filter((key) =>
      key === "deliverableWhole"
        ? ![
            "deliverableGenerate",
            "deliverablePreview",
            "deliverableRelease",
          ].every((part) => inSomeSection.has(part))
        : !inSomeSection.has(key),
    );
    expect(lost).toEqual([]);
    // And the whole page itself is unchanged in what it holds.
    expect(whole.sort()).toEqual(
      [
        "status",
        "stages",
        "figures",
        "upload",
        "documents",
        "reconciliation",
        "runStatus",
        "aiSource",
        "discard",
        "securityQueue",
        "flags",
        "findings",
        "dispositionHelp",
        "bulkKeep",
        "table",
        "approve",
        "plan",
        "whatIf",
        "overlap",
        "deliverableWhole",
      ].sort(),
    );
  });

  it("every block in the table is placed in at least one section", () => {
    for (const [block, sections] of Object.entries(TD_BLOCK_SECTIONS)) {
      expect(sections.length, block).toBeGreaterThan(0);
    }
  });
});

describe("each section opens with the shared header (#1376)", () => {
  it("names the section as the page's heading, with its visibility", async () => {
    await renderSettled("analysis");
    expect(
      screen.getByRole("heading", { level: 1, name: "Analysis" }),
    ).toBeVisible();
    expect(screen.getByTestId("section-visibility")).toHaveTextContent(
      "Client preview",
    );
    // The old page title does not repeat inside a section.
    expect(screen.queryByText("Tech Debt service")).toBeNull();
  });

  it("Approve and release says what is released, and when, once it is", async () => {
    fetchLatestDeliverable.mockResolvedValue({
      id: "deliv-1",
      version: 2,
      released_at: "2026-10-12T10:00:00+00:00",
      finalized_at: "2026-10-11T10:00:00+00:00",
    } as unknown as Deliverable);
    await renderSettled("approve-and-release");
    await waitFor(() =>
      expect(screen.getByTestId("section-visibility")).toHaveTextContent(
        "Released to client: v2, 12 Oct 2026",
      ),
    );
  });

  it("Approve and release reads 'Client preview' before the release", async () => {
    await renderSettled("approve-and-release");
    expect(screen.getByTestId("section-visibility")).toHaveTextContent(
      "Client preview",
    );
  });

  it("the what-if is marked KENTRO ADMIN ONLY in Analysis", async () => {
    await renderSettled("analysis");
    const band = screen.getByTestId("internal-only-band");
    expect(within(band).getByTestId("blk-what-if")).toBeInTheDocument();
    expect(within(band).queryByTestId("blk-overlap")).toBeNull();
    expect(within(band).queryByTestId("blk-plan")).toBeNull();
  });
});

describe("the AI draft result card, counted in uploaded rows (#1376)", () => {
  it("an exact count: asked 5, applied 4, not applied 1, unscored 0", async () => {
    await renderSettled("ai-draft");
    const card = screen.getByTestId("ai-result-card");
    expect(card).toHaveTextContent("4 of 5 uploaded rows are in the list.");
    const figures = within(card).getByTestId("ai-result-figures");
    expect(figures).toHaveTextContent(
      "Asked5Applied4Not applied1Not in the list 1Unscored0",
    );
  });

  it("every row included reads as a success", async () => {
    fetchLatestList.mockResolvedValue(
      list({ source_rows_total: 4, excluded_rows: [] }),
    );
    await renderSettled("ai-draft");
    expect(screen.getByTestId("ai-result-card")).toHaveTextContent(
      "All 4 uploaded rows are in the list.",
    );
  });

  it("an unknown count shows no card, and says why", async () => {
    fetchLatestList.mockResolvedValue(
      list({ exclusion_count_state: "unknown", excluded_rows: [] }),
    );
    await renderSettled("ai-draft");
    expect(screen.queryByTestId("ai-result-card")).toBeNull();
    expect(
      screen.getByText(
        "This result can't be counted: the AI could not match every capability to one uploaded row. Inputs shows what is known.",
      ),
    ).toBeVisible();
  });

  it("no row count on record shows no card, and says why", async () => {
    fetchLatestList.mockResolvedValue(list({ source_rows_total: null }));
    await renderSettled("ai-draft");
    expect(screen.queryByTestId("ai-result-card")).toBeNull();
    expect(
      screen.getByText(
        "This list has no record of how many rows were uploaded, so the result can't be counted.",
      ),
    ).toBeVisible();
  });
});

describe("the exclusion disclosure reaches every place the totals are read (#1376)", () => {
  it.each(["overview", "review"] as SectionKey[])(
    "%s says the totals cover the included rows only, with the count of excluded rows",
    async (section) => {
      await renderSettled(section);
      const note = screen.getByRole("status", {
        name: "Totals cover included rows only",
      });
      expect(note).toHaveTextContent(
        "5 rows received · 4 included · 1 excluded",
      );
    },
  );

  it("an unknown excluded count is called unknown in Overview, not left as bare totals", async () => {
    fetchLatestList.mockResolvedValue(
      list({ exclusion_count_state: "unknown", excluded_rows: [] }),
    );
    await renderSettled("overview");
    expect(
      screen.getByRole("status", { name: "Totals cover included rows only" }),
    ).toHaveTextContent("excluded count unknown (at least 1)");
  });

  it("no note when every uploaded row is in the list", async () => {
    fetchLatestList.mockResolvedValue(
      list({ source_rows_total: 4, excluded_rows: [] }),
    );
    await renderSettled("overview");
    expect(
      screen.queryByRole("status", { name: "Totals cover included rows only" }),
    ).toBeNull();
  });
});

describe("a refused Include or Correctly excluded shows in Inputs, where the buttons are (#1376)", () => {
  it("shows the refusal as an alert in Inputs", async () => {
    vi.spyOn(window, "prompt").mockReturnValue("Named by hand");
    vi.mocked(techDebtClient.includeExcludedRow).mockRejectedValue(
      new Error("That row cannot be included."),
    );
    await renderSettled("inputs");
    await act(async () => {
      screen.getByText(/Show the 1 excluded row/).click();
    });
    await act(async () => {
      screen.getByRole("button", { name: /Include/ }).click();
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That row cannot be included.",
    );
  });

  it("shows a refused confirmation as an alert in Inputs", async () => {
    vi.mocked(techDebtClient.confirmExcludedRow).mockRejectedValue(
      new Error("That row cannot be confirmed."),
    );
    await renderSettled("inputs");
    await act(async () => {
      screen.getByText(/Show the 1 excluded row/).click();
    });
    await act(async () => {
      screen.getByRole("button", { name: /Correctly excluded/ }).click();
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That row cannot be confirmed.",
    );
  });
});

describe("the result card does not credit a consultant's row to the extraction (#1376)", () => {
  it("says the row is in the list, whoever put it there", async () => {
    // The state after Include on the last left-out row: five rows received,
    // five items, the last with no AI confidence and no source artifact.
    fetchLatestList.mockResolvedValue(
      list({
        excluded_rows: [],
        items: [1, 2, 3, 4, 5].map((n) =>
          n === 5 ? { ...item(n), confidence_pct: null } : item(n),
        ),
      } as never),
    );
    await renderSettled("ai-draft");
    const card = screen.getByTestId("ai-result-card");
    expect(card).toHaveTextContent("All 5 uploaded rows are in the list.");
    expect(card).not.toHaveTextContent(/extraction made/i);
  });
});

describe("copy that named a place on the old page names the section (#1376)", () => {
  it("with no list, a section points at Inputs rather than 'above'", async () => {
    fetchLatestList.mockRejectedValue(new Error("no list"));
    await renderSettled("review");
    expect(
      screen.getByText(
        "Upload an inventory in Inputs to run the first AI extraction.",
      ),
    ).toBeVisible();
  });

  it("Generate names Review, not step 3, while the list is a draft", async () => {
    await renderSettled("generate");
    expect(screen.getByRole("note")).toHaveTextContent(
      "Approve the capability list in Review before generating a deliverable from it.",
    );
  });

  it("a failed deliverable read names Generate, in every section", async () => {
    fetchLatestDeliverable.mockRejectedValue(new Error("down"));
    await renderSettled("overview");
    expect(screen.getByTestId("techdebt-refresh-error")).toHaveTextContent(
      "Couldn't check for a finalized deliverable. What Generate shows is not a statement about whether one exists.",
    );
  });

  it("the reconciliation box in Inputs names where the totals are", async () => {
    await renderSettled("inputs");
    expect(
      screen.getByRole("status", { name: "Extraction reconciliation" }),
    ).toHaveTextContent(
      "The totals in Overview and Review cover the included rows only, not the whole upload.",
    );
  });

  it("the documents panel and the plan card are told they are in a section", async () => {
    await renderSettled("inputs");
    expect(screen.getByTestId("blk-documents")).toHaveAttribute(
      "data-in-section",
      "true",
    );
  });

  it("the plan card is told it is in a section", async () => {
    await renderSettled("analysis");
    expect(screen.getByTestId("blk-plan")).toHaveAttribute(
      "data-in-section",
      "true",
    );
  });
});
