import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
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
 * #385 -- A FAILED GAP FETCH REVERTS THE CONTROL. The label follows the data;
 * the data is never relabelled.
 *
 * `onChangeTargetStage` set the label first and awaited the gap fetch with no
 * catch, so a rejection left the PREVIOUS target's rows on screen under the
 * NEW target's heading -- a number the consultant never asked for, presented
 * as one they did.
 *
 * ## Why this is a separate file from `ZtWorkspace.test.tsx`
 *
 * That file stubs `ZtGapList` to null, deliberately, so a child's failure
 * cannot be mistaken for its banner assertions passing. The control under
 * test here IS in `ZtGapList` -- a `<select>` labelled "Target stage" -- so
 * these tests need it rendered for real. `CLAUDE.md`: test through the
 * surface the consultant reaches, never by importing the handler. A test that
 * called `onChangeTargetStage` directly would prove the function reverts a
 * variable and say nothing about what is on screen.
 *
 * The CSF twin is `csf/CsfWorkspace.target-revert.test.tsx`, duplicated
 * rather than shared for the reason the existing pair already gives: separate
 * components, separate clients, separate copy, and a shared helper would hide
 * the divergence the twin-sweep rule exists to catch.
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

/** The stage a row's name carries is what makes label-versus-data readable. */
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
 * `fetchGapAnalysis`'s options are OPTIONAL all the way down --
 * `opts?: { targetStage?: number }` -- so a mock annotated with a required
 * target is not assignable to it, and one that defaulted a missing target
 * would answer a question the workspace never asked. Reading it through here
 * keeps the mock assignable AND turns "called with no target" into a
 * failure instead of a plausible row.
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
 * Copied off the PRODUCER: `routes/zt.py` raises an `HTTPException(422,
 * detail={"reason": ..., "message": ...})` and `_handle_http_exception`
 * rewraps it into the `{error: {...}}` envelope, while the proxy class keeps
 * the payload and puts its own internal label in `message`. A fixture written
 * to suit `serverReason` would agree with a broken reader by construction.
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

describe("ZtWorkspace reverts the target stage when its gap fetch fails (#385)", () => {
  it("keeps the new target, and shows its rows, when the fetch succeeds", async () => {
    // THE POSITIVE HALF. Without it, a handler that reverted unconditionally
    // -- never letting the target change at all -- would satisfy every
    // failure assertion below. `CLAUDE.md`: test both halves of the branch
    // you changed.
    baseMocks();
    fetchGapAnalysis.mockImplementation(async (_id, opts) =>
      gapAt(requestedStage(opts)),
    );

    renderWorkspace("svc-385-zt-ok");

    await screen.findByText("rows-computed-for-stage-2");
    await act(async () => {
      fireEvent.change(picker(), { target: { value: "4" } });
    });

    expect(picker()).toHaveValue("4");
    expect(screen.getByText("rows-computed-for-stage-4")).toBeInTheDocument();
    expect(screen.queryByText("rows-computed-for-stage-2")).toBeNull();
    expect(screen.queryByTestId("zt-refresh-error")).toBeNull();
  });

  it("reverts the control to the target whose rows are still on screen", async () => {
    // THE DEFECT, stated as the pairing it produced: stage 4 in the control,
    // stage 2's rows underneath it, and nothing saying so.
    baseMocks();
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      if (requestedStage(opts) === 4) throw new TypeError("fetch failed");
      return gapAt(requestedStage(opts));
    });

    renderWorkspace("svc-385-zt-revert");

    await screen.findByText("rows-computed-for-stage-2");
    await act(async () => {
      fireEvent.change(picker(), { target: { value: "4" } });
    });

    // ASSERT WHAT MUST APPEAR BEFORE WHAT MUST NOT: the banner is the proof
    // the rejection has been handled, so the two assertions after it are not
    // reading a page that is still mid-fetch.
    const note = await screen.findByTestId("zt-refresh-error");

    // THE REVERT. This is the line that goes red with `setTargetStage(previous)`
    // removed, and it is the whole of the owner's ruling: the control follows
    // the data rather than the data being relabelled.
    expect(picker()).toHaveValue("2");
    expect(screen.getByText("rows-computed-for-stage-2")).toBeInTheDocument();
    expect(screen.queryByText("rows-computed-for-stage-4")).toBeNull();

    // A CONTROL THAT SNAPS BACK IN SILENCE READS AS A MISCLICK. The message
    // names the observable fact, and never the caught value's own text.
    expect(note.textContent).toMatch(/unchanged/i);
    expect(note.textContent).not.toContain("fetch failed");
  });

  it("puts the framework's own refusal on screen beside the revert", async () => {
    // The typed 422 names the framework AND the offending value -- the one
    // thing that tells a consultant why the control moved back. A generic
    // fallback that discarded it would still pass the test above.
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
    await act(async () => {
      fireEvent.change(picker(), { target: { value: "4" } });
    });

    const note = await screen.findByTestId("zt-refresh-error");
    expect(note.textContent).toContain(
      "dod_ztra has stages 1-3; target_stage=4 is not one of them.",
    );
    expect(note.textContent).toMatch(/unchanged/i);
    // Never the internal label the proxy class puts in its own `message`.
    expect(note.textContent).not.toContain("ZT proxy");
    expect(picker()).toHaveValue("2");
  });

  it("does not revert past a later change that already succeeded", async () => {
    // 2 -> 3 (rejects LAST) -> 4 (resolves FIRST).
    //
    // The stage-3 attempt captured `previous = 2`. Unguarded, its rejection
    // pulls the control back to 2 while stage 4's rows are on screen -- the
    // same mislabelling the fix exists to stop, arrived at from the other
    // direction. `attempt.superseded()` is what refuses it, and this test is
    // the only thing pinning that check.
    baseMocks();
    let reject3: (err: unknown) => void = () => {};
    fetchGapAnalysis.mockImplementation(async (_id, opts) => {
      if (requestedStage(opts) === 3) {
        return new Promise<GapAnalysis>((_res, rej) => {
          reject3 = rej;
        });
      }
      return gapAt(requestedStage(opts));
    });

    renderWorkspace("svc-385-zt-superseded");

    await screen.findByText("rows-computed-for-stage-2");
    await act(async () => {
      fireEvent.change(picker(), { target: { value: "3" } });
    });
    await act(async () => {
      fireEvent.change(picker(), { target: { value: "4" } });
    });
    // Stage 4 has landed BEFORE the stale rejection is released, which is the
    // ordering this test is about.
    await screen.findByText("rows-computed-for-stage-4");

    await act(async () => {
      reject3(new TypeError("fetch failed"));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(picker()).toHaveValue("4");
    expect(screen.getByText("rows-computed-for-stage-4")).toBeInTheDocument();
    // The superseded attempt writes NOTHING -- not the control, not a message
    // about a target the consultant has already moved off.
    expect(screen.queryByTestId("zt-refresh-error")).toBeNull();
  });
});
