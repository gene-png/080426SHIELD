import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as ztClient from "@/lib/zt/client";
import type {
  GapAnalysis,
  ZtAssessment,
  ZtCatalog,
  ZtScoreSummary,
} from "@/lib/zt/types";
import type { SectionKey } from "@/components/service-shell/SectionBar";

import { ZtWorkspace } from "./ZtWorkspace";

/**
 * #1379: Zero Trust is split into the client frame's sections. Each section
 * renders only its own blocks, under the shared section header, and the whole
 * page (no `section`) is unchanged. Driven through the workspace, the surface
 * an admin reaches.
 *
 * The expected markers are written out per section below, never read from
 * `ztSections.ts`, so a block moved in the map moves a marker here only on
 * purpose.
 */

vi.mock("@/lib/zt/client", () => ({
  ZtProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  fetchScore: vi.fn(),
  fetchGapAnalysis: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  discardAssessment: vi.fn(),
  startRevision: vi.fn(),
  patchAnswer: vi.fn(),
  runZtAi: vi.fn(),
  fetchZtRun: vi.fn(),
  fetchZtRunSummary: vi.fn(() =>
    Promise.resolve({ running: null, latest: null, last_completed: null }),
  ),
  finalizeZtDeliverable: vi.fn(),
  releaseZtDeliverable: vi.fn(),
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: "ready", stages: null }),
}));

// Each child is a marker, so the test reads WHICH blocks a section shows.
vi.mock("./ZtScoreCard", () => ({
  ZtScoreCard: () => <div data-testid="m-score" />,
}));
vi.mock("./ZtGapList", () => ({
  ZtGapList: () => <div data-testid="m-gap" />,
}));
vi.mock("./ZtRoadmapCard", () => ({
  ZtRoadmapCard: () => <div data-testid="m-roadmap" />,
}));
vi.mock("./ZtQuestionnaire", () => ({
  ZtQuestionnaire: () => <div data-testid="m-questionnaire" />,
}));
vi.mock("./ZtDeliverableCard", () => ({
  ZtDeliverableCard: (p: { part?: string }) => (
    <div data-testid="m-deliverable" data-part={p.part ?? "whole"} />
  ),
}));
vi.mock("./ZtRunAiAccounting", () => ({
  ZtRunAiAccounting: () => null,
  lostValueCount: () => 0,
}));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => <div data-testid="m-messages" />,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => <div data-testid="m-stale-docs" />,
}));
vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: () => <div data-testid="m-run-ai" />,
}));
vi.mock("@/components/admin/AiPreviewButton", () => ({
  AiPreviewButton: () => <div data-testid="m-ai-preview" />,
}));
vi.mock("@/components/admin/DiscardDraftButton", () => ({
  DiscardDraftButton: () => <div data-testid="m-discard" />,
}));
vi.mock("@/components/admin/StartRevisionButton", () => ({
  StartRevisionButton: () => <div data-testid="m-start-revision" />,
}));

const CATALOG = { pillars: [], stages: [] } as unknown as ZtCatalog;
const SCORE = {} as unknown as ZtScoreSummary;
const GAP = {} as unknown as GapAnalysis;

function draft(): ZtAssessment {
  return {
    id: "zt-assess-1",
    status: "draft",
    version: 1,
    answers: [],
    client_target_stage: 3,
    documents_stale: false,
    ai_source: {
      state: "none",
      sentence: "No AI suggestions were used in this assessment.",
      live_runs: 0,
      fixture_runs: 0,
    },
  } as unknown as ZtAssessment;
}

const MARKERS = [
  "m-score",
  "m-gap",
  "m-roadmap",
  "m-questionnaire",
  "m-deliverable",
  "m-stale-docs",
  "m-messages",
  "m-run-ai",
  "m-ai-preview",
  "m-discard",
  "m-start-revision",
] as const;

// Which markers each section shows (an assessment exists). Written by hand.
const EXPECTED: Record<string, readonly (typeof MARKERS)[number][]> = {
  overview: ["m-score", "m-messages", "m-discard", "m-start-revision"],
  "ai-draft": ["m-run-ai", "m-ai-preview"],
  review: ["m-questionnaire"],
  analysis: ["m-gap", "m-roadmap"],
  generate: ["m-deliverable", "m-stale-docs"],
  "quality-check": ["m-deliverable"],
  "approve-and-release": ["m-deliverable"],
  recommendations: [],
};

const DELIVERABLE_PART: Record<string, string> = {
  generate: "generate",
  "quality-check": "preview",
  "approve-and-release": "release",
};

function renderSection(section: SectionKey | undefined): void {
  render(
    <ZtWorkspace
      serviceId="svc-1379"
      framework="cisa_ztmm_2_0"
      serviceTitle="Atlas Zero Trust"
      section={section}
    />,
  );
}

beforeEach(() => {
  vi.mocked(ztClient.fetchCatalog).mockResolvedValue(CATALOG);
  vi.mocked(ztClient.fetchLatestAssessment).mockResolvedValue(draft());
  vi.mocked(ztClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(ztClient.fetchScore).mockResolvedValue(SCORE);
  vi.mocked(ztClient.fetchGapAnalysis).mockResolvedValue(GAP);
});
afterEach(cleanup);

describe("ZtWorkspace renders only the section's blocks (#1379)", () => {
  it.each(Object.keys(EXPECTED))(
    "%s shows its own blocks and no others",
    async (section) => {
      renderSection(section as SectionKey);

      // Positive first: the section's header, and the assessment's status pill
      // (Recommendations is admin-only and shows no assessment state).
      if (section === "recommendations") {
        expect(
          await screen.findByText(
            "Recommendations are not built for Zero Trust assessments yet.",
          ),
        ).toBeVisible();
        expect(screen.queryByText("Draft v1")).toBeNull();
      } else {
        expect(await screen.findByText("Draft v1")).toBeVisible();
      }
      expect(screen.getByTestId("section-visibility")).toBeVisible();
      expect(
        screen.queryByRole("heading", { level: 1, name: "Atlas Zero Trust" }),
      ).toBeNull();

      const want = EXPECTED[section]!;
      for (const id of MARKERS) {
        if (want.includes(id)) {
          expect(
            await screen.findByTestId(id),
            `${section}: ${id}`,
          ).toBeVisible();
        } else {
          expect(screen.queryByTestId(id), `${section}: ${id}`).toBeNull();
        }
      }
      const part = DELIVERABLE_PART[section];
      if (part) {
        expect(screen.getByTestId("m-deliverable")).toHaveAttribute(
          "data-part",
          part,
        );
      }
    },
  );

  it("puts Approve in Review and nowhere else", async () => {
    renderSection("review");
    expect(await screen.findByText("Draft v1")).toBeVisible();
    expect(screen.getByRole("button", { name: "Approve" })).toBeVisible();
    cleanup();

    for (const other of ["overview", "ai-draft", "analysis", "generate"]) {
      renderSection(other as SectionKey);
      expect(await screen.findByText("Draft v1")).toBeVisible();
      expect(
        screen.queryByRole("button", { name: "Approve" }),
        other,
      ).toBeNull();
      cleanup();
    }
  });

  it("with no section it is the whole page, as before", async () => {
    renderSection(undefined);
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Atlas Zero Trust",
      }),
    ).toBeVisible();
    for (const id of MARKERS) {
      expect(await screen.findByTestId(id), id).toBeVisible();
    }
    expect(screen.getByTestId("m-deliverable")).toHaveAttribute(
      "data-part",
      "whole",
    );
    expect(screen.queryByTestId("section-visibility")).toBeNull();
  });

  it("Overview offers Start assessment when there is none; Review points there instead", async () => {
    vi.mocked(ztClient.fetchLatestAssessment).mockResolvedValue(null);

    renderSection("overview");
    expect(await screen.findByText("No assessment yet")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Start assessment" }),
    ).toBeVisible();
    cleanup();

    renderSection("review");
    expect(await screen.findByText("No assessment yet")).toBeVisible();
    expect(
      await screen.findByText(
        "Start the assessment in Overview to begin scoring.",
      ),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Start assessment" }),
    ).toBeNull();
  });
});
