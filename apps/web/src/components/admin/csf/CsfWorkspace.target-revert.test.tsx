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
 * #385 -- THE CONTROL SHOWS THE TARGET ITS ROWS WERE COMPUTED FOR.
 *
 * The ZT twin, `zt/ZtWorkspace.target-revert.test.tsx`, carries the reasoning
 * and the truth table these cells come from. In brief: the first fix
 * REMEMBERED the control's previous value and wrote it back on failure, which
 * names a tier no rows were ever fetched for; the control is now derived from
 * the rendered rows instead.
 *
 * Separate from `CsfWorkspace.test.tsx` because that file stubs `CsfGapList`
 * to null, and the control under test -- a `<select>` labelled "Target tier"
 * -- lives inside it. That select is CONTROLLED, so `toHaveValue(...)` can
 * only pass if the derivation produced the value.
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
// NOT `() => null`. CSF has no Run-AI control to drive `refreshScoreAndGap`
// from, so the questionnaire stub exposes the REAL `onAnswerUpdate` prop
// behind a button. That is the surface a consultant uses to trigger a
// refresh, and the invariant test below needs one.
vi.mock("./CsfQuestionnaire", () => ({
  CsfQuestionnaire: ({
    onAnswerUpdate,
  }: {
    onAnswerUpdate: (id: string, patch: unknown) => void;
  }) => (
    <button
      type="button"
      onClick={() => onAnswerUpdate("answer-1", { maturity_tier: 2 })}
    >
      edit an answer
    </button>
  ),
}));
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

/** Rows that NAME their own target, so a disagreeing cell is visible. */
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

/**
 * A promise the test settles by hand, with a TAP proving it propagated.
 * Without it, an end state equal to the state BEFORE the settle passes even
 * when the settle never reached the component (adversarial finding 4b).
 */
function deferredGap(): {
  promise: Promise<GapAnalysis>;
  settled: Promise<string>;
  resolve: (g: GapAnalysis) => void;
  reject: (e: unknown) => void;
} {
  let resolve!: (g: GapAnalysis) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<GapAnalysis>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  const settled = promise.then(
    () => "resolved",
    () => "rejected",
  );
  return { promise, settled, resolve, reject };
}

/** The same tap, for the ACTION a refresh hangs off (`patchAnswer`). */
function deferredRun(): {
  promise: Promise<unknown>;
  settled: Promise<string>;
  resolve: (v: unknown) => void;
} {
  let resolve!: (v: unknown) => void;
  const promise = new Promise<unknown>((res) => {
    resolve = res;
  });
  const settled = promise.then(
    () => "resolved",
    () => "rejected",
  );
  return { promise, settled, resolve };
}

function baseMocks(): void {
  fetchCatalog.mockResolvedValue(CATALOG);
  // A REAL SHAPE, not `{}`. The workspace derives its per-subcategory prompt
  // map from `questions`, and an empty object made that derivation throw --
  // putting an unrelated "interview" message in the SHARED banner, which is
  // the element these tests assert is empty.
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

async function pick(value: string): Promise<void> {
  await act(async () => {
    fireEvent.change(picker(), { target: { value } });
  });
}

describe("CsfWorkspace target tier is derived from the rows (#385)", () => {
  it("keeps the new target, and shows its rows, when the fetch succeeds", async () => {
    // THE POSITIVE HALF. A handler that never let the tier move would satisfy
    // every failure cell below.
    baseMocks();
    fetchGapAnalysis.mockImplementation(async (_id, opts) =>
      gapAt(requestedTier(opts)),
    );

    renderWorkspace("svc-385-csf-ok");

    await screen.findByText("rows-computed-for-tier-2");
    await pick("4");

    expect(picker()).toHaveValue("4");
    expect(screen.getByText("rows-computed-for-tier-4")).toBeInTheDocument();
    expect(screen.queryByText("rows-computed-for-tier-2")).toBeNull();
    expect(screen.queryByTestId("csf-refresh-error")).toBeNull();
  });

  it("falls back to the rows' own target when the fetch fails", async () => {
    baseMocks();
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      if (requestedTier(opts) === 4) throw new TypeError("fetch failed");
      return gapAt(requestedTier(opts));
    });

    renderWorkspace("svc-385-csf-revert");

    await screen.findByText("rows-computed-for-tier-2");
    await pick("4");

    const note = await screen.findByTestId("csf-refresh-error");

    expect(picker()).toHaveValue("2");
    expect(screen.getByText("rows-computed-for-tier-2")).toBeInTheDocument();
    expect(screen.queryByText("rows-computed-for-tier-4")).toBeNull();

    // Claims only what is true in every cell -- see the ZT twin.
    expect(note.textContent).toMatch(/target tier 4/i);
    expect(note.textContent).toMatch(/pick a tier again/i);
    expect(note.textContent).not.toMatch(/gone back/i);
    expect(note.textContent).not.toMatch(/unchanged/i);
    expect(note.textContent).not.toMatch(/reload/i);
    expect(note.textContent).not.toContain("fetch failed");
  });

  it("reverts to the ROWS' target, not to the control's previous value", async () => {
    // THE CELL THE FIRST FIX FAILED. 2 -> pick 3 (slow) -> pick 4 -> 4 fails.
    // A remembered `previous` is 3, a tier whose rows were never rendered.
    baseMocks();
    const slow3 = deferredGap();
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      const t = requestedTier(opts);
      if (t === 3) return slow3.promise;
      if (t === 4) throw new TypeError("fetch failed");
      return gapAt(t);
    });

    renderWorkspace("svc-385-csf-two-picks");

    await screen.findByText("rows-computed-for-tier-2");
    await pick("3");
    await pick("4");

    const note = await screen.findByTestId("csf-refresh-error");

    expect(picker()).toHaveValue("2");
    expect(screen.getByText("rows-computed-for-tier-2")).toBeInTheDocument();
    expect(note.textContent).toMatch(/target tier 4/i);

    await act(async () => {
      slow3.resolve(gapAt(3));
      expect(await slow3.settled).toBe("resolved");
    });
    expect(picker()).toHaveValue("2");
    expect(screen.queryByText("rows-computed-for-tier-3")).toBeNull();
  });

  it("does not land a superseded attempt's rows when that attempt SUCCEEDS", async () => {
    // THE SUCCESS-SIDE GUARD (adversarial finding 4a): the previous version
    // only ever REJECTED the superseded promise, so the guard above `setGap`
    // was deletable with the suite green.
    baseMocks();
    const slow3 = deferredGap();
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      const t = requestedTier(opts);
      if (t === 3) return slow3.promise;
      return gapAt(t);
    });

    renderWorkspace("svc-385-csf-superseded-success");

    await screen.findByText("rows-computed-for-tier-2");
    await pick("3");
    await pick("4");
    await screen.findByText("rows-computed-for-tier-4");

    await act(async () => {
      slow3.resolve(gapAt(3));
      expect(await slow3.settled).toBe("resolved");
    });

    expect(picker()).toHaveValue("4");
    expect(screen.getByText("rows-computed-for-tier-4")).toBeInTheDocument();
    expect(screen.queryByText("rows-computed-for-tier-3")).toBeNull();
    expect(screen.queryByTestId("csf-refresh-error")).toBeNull();
  });

  it("does not revert past a later change that already succeeded", async () => {
    baseMocks();
    const slow3 = deferredGap();
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      const t = requestedTier(opts);
      if (t === 3) return slow3.promise;
      return gapAt(t);
    });

    renderWorkspace("svc-385-csf-superseded");

    await screen.findByText("rows-computed-for-tier-2");
    await pick("3");
    await pick("4");
    await screen.findByText("rows-computed-for-tier-4");

    await act(async () => {
      slow3.reject(new TypeError("fetch failed"));
      expect(await slow3.settled).toBe("rejected");
    });

    expect(picker()).toHaveValue("4");
    expect(screen.getByText("rows-computed-for-tier-4")).toBeInTheDocument();
    expect(screen.queryByTestId("csf-refresh-error")).toBeNull();
  });

  it("puts the server's own refusal on screen beside the fallback", async () => {
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
    await pick("4");

    const note = await screen.findByTestId("csf-refresh-error");
    expect(note.textContent).toContain(
      "target_tier=4 is not selectable for this assessment.",
    );
    expect(note.textContent).toMatch(/target tier 4/i);
    expect(note.textContent).not.toContain("CSF proxy");
    expect(picker()).toHaveValue("2");
  });

  it("discards a stale refresh rather than letting it relabel the rows", async () => {
    // `gapWriteSeq`. See the ZT twin: an unguarded stale success used to
    // relabel the rows, and once the control was derived from them it
    // discarded the consultant's tier selection in silence instead. The stale
    // write no longer lands.
    baseMocks();
    const stale2 = deferredGap();
    let tier2Calls = 0;
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      const t = requestedTier(opts);
      if (t === 2) {
        tier2Calls += 1;
        // The first tier-2 fetch is `initialLoad`'s and must land, or there
        // are no rows to relabel. The second is the answer-edit refresh.
        if (tier2Calls > 1) return stale2.promise;
      }
      return gapAt(t);
    });
    vi.mocked(csfClient.patchAnswer).mockResolvedValue(
      {} as unknown as Awaited<ReturnType<typeof csfClient.patchAnswer>>,
    );

    renderWorkspace("svc-385-csf-stale-refresh");
    await screen.findByText("rows-computed-for-tier-2");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "edit an answer" }));
    });
    expect(tier2Calls).toBeGreaterThan(1);

    await pick("4");
    await screen.findByText("rows-computed-for-tier-4");

    await act(async () => {
      stale2.resolve(gapAt(2));
      expect(await stale2.settled).toBe("resolved");
    });

    // The consultant's selection SURVIVES, and the invariant still holds.
    expect(screen.getByText("rows-computed-for-tier-4")).toBeInTheDocument();
    expect(screen.queryByText("rows-computed-for-tier-2")).toBeNull();
    expect(picker()).toHaveValue("4");
  });

  it("refreshes the target that is ON SCREEN, not the one its closure began with", async () => {
    // ACTION FIRST, pick while it is in flight -- the order the ref exists
    // for. The first version of this test picked first, so the closure and
    // the ref agreed and it discriminated nothing (see the ZT twin).
    baseMocks();
    const slowPatch = deferredRun();
    fetchGapAnalysis.mockImplementation(async (_id, opts) =>
      gapAt(requestedTier(opts)),
    );
    vi.mocked(csfClient.patchAnswer).mockImplementation(
      () => slowPatch.promise as never,
    );

    renderWorkspace("svc-385-csf-live-ref");
    await screen.findByText("rows-computed-for-tier-2");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "edit an answer" }));
    });

    await pick("4");
    await screen.findByText("rows-computed-for-tier-4");

    fetchGapAnalysis.mockClear();
    await act(async () => {
      slowPatch.resolve({});
      expect(await slowPatch.settled).toBe("resolved");
    });

    const refreshed = fetchGapAnalysis.mock.calls.map(([, opts]) =>
      requestedTier(opts),
    );
    expect(refreshed.length).toBeGreaterThan(0);
    expect(refreshed).toContain(4);
    expect(refreshed).not.toContain(2);
  });
});
