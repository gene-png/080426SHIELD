import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as attackClient from "@/lib/attack/client";
import type {
  AttackAssessment,
  AttackCatalog,
  AttackHeatmap,
} from "@/lib/attack/types";
import type { SectionKey } from "@/components/service-shell/SectionBar";

import type * as React from "react";

import { AttackWorkspace } from "./AttackWorkspace";

/**
 * #1377: the ATT&CK workspace renders one section at a time. Every block of
 * today's page lands in exactly one section, except the ones listed in
 * SHARED, and the expectations below are literals typed from the plan's
 * section map, never read from `ATTACK_BLOCK_SECTIONS`.
 *
 * Every child is mocked to a marker with a test id, so what a section renders
 * is what the workspace chose, not what a child printed.
 */

vi.mock("@/lib/attack/client", () => ({
  AttackProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchHeatmap: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  reviewComputedStatuses: vi.fn(),
  patchCoverage: vi.fn(),
  confirmCoverageCitations: vi.fn(),
  runAttackAi: vi.fn(),
  fetchAttackRun: vi.fn(),
  fetchAttackRunSummary: vi.fn(() =>
    Promise.resolve({ running: null, latest: null, last_completed: null }),
  ),
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({
    phase: "ready",
    stages: { stages: [], kind: "attack", version: 1 },
  }),
}));

vi.mock("../ProgressStages", () => ({
  ProgressStages: function Mock() {
    return <div data-testid="stages" />;
  },
}));
vi.mock("./AttackDeliverableCard", () => ({
  AttackDeliverableCard: function Mock(p: { part?: string }) {
    return <div data-testid={`deliverable-${p.part ?? "whole"}`} />;
  },
}));
vi.mock("./AttackHeatmapCard", () => ({
  AttackHeatmapCard: function Mock() {
    return <div data-testid="heatmap" />;
  },
}));
vi.mock("./AttackMatrix", () => ({
  AttackMatrix: function Mock() {
    return <div data-testid="matrix" />;
  },
}));
vi.mock("./AttackTechniquePanel", () => ({
  AttackTechniquePanel: function Mock() {
    return <div data-testid="technique-panel" />;
  },
}));
vi.mock("./AttackAiInputsPanel", () => ({
  AttackAiInputsPanel: function Mock() {
    return <div data-testid="ai-inputs" />;
  },
}));
vi.mock("./AttackComputedReviewPanel", () => ({
  AttackComputedReviewPanel: function Mock() {
    return <div data-testid="computed-review" />;
  },
}));
vi.mock("./AttackScenarioPanel", () => ({
  AttackScenarioPanel: function Mock() {
    return <div data-testid="what-if" />;
  },
}));
vi.mock("./AttackOutsideSubsetAlert", () => ({
  AttackOutsideSubsetAlert: function Mock(p: { phase: string }) {
    return <div data-testid={`subset-${p.phase}`} />;
  },
}));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: function Mock() {
    return <div data-testid="messages" />;
  },
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: function Mock() {
    return <div data-testid="stale-docs" />;
  },
}));
vi.mock("@/components/admin/AiPreviewButton", () => ({
  AiPreviewButton: function Mock() {
    return <div data-testid="ai-preview" />;
  },
}));
vi.mock("@/components/admin/AiRunStatus", () => ({
  AiRunStatus: function Mock() {
    return <div data-testid="run-status" />;
  },
  LastRunNote: () => null,
}));
vi.mock("@/components/AiSourceNote", () => ({
  AiSourceNote: function Mock() {
    return <div data-testid="ai-source" />;
  },
}));
vi.mock("@/components/admin/DiscardDraftButton", () => ({
  DiscardDraftButton: function Mock() {
    return <div data-testid="discard" />;
  },
}));
vi.mock("@/components/admin/StartRevisionButton", () => ({
  StartRevisionButton: function Mock() {
    return <div data-testid="start-revision" />;
  },
}));
vi.mock("@/components/admin/RevisionBanner", () => ({
  RevisionBanner: function Mock() {
    return <div data-testid="revision-banner" />;
  },
}));
vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: (props: {
    onProceed: () => void;
    children: (p: {
      onClick: () => void;
      statusUnknown: boolean;
    }) => React.ReactNode;
  }) => props.children({ onClick: props.onProceed, statusUnknown: false }),
}));

function draft(): AttackAssessment {
  return {
    id: "assess-1",
    service_id: "svc-1377",
    status: "draft",
    version: 1,
    coverage: [{ id: "r1", technique_code: "T1", status: "covered" }],
    documents_stale: false,
    statuses_computed: true,
    ai_source: {
      state: "none",
      sentence: "No AI suggestions were used in this assessment.",
      live_runs: 0,
      fixture_runs: 0,
    },
    catalog_version: "19.2",
    catalog_current: true,
  } as unknown as AttackAssessment;
}

beforeEach(() => {
  vi.mocked(attackClient.fetchCatalog).mockResolvedValue({
    techniques: [],
    coverage_definitions: [],
    reason_codes: [],
  } as unknown as AttackCatalog);
  vi.mocked(attackClient.fetchHeatmap).mockResolvedValue({
    by_tactic: [],
  } as unknown as AttackHeatmap);
  vi.mocked(attackClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(attackClient.fetchLatestAssessment).mockResolvedValue(draft());
});
afterEach(cleanup);

/** Every marker a section can show, in one list. */
const MARKERS = [
  "stages",
  "revision-banner",
  "discard",
  "start-revision",
  "ai-inputs",
  "ai-preview",
  "run-status",
  "ai-source",
  "technique-panel",
  "matrix",
  "computed-review",
  "subset-draft",
  "subset-approved",
  "stale-docs",
  "deliverable-generate",
  "deliverable-preview",
  "deliverable-release",
  "heatmap",
  "what-if",
  "messages",
] as const;

/** What each section shows, typed from the plan v2 section map. */
const EXPECTED: Record<SectionKey, readonly string[]> = {
  overview: [
    "stages",
    "revision-banner",
    "discard",
    "start-revision",
    "messages",
  ],
  inputs: ["ai-inputs"],
  "ai-draft": ["ai-preview", "run-status", "ai-source"],
  review: ["technique-panel", "matrix", "subset-draft", "computed-review"],
  analysis: ["heatmap", "what-if"],
  generate: ["stale-docs", "subset-approved", "deliverable-generate"],
  "quality-check": ["deliverable-preview"],
  "approve-and-release": ["deliverable-release"],
  recommendations: [],
};

async function open(section: SectionKey): Promise<void> {
  render(
    <AttackWorkspace
      serviceId="svc-1377"
      serviceTitle="ATT&CK"
      section={section}
    />,
  );
  // Wait on the section's own level-1 heading before anything is absent.
  await screen.findByRole("heading", { level: 1 });
}

function shown(): string[] {
  return MARKERS.filter((m) => screen.queryByTestId(m) !== null);
}

describe("each ATT&CK section shows only its own blocks (#1377)", () => {
  const sections = Object.keys(EXPECTED) as SectionKey[];

  it.each(sections)("%s", async (section) => {
    await open(section);
    // The assessment loads after the heading; wait for what that section
    // needs before judging absence.
    if (EXPECTED[section].length > 0) {
      await screen.findByTestId(EXPECTED[section][0]);
    } else {
      await screen.findByText(/not built for MITRE ATT&CK/);
    }
    expect(shown().sort()).toEqual([...EXPECTED[section]].sort());
  });

  it("no block of the old page is lost: every marker is in some section", () => {
    const covered = new Set(Object.values(EXPECTED).flat());
    expect(MARKERS.filter((m) => !covered.has(m))).toEqual([]);
  });

  it("no block is in two sections", () => {
    const all = Object.values(EXPECTED).flat();
    expect(all.length).toBe(new Set(all).size);
  });
});

describe("the controls land in one section each (#1377)", () => {
  it("Run AI is in AI draft only", async () => {
    await open("ai-draft");
    expect(
      await screen.findByRole("button", { name: "Run AI" }),
    ).toBeInTheDocument();
    cleanup();
    await open("review");
    await screen.findByTestId("matrix");
    expect(screen.queryByRole("button", { name: "Run AI" })).toBeNull();
  });

  it("Approve is in Review only", async () => {
    await open("review");
    expect(
      await screen.findByRole("button", { name: "Approve" }),
    ).toBeInTheDocument();
    cleanup();
    await open("ai-draft");
    await screen.findByTestId("ai-preview");
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });

  it("the section heading is the section's name, once", async () => {
    await open("quality-check");
    await screen.findByTestId("deliverable-preview");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Quality check",
    );
  });
});

describe("a section that needs an assessment says where to start one (#1377)", () => {
  it("Review with no assessment points to Overview, and Overview offers Start assessment", async () => {
    vi.mocked(attackClient.fetchLatestAssessment).mockResolvedValue(null);
    await open("review");
    expect(
      await screen.findByText(/Start the assessment in Overview/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Start assessment" }),
    ).toBeNull();
    cleanup();
    await open("overview");
    expect(
      await screen.findByRole("button", { name: "Start assessment" }),
    ).toBeInTheDocument();
  });
});

describe("the whole page is unchanged without a section (#1377)", () => {
  it("shows every block and the four numbered steps", async () => {
    render(<AttackWorkspace serviceId="svc-1377" serviceTitle="ATT&CK" />);
    await screen.findByRole("heading", {
      name: "Step 4: Generate and release the deliverable",
    });
    for (const n of [
      "Step 1: Draft the mapping with AI",
      "Step 2: Review every technique and adjust",
      "Step 3: Approve the assessment",
    ]) {
      // A done step reads "... — done", so match the start of the name.
      expect(
        screen.getByRole("heading", { name: new RegExp(`^${n}`) }),
      ).toBeInTheDocument();
    }
    expect(screen.getByTestId("deliverable-whole")).toBeInTheDocument();
    expect(shown().sort()).toEqual(
      MARKERS.filter(
        (m) =>
          m !== "deliverable-generate" &&
          m !== "deliverable-preview" &&
          m !== "deliverable-release",
      ).sort(),
    );
  });
});
