import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type {
  CsfAssessment,
  CsfCatalog,
  CsfScoreSummary,
  GapAnalysis,
} from "@/lib/csf/types";

import { CsfWorkspace } from "./CsfWorkspace";

/**
 * #385 -- A FAILED GAP FETCH REVERTS THE CONTROL. The label follows the data;
 * the data is never relabelled.
 *
 * The ZT twin, `zt/ZtWorkspace.target-revert.test.tsx`, carries the reasoning
 * in full. In brief: `onChangeTargetTier` set the label first and awaited the
 * gap fetch with no catch, so a rejection left the PREVIOUS target's rows on
 * screen under the NEW target's heading.
 *
 * Separate from `CsfWorkspace.test.tsx` because that file stubs `CsfGapList`
 * to null, and the control under test -- a `<select>` labelled "Target tier"
 * -- lives inside it. Driving the surface is the point: a test that imported
 * the handler would prove a variable reverts and say nothing about the
 * screen.
 */

vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchInterviewQuestionnaire: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  fetchScore: vi.fn(),
  fetchGapAnalysis: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  discardAssessment: vi.fn(),
  patchAnswer: vi.fn(),
}));

vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: "ready", stages: null }),
}));

// EVERY CHILD BUT `CsfGapList` IS STUBBED. That one is the surface under test.
vi.mock("./CsfScoreCard", () => ({ CsfScoreCard: () => null }));
vi.mock("./CsfPlaybookPanel", () => ({ CsfPlaybookPanel: () => null }));
vi.mock("./CsfDeliverableCard", () => ({ CsfDeliverableCard: () => null }));
vi.mock("./CsfQuestionnaire", () => ({ CsfQuestionnaire: () => null }));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));

const fetchCatalog = vi.mocked(csfClient.fetchCatalog);
const fetchInterviewQuestionnaire = vi.mocked(
  csfClient.fetchInterviewQuestionnaire,
);
const fetchLatestAssessment = vi.mocked(csfClient.fetchLatestAssessment);
const fetchLatestDeliverable = vi.mocked(csfClient.fetchLatestDeliverable);
const fetchScore = vi.mocked(csfClient.fetchScore);
const fetchGapAnalysis = vi.mocked(csfClient.fetchGapAnalysis);

const CATALOG = {} as unknown as CsfCatalog;
const SCORE = {} as unknown as CsfScoreSummary;

/** The tier a row's name carries is what makes label-versus-data readable. */
function gapAt(tier: number): GapAnalysis {
  return {
    assessment_id: "csf-assess-385",
    version: 1,
    target_tier: tier,
    target_label: `tier-${tier}`,
    total_gap_count: 1,
    unscored_count: 0,
    gaps: [
      {
        code: "GV.OC-01",
        function_name: "Govern",
        name: `rows-computed-for-tier-${tier}`,
        outcome: "an outcome",
        notes: null,
        current_tier: 1,
        target_tier: tier,
        gap_size: tier - 1,
        priority_score: 1,
      },
    ],
  } as unknown as GapAnalysis;
}

/** The tier a call asked for, or a loud failure. See the ZT twin for why. */
function requestedTier(opts?: { targetTier?: number }): number {
  if (opts?.targetTier === undefined) {
    throw new Error("fetchGapAnalysis was called with no target tier");
  }
  return opts.targetTier;
}

function draftAtTier2(): CsfAssessment {
  return {
    id: "csf-assess-385",
    status: "draft",
    version: 1,
    answers: [],
    client_target_tier: 2,
    documents_stale: false,
  } as unknown as CsfAssessment;
}

/** Shaped off the PRODUCER -- see the ZT twin for why that matters. */
function typedRefusal(status: number, reason: string, message: string): Error {
  const err = new Error("CSF proxy " + String(status)) as Error & {
    status: number;
    payload: unknown;
  };
  err.status = status;
  err.payload = {
    error: { code: status, correlation_id: "c-385", reason, message },
  };
  return err;
}

function baseMocks(): void {
  fetchCatalog.mockResolvedValue(CATALOG);
  // A REAL SHAPE, not `{}`. The workspace derives its per-subcategory prompt
  // map from `questions`, and an empty object made that derivation throw --
  // so an unrelated "interview" message appeared in the shared banner and the
  // positive control below failed for a reason that had nothing to do with
  // the target. The failure was useful: it is the same banner, so a fixture
  // that quietly broke a sibling source would otherwise have weakened this
  // file's one assertion that the banner stays EMPTY.
  fetchInterviewQuestionnaire.mockResolvedValue({
    framework_key: "csf_2_0",
    profile: null,
    questions: [],
  });
  fetchLatestAssessment.mockResolvedValue(draftAtTier2());
  fetchLatestDeliverable.mockResolvedValue(null);
  fetchScore.mockResolvedValue(SCORE);
}

function renderWorkspace(serviceId: string): void {
  render(<CsfWorkspace serviceId={serviceId} serviceTitle="Atlas CSF" />);
}

/** The control itself, found the way a consultant finds it. */
function picker(): HTMLSelectElement {
  return screen.getByLabelText("Target tier") as HTMLSelectElement;
}

describe("CsfWorkspace reverts the target tier when its gap fetch fails (#385)", () => {
  it("keeps the new target, and shows its rows, when the fetch succeeds", async () => {
    // THE POSITIVE HALF. A handler that reverted unconditionally would
    // satisfy every failure assertion below.
    baseMocks();
    fetchGapAnalysis.mockImplementation(async (_id, opts) =>
      gapAt(requestedTier(opts)),
    );

    renderWorkspace("svc-385-csf-ok");

    await screen.findByText("rows-computed-for-tier-2");
    await act(async () => {
      fireEvent.change(picker(), { target: { value: "4" } });
    });

    expect(picker()).toHaveValue("4");
    expect(screen.getByText("rows-computed-for-tier-4")).toBeInTheDocument();
    expect(screen.queryByText("rows-computed-for-tier-2")).toBeNull();
    expect(screen.queryByTestId("csf-refresh-error")).toBeNull();
  });

  it("reverts the control to the target whose rows are still on screen", async () => {
    // THE DEFECT, stated as the pairing it produced: tier 4 in the control,
    // tier 2's rows underneath it, and nothing saying so.
    baseMocks();
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      if (requestedTier(opts) === 4) throw new TypeError("fetch failed");
      return gapAt(requestedTier(opts));
    });

    renderWorkspace("svc-385-csf-revert");

    await screen.findByText("rows-computed-for-tier-2");
    await act(async () => {
      fireEvent.change(picker(), { target: { value: "4" } });
    });

    // ASSERT WHAT MUST APPEAR BEFORE WHAT MUST NOT.
    const note = await screen.findByTestId("csf-refresh-error");

    expect(picker()).toHaveValue("2");
    expect(screen.getByText("rows-computed-for-tier-2")).toBeInTheDocument();
    expect(screen.queryByText("rows-computed-for-tier-4")).toBeNull();

    expect(note.textContent).toMatch(/unchanged/i);
    expect(note.textContent).not.toContain("fetch failed");
  });

  it("puts the server's own refusal on screen beside the revert", async () => {
    baseMocks();
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      if (requestedTier(opts) === 4) {
        throw typedRefusal(
          422,
          "target_tier_out_of_range",
          "target_tier=4 is not selectable for this assessment.",
        );
      }
      return gapAt(requestedTier(opts));
    });

    renderWorkspace("svc-385-csf-typed");

    await screen.findByText("rows-computed-for-tier-2");
    await act(async () => {
      fireEvent.change(picker(), { target: { value: "4" } });
    });

    const note = await screen.findByTestId("csf-refresh-error");
    expect(note.textContent).toContain(
      "target_tier=4 is not selectable for this assessment.",
    );
    expect(note.textContent).toMatch(/unchanged/i);
    expect(note.textContent).not.toContain("CSF proxy");
    expect(picker()).toHaveValue("2");
  });

  it("does not revert past a later change that already succeeded", async () => {
    // 2 -> 3 (rejects LAST) -> 4 (resolves FIRST). The tier-3 attempt
    // captured `previous = 2`; unguarded, its rejection pulls the control
    // back to 2 under tier 4's rows. `attempt.superseded()` refuses it, and
    // this test is the only thing pinning that check.
    baseMocks();
    let reject3: (err: unknown) => void = () => {};
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      if (requestedTier(opts) === 3) {
        return new Promise<GapAnalysis>((_res, rej) => {
          reject3 = rej;
        });
      }
      return gapAt(requestedTier(opts));
    });

    renderWorkspace("svc-385-csf-superseded");

    await screen.findByText("rows-computed-for-tier-2");
    await act(async () => {
      fireEvent.change(picker(), { target: { value: "3" } });
    });
    await act(async () => {
      fireEvent.change(picker(), { target: { value: "4" } });
    });
    await screen.findByText("rows-computed-for-tier-4");

    await act(async () => {
      reject3(new TypeError("fetch failed"));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(picker()).toHaveValue("4");
    expect(screen.getByText("rows-computed-for-tier-4")).toBeInTheDocument();
    expect(screen.queryByTestId("csf-refresh-error")).toBeNull();
  });
});
