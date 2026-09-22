import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import * as ztClient from "@/lib/zt/client";
import type {
  GapAnalysis,
  ZtAssessment,
  ZtCatalog,
  ZtScoreSummary,
} from "@/lib/zt/types";

import { ZtWorkspace } from "./ZtWorkspace";

/**
 * #385 -- THE CONTROL SHOWS THE TARGET ITS ROWS WERE COMPUTED FOR.
 *
 * `onChangeTargetStage` set the label and awaited the gap fetch with no
 * catch, so a rejection left the PREVIOUS target's rows under the NEW
 * target's heading.
 *
 * ## These cells come from a truth table, not from the fix
 *
 * The first attempt at this fix REMEMBERED the control's previous value and
 * wrote it back. It passed a version of this file that enumerated exactly one
 * cell -- the later fetch SUCCEEDS -- and three independent adversarial
 * reviews then found four interleavings where a remembered label names a
 * target no rows were ever fetched for. `CLAUDE.md`: a matrix written after a
 * fix only pins the fix.
 *
 * So the cells below are written against the RULING -- "the control reads the
 * target of the rows beneath it whenever nothing is pending" -- and the two
 * the old fix failed are marked where they sit.
 *
 * ## Why this is a separate file from `ZtWorkspace.test.tsx`
 *
 * That file stubs `ZtGapList` to null. The control under test IS in
 * `ZtGapList` -- a `<select>` labelled "Target stage" -- so it is rendered for
 * real here. `CLAUDE.md`: drive the surface the consultant reaches, never
 * import the handler. Because that `<select>` is CONTROLLED
 * (`value={shownTarget}`), `toHaveValue(...)` can only pass if the derivation
 * produced that value.
 *
 * The CSF twin is `csf/CsfWorkspace.target-revert.test.tsx`.
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
  patchAnswer: vi.fn(),
  runZtAi: vi.fn(),
  finalizeZtDeliverable: vi.fn(),
  releaseZtDeliverable: vi.fn(),
}));

vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: "ready", stages: null }),
}));

// EVERY CHILD BUT `ZtGapList` IS STUBBED. That one is the surface under test
// and is rendered for real; stubbing it would leave these tests driving a
// control that does not exist, which passes by selecting nothing.
vi.mock("./ZtScoreCard", () => ({ ZtScoreCard: () => null }));
vi.mock("./ZtRoadmapCard", () => ({ ZtRoadmapCard: () => null }));
vi.mock("./ZtQuestionnaire", () => ({ ZtQuestionnaire: () => null }));
vi.mock("./ZtDeliverableCard", () => ({ ZtDeliverableCard: () => null }));
vi.mock("./ZtRunAiAccounting", () => ({
  ZtRunAiAccounting: () => null,
  lostValueCount: () => 0,
}));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));
// Rendered as a pass-through so `onRunAi` is reachable from the surface. The
// real guard fetches an AI status of its own; that decision is `RunAiGuard`'s
// own tests' business, and stubbing it is what makes the invariant test below
// able to fire `refreshScoreAndGap` the way a consultant does.
vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: ({
    onProceed,
    children,
  }: {
    onProceed: () => void;
    children: (p: { onClick: () => void }) => React.ReactNode;
  }) => children({ onClick: onProceed }),
}));
vi.mock("@/components/admin/AiPreviewButton", () => ({
  AiPreviewButton: () => null,
}));

const fetchCatalog = vi.mocked(ztClient.fetchCatalog);
const fetchLatestAssessment = vi.mocked(ztClient.fetchLatestAssessment);
const fetchLatestDeliverable = vi.mocked(ztClient.fetchLatestDeliverable);
const fetchScore = vi.mocked(ztClient.fetchScore);
const fetchGapAnalysis = vi.mocked(ztClient.fetchGapAnalysis);

const CATALOG = {
  pillars: [],
  stages: [
    { stage: 1, label: "Traditional" },
    { stage: 2, label: "Initial" },
    { stage: 3, label: "Advanced" },
    { stage: 4, label: "Optimal" },
  ],
} as unknown as ZtCatalog;

const SCORE = {} as unknown as ZtScoreSummary;

/**
 * Rows that NAME their own target.
 *
 * `target_stage` is what the component derives the control from, and the row
 * name is what a human reads, so a disagreeing cell is visible in both.
 */
function gapAt(stage: number): GapAnalysis {
  return {
    assessment_id: "zt-assess-385",
    version: 1,
    framework: "dod_ztra",
    target_stage: stage,
    target_label: `stage-${stage}`,
    total_gap_count: 1,
    unscored_count: 0,
    gap_count_by_pillar: {},
    gaps: [
      {
        code: "ZT-1",
        pillar_name: "Identity",
        name: `rows-computed-for-stage-${stage}`,
        outcome: "an outcome",
        notes: null,
        current_stage: 1,
        target_stage: stage,
        gap_size: stage - 1,
        priority_score: 1,
      },
    ],
  } as unknown as GapAnalysis;
}

/**
 * The stage a call asked for, or a loud failure.
 *
 * `fetchGapAnalysis`'s options are optional all the way down, so a mock
 * annotated with a required target is not assignable; and one that DEFAULTED
 * a missing target would answer a question the workspace never asked.
 */
function requestedStage(opts?: { targetStage?: number }): number {
  if (opts?.targetStage === undefined) {
    throw new Error("fetchGapAnalysis was called with no target stage");
  }
  return opts.targetStage;
}

function draftAtStage2(): ZtAssessment {
  return {
    id: "zt-assess-385",
    status: "draft",
    version: 1,
    answers: [],
    client_target_stage: 2,
    documents_stale: false,
  } as unknown as ZtAssessment;
}

/**
 * A rejection shaped like the one `lib/zt/client.ts` throws.
 *
 * Copied off the PRODUCER: `routes/zt.py` raises `HTTPException(422,
 * detail={"reason": ..., "message": ...})`, `_handle_http_exception` rewraps
 * it into the `{error: {...}}` envelope, and the proxy class keeps the
 * payload while putting its own internal label in `Error.message`. A fixture
 * written to suit `serverReason` could not catch that label leaking.
 */
function typedRefusal(status: number, reason: string, message: string): Error {
  const err = new Error("ZT proxy " + String(status)) as Error & {
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
 * A promise the test settles by hand, carrying a TAP that proves it
 * propagated.
 *
 * The component attaches its `await` handler before the test awaits `settled`,
 * so once `settled` has resolved the component's own `try`/`catch` has already
 * run. Without this, a test whose expected end state equals the state BEFORE
 * the settle passes just as well when the settle never propagated -- which is
 * precisely what the previous version of this file did (adversarial finding
 * 4b), and its green was indistinguishable from an unflushed rejection.
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

function baseMocks(): void {
  fetchCatalog.mockResolvedValue(CATALOG);
  fetchLatestAssessment.mockResolvedValue(draftAtStage2());
  fetchLatestDeliverable.mockResolvedValue(null);
  fetchScore.mockResolvedValue(SCORE);
}

function renderWorkspace(serviceId: string): void {
  render(
    <ZtWorkspace
      serviceId={serviceId}
      framework="dod_ztra"
      serviceTitle="Atlas Zero Trust"
    />,
  );
}

/** The control itself, found the way a consultant finds it. */
function picker(): HTMLSelectElement {
  return screen.getByLabelText("Target stage") as HTMLSelectElement;
}

async function pick(value: string): Promise<void> {
  await act(async () => {
    fireEvent.change(picker(), { target: { value } });
  });
}

describe("ZtWorkspace target stage is derived from the rows (#385)", () => {
  it("keeps the new target, and shows its rows, when the fetch succeeds", async () => {
    // THE POSITIVE HALF. Without it, a handler that never let the target move
    // would satisfy every failure cell below.
    baseMocks();
    fetchGapAnalysis.mockImplementation(async (_id, opts) =>
      gapAt(requestedStage(opts)),
    );

    renderWorkspace("svc-385-zt-ok");

    await screen.findByText("rows-computed-for-stage-2");
    await pick("4");

    expect(picker()).toHaveValue("4");
    expect(screen.getByText("rows-computed-for-stage-4")).toBeInTheDocument();
    expect(screen.queryByText("rows-computed-for-stage-2")).toBeNull();
    expect(screen.queryByTestId("zt-refresh-error")).toBeNull();
  });

  it("falls back to the rows' own target when the fetch fails", async () => {
    // CELL: A fails, B absent. The control must read what the rows read.
    baseMocks();
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      if (requestedStage(opts) === 4) throw new TypeError("fetch failed");
      return gapAt(requestedStage(opts));
    });

    renderWorkspace("svc-385-zt-revert");

    await screen.findByText("rows-computed-for-stage-2");
    await pick("4");

    // ASSERT WHAT MUST APPEAR BEFORE WHAT MUST NOT: the banner proves the
    // rejection was handled, so what follows is not read off a page that is
    // still mid-fetch.
    const note = await screen.findByTestId("zt-refresh-error");

    expect(picker()).toHaveValue("2");
    expect(screen.getByText("rows-computed-for-stage-2")).toBeInTheDocument();
    expect(screen.queryByText("rows-computed-for-stage-4")).toBeNull();

    // THE COPY CLAIMS ONLY WHAT THE DERIVATION GUARANTEES, and its remedy is
    // a control that works. It used to say "unchanged" -- false in the
    // two-picker cell below -- and "Reload to try again", but a reload
    // re-reads `client_target_stage` and so retries a DIFFERENT target.
    expect(note.textContent).toMatch(/gone back to the stage/i);
    expect(note.textContent).toMatch(/pick a stage again/i);
    expect(note.textContent).not.toMatch(/unchanged/i);
    expect(note.textContent).not.toMatch(/reload/i);
    expect(note.textContent).not.toContain("fetch failed");
  });

  it("reverts to the ROWS' target, not to the control's previous value", async () => {
    // THE CELL THE FIRST FIX FAILED, and the reason this file has this shape.
    // 2 -> pick 3 (slow) -> pick 4 -> 4 FAILS -> 3 resolves late.
    //
    // A remembered `previous` is 3 here, because the control had already
    // committed to 3, so reverting to it puts the selector on a stage whose
    // rows were never rendered. The rows are still stage 2's, so 2 is the
    // only honest answer.
    baseMocks();
    const slow3 = deferredGap();
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      const t = requestedStage(opts);
      if (t === 3) return slow3.promise;
      if (t === 4) throw new TypeError("fetch failed");
      return gapAt(t);
    });

    renderWorkspace("svc-385-zt-two-picks");

    await screen.findByText("rows-computed-for-stage-2");
    await pick("3");
    await pick("4");

    const note = await screen.findByTestId("zt-refresh-error");

    // 3 never landed and 4 failed, so the rows are still stage 2's.
    expect(picker()).toHaveValue("2");
    expect(screen.getByText("rows-computed-for-stage-2")).toBeInTheDocument();
    expect(note.textContent).toMatch(/gone back to the stage/i);

    // And the late stage-3 response must not resurrect stage 3 either.
    await act(async () => {
      slow3.resolve(gapAt(3));
      expect(await slow3.settled).toBe("resolved");
    });
    expect(picker()).toHaveValue("2");
    expect(screen.queryByText("rows-computed-for-stage-3")).toBeNull();
  });

  it("does not land a superseded attempt's rows when that attempt SUCCEEDS", async () => {
    // THE SUCCESS-SIDE GUARD. The previous version of this file only ever
    // REJECTED the superseded promise, so the guard above `setGap` could be
    // deleted with every test still green (adversarial finding 4a). Here the
    // stale attempt RESOLVES.
    //
    // 2 -> pick 3 (slow, will succeed) -> pick 4 (succeeds) -> 3 resolves.
    // Stage 3's rows must never appear under a control reading 4.
    baseMocks();
    const slow3 = deferredGap();
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      const t = requestedStage(opts);
      if (t === 3) return slow3.promise;
      return gapAt(t);
    });

    renderWorkspace("svc-385-zt-superseded-success");

    await screen.findByText("rows-computed-for-stage-2");
    await pick("3");
    await pick("4");
    await screen.findByText("rows-computed-for-stage-4");

    await act(async () => {
      slow3.resolve(gapAt(3));
      // PROOF THE RESOLUTION PROPAGATED. Without it the expected end state is
      // byte-identical to the state before the promise was released.
      expect(await slow3.settled).toBe("resolved");
    });

    expect(picker()).toHaveValue("4");
    expect(screen.getByText("rows-computed-for-stage-4")).toBeInTheDocument();
    expect(screen.queryByText("rows-computed-for-stage-3")).toBeNull();
    expect(screen.queryByTestId("zt-refresh-error")).toBeNull();
  });

  it("does not revert past a later change that already succeeded", async () => {
    // THE MIRROR. 2 -> pick 3 (slow, will REJECT) -> pick 4 (succeeds).
    // The stale rejection must write nothing at all.
    baseMocks();
    const slow3 = deferredGap();
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      const t = requestedStage(opts);
      if (t === 3) return slow3.promise;
      return gapAt(t);
    });

    renderWorkspace("svc-385-zt-superseded");

    await screen.findByText("rows-computed-for-stage-2");
    await pick("3");
    await pick("4");
    await screen.findByText("rows-computed-for-stage-4");

    await act(async () => {
      slow3.reject(new TypeError("fetch failed"));
      expect(await slow3.settled).toBe("rejected");
    });

    expect(picker()).toHaveValue("4");
    expect(screen.getByText("rows-computed-for-stage-4")).toBeInTheDocument();
    // A superseded attempt writes NOTHING -- not the control, and not a
    // message about a target the consultant has already moved off.
    expect(screen.queryByTestId("zt-refresh-error")).toBeNull();
  });

  it("puts the framework's own refusal on screen beside the fallback", async () => {
    // The typed 422 names the framework AND the offending value -- the one
    // thing that tells a consultant why the selector moved back.
    baseMocks();
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      if (requestedStage(opts) === 4) {
        throw typedRefusal(
          422,
          "target_stage_out_of_range",
          "dod_ztra has stages 1-3; target_stage=4 is not one of them.",
        );
      }
      return gapAt(requestedStage(opts));
    });

    renderWorkspace("svc-385-zt-typed");

    await screen.findByText("rows-computed-for-stage-2");
    await pick("4");

    const note = await screen.findByTestId("zt-refresh-error");
    expect(note.textContent).toContain(
      "dod_ztra has stages 1-3; target_stage=4 is not one of them.",
    );
    expect(note.textContent).toMatch(/gone back to the stage/i);
    // Never the internal label the proxy class puts in its own `message`.
    expect(note.textContent).not.toContain("ZT proxy");
    expect(picker()).toHaveValue("2");
  });

  it("keeps the control on the rows' target when a stale refresh relabels them", async () => {
    // THE CELL THAT MAKES `gap?.target_stage` LOAD-BEARING, and it was found
    // by mutation rather than by reading: deleting that term from the
    // derivation left the entire suite green, which is the #72 shape inside
    // the fix for #385.
    //
    // It defends a LIVE path. `refreshScoreAndGap`'s success branch writes
    // `setGap(...)` WITHOUT a supersession guard (an adversarial finding, and
    // a pre-existing site), so a slow refresh can land rows for an older
    // target after a newer target's rows are already on screen. Deriving the
    // control from the rows means that write moves the LABEL WITH the data --
    // correct-but-stale rather than mislabelled, which is the whole ruling.
    //
    // Sequence: Run AI refreshes for the current target (2) and hangs; the
    // consultant picks 4 and it succeeds; the stale stage-2 response then
    // lands through the unguarded write.
    baseMocks();
    const stale2 = deferredGap();
    let stage2Calls = 0;
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      const t = requestedStage(opts);
      if (t === 2) {
        stage2Calls += 1;
        // The first stage-2 fetch is `initialLoad`'s and must land, or there
        // are no rows to relabel. The second is the Run-AI refresh.
        if (stage2Calls > 1) return stale2.promise;
      }
      return gapAt(t);
    });
    vi.mocked(ztClient.runZtAi).mockResolvedValue(
      {} as unknown as Awaited<ReturnType<typeof ztClient.runZtAi>>,
    );

    renderWorkspace("svc-385-zt-stale-refresh");
    await screen.findByText("rows-computed-for-stage-2");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run AI" }));
    });
    // The refresh's gap fetch is now in flight for stage 2.
    expect(stage2Calls).toBeGreaterThan(1);

    await pick("4");
    await screen.findByText("rows-computed-for-stage-4");

    await act(async () => {
      stale2.resolve(gapAt(2));
      expect(await stale2.settled).toBe("resolved");
    });

    // THE INVARIANT, asserted as a relationship rather than as two constants:
    // whatever rows are on screen, the control names THEIR target.
    expect(screen.getByText("rows-computed-for-stage-2")).toBeInTheDocument();
    expect(screen.queryByText("rows-computed-for-stage-4")).toBeNull();
    expect(picker()).toHaveValue("2");
  });

  it("refreshes the target that is ON SCREEN, not the one its closure began with", async () => {
    // WHAT `shownTargetRef` IS FOR, pinned rather than asserted in a comment.
    //
    // `onRunAi` and `onAnswerUpdate` both await before they refresh, so the
    // target they closed over belongs to the render the action STARTED in.
    // Passing that refetches the old target and, since the control is derived
    // from the rows, drags the selector back down with it -- silently undoing
    // a selection the consultant made while the action was in flight.
    //
    // Here the pick is still PENDING when Run AI fires, so the committed
    // `targetStage` is still 2 while the screen shows 4. Reading the ref is
    // the only way to refresh 4.
    baseMocks();
    const slow4 = deferredGap();
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      const t = requestedStage(opts);
      if (t === 4) return slow4.promise;
      return gapAt(t);
    });
    vi.mocked(ztClient.runZtAi).mockResolvedValue(
      {} as unknown as Awaited<ReturnType<typeof ztClient.runZtAi>>,
    );

    renderWorkspace("svc-385-zt-live-ref");
    await screen.findByText("rows-computed-for-stage-2");

    await pick("4");
    // The pick is in flight: the control shows 4, nothing is committed yet.
    expect(picker()).toHaveValue("4");

    fetchGapAnalysis.mockClear();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run AI" }));
    });

    const refreshed = fetchGapAnalysis.mock.calls.map(([, opts]) =>
      requestedStage(opts),
    );
    expect(refreshed.length).toBeGreaterThan(0);
    expect(refreshed).not.toContain(2);
    expect(refreshed).toContain(4);

    await act(async () => {
      slow4.resolve(gapAt(4));
      expect(await slow4.settled).toBe("resolved");
    });
  });
});
