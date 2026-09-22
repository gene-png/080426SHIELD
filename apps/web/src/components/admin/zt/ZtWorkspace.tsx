"use client";
import * as React from "react";

import {
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  StatusPill,
} from "@shield/design-system";

import {
  approveAssessment,
  createAssessment,
  discardAssessment,
  fetchCatalog,
  fetchGapAnalysis,
  fetchLatestAssessment,
  fetchLatestDeliverable,
  fetchScore,
  patchAnswer,
  runZtAi,
  ZtProxyError,
} from "@/lib/zt/client";
import type {
  GapAnalysis,
  ZtAnswer,
  ZtAnswerPatch,
  ZtAssessment,
  CatalogStage,
  ZtCatalog,
  ZtDeliverable,
  ZtFramework,
  ZtRunAiResponse,
  ZtScoreSummary,
} from "@/lib/zt/types";

import { MessageThread } from "@/components/messages/MessageThread";
import { StaleDocsNudge } from "@/components/admin/StaleDocsNudge";
import { WorkflowStep } from "@/components/admin/WorkflowStep";
import { AiPreviewButton } from "@/components/admin/AiPreviewButton";
import { DiscardDraftButton } from "@/components/admin/DiscardDraftButton";
import { RunAiGuard } from "@/components/admin/RunAiGuard";
import { AiDraftProvenanceNotice } from "@/components/admin/AiDraftProvenanceNotice";

import { ZtDeliverableCard } from "./ZtDeliverableCard";
import { lostValueCount, ZtRunAiAccounting } from "./ZtRunAiAccounting";
import { ZtGapList } from "./ZtGapList";
import { ZtRoadmapCard } from "./ZtRoadmapCard";
import { ZtQuestionnaire } from "./ZtQuestionnaire";
import { ZtScoreCard } from "./ZtScoreCard";

import type { JSX } from "react";
import { ProgressStages } from "../ProgressStages";
import { useServiceStages } from "@/lib/stages/client";
import { useRefreshFailures } from "@/components/admin/useRefreshFailures";
import { serverReason } from "@/lib/describe-save-error";
import { MIN_TARGET_STAGE } from "@/lib/assessment-targets";

export interface ZtWorkspaceProps {
  serviceId: string;
  framework: ZtFramework;
  serviceTitle: string;
}

/** Mirrors `DEFAULT_TARGET_STAGE` in `app/zt/scoring.py`; valid on both ladders. */
const DEFAULT_TARGET_STAGE = 3;

/**
 * Clamp a stored target stage to one THIS FRAMEWORK actually has.
 *
 * Framework-blindness here was a live defect, not a theoretical one. This
 * returned the stored value for any of 2, 3 or 4 regardless of framework, and
 * DoD ZTRA has three stages while intake still offers a fourth -- so a stored 4
 * on a DoD engagement is reachable through the product's own wizard and is
 * exactly the population #125 is about.
 *
 * It stopped being survivable when `analyze_gaps` began REFUSING an
 * out-of-range target instead of clamping it: `/gap-analysis` now answers a
 * typed 422 where the same request used to return 200 with a clamped gap set.
 *
 * **THE REST OF THIS PARAGRAPH DESCRIBED A STATE THAT NO LONGER EXISTS, and
 * it is corrected rather than deleted because it is where someone debugging
 * this would look.** It read that `refreshScoreAndGap` "runs both fetches
 * under one `Promise.all` whose rejection is swallowed -- so asking for a
 * stage the framework lacks blanks the gap card AND the score card", and that
 * "the consultant sees two empty cards, is told nothing". Two separate fixes
 * have since landed underneath it and neither updated the sentence:
 *
 *   - `3933c46` (#292/#379) replaced the swallowing `catch` with a recorded
 *     note, so the consultant IS told. "Whose rejection is swallowed" expired
 *     there and survived as a sentence telling the next reader the branch was
 *     still silent -- a precondition that expired, sitting exactly where it
 *     would be checked.
 *   - #185 replaced the `Promise.all` with `allSettled` keyed per panel, so a
 *     gap refusal no longer blanks the score card, which never depended on the
 *     target stage.
 *
 * What remains TRUE, and is the reason this clamp still matters: a target the
 * framework lacks costs the consultant the gap panel, and the typed 422's own
 * sentence is now what they read -- recoverable only through a dropdown that
 * never offered the stored value in the first place. Normalising here is what
 * stops the request being made at all.
 *
 * `stages` is the framework's own ladder, fetched from the catalog the target
 * dropdown is already built from. **That covers the LADDER and not the FLOOR,
 * and the sentence here used to claim both** -- it read "so this cannot drift
 * from what the UI offers", full stop, which is a scope wider than its own
 * argument supports (#194).
 *
 * The ladder genuinely cannot drift: it is the same catalog the dropdown is
 * built from. The floor is a separate, hand-written product rule, and it was
 * spelled as a bare `2` at three sibling filters while only this function
 * named it. Raise the picker's floor without the constant and this returns a
 * stage the dropdown no longer offers -- a controlled `<select>` with
 * `selectedIndex = -1`, which renders blank with no error at all. Both halves
 * now come from `MIN_TARGET_STAGE` in `@/lib/assessment-targets`, so the
 * claim is true of the floor because it has one home rather than because
 * nobody has changed it yet.
 *
 * When the ladder is unavailable, fall back to the engine default rather than
 * trusting the stored value: asking for a stage that cannot be checked is the
 * case that just cost two cards.
 */
export function normalizeTarget(
  value: number | null | undefined,
  stages: readonly CatalogStage[] | null | undefined,
): number {
  const selectable = (stages ?? [])
    .map((s) => s.stage)
    .filter((s) => s >= MIN_TARGET_STAGE)
    .sort((a, b) => a - b);
  if (selectable.length === 0) return DEFAULT_TARGET_STAGE;
  if (typeof value === "number" && selectable.includes(value)) return value;
  return selectable.includes(DEFAULT_TARGET_STAGE)
    ? DEFAULT_TARGET_STAGE
    : selectable[selectable.length - 1];
}

function describeError(err: unknown): string {
  if (err instanceof ZtProxyError) {
    const payload = err.payload as
      { error?: { message?: string }; detail?: string } | undefined;
    return (
      payload?.error?.message ??
      payload?.detail ??
      `Request failed (${err.status}).`
    );
  }
  return err instanceof Error ? err.message : "Request failed.";
}

const FRAMEWORK_NAME: Record<ZtFramework, string> = {
  cisa_ztmm_2_0: "CISA ZTMM 2.0",
  dod_ztra: "DoD ZT Reference Architecture",
};

export function ZtWorkspace({
  serviceId,
  framework,
  serviceTitle,
}: ZtWorkspaceProps): JSX.Element {
  const [catalog, setCatalog] = React.useState<ZtCatalog | null>(null);
  const [assessment, setAssessment] = React.useState<ZtAssessment | null>(null);
  // Derived six-stage progress. Re-reads when this workspace's own
  // state moves, since the derivation is computed from that same state.
  const { phase: stagesPhase, stages: serviceStages } = useServiceStages(
    serviceId,
    `${assessment?.status ?? ""}:${assessment?.version ?? ""}`,
  );
  const [score, setScore] = React.useState<ZtScoreSummary | null>(null);
  const [gap, setGap] = React.useState<GapAnalysis | null>(null);
  const [deliverable, setDeliverable] = React.useState<ZtDeliverable | null>(
    null,
  );
  const [loadError, setLoadError] = React.useState<string | null>(null);
  /**
   * SUPPLEMENTARY fetches that failed, keyed by source (#292). Distinct from
   * `loadError`: that one blocks and says the workspace could not load; these
   * are side panels that failed while the workspace itself is fine.
   *
   * `null` was doing two jobs. The panels are `T | null`, and a bare
   * `} catch {}` left them null on failure -- byte-identical to
   * still-loading. `CLAUDE.md`: a value that is `null` for BOTH "still
   * loading" and "request failed" makes its callers conflate the two.
   *
   * Keyed rather than a single string because one slot was wrong in two
   * opposite directions; see `useRefreshFailures`. This file had the SECOND
   * half: it never cleared at all, so one transient failure pinned a
   * permanent "may be out of date" warning over figures that had since
   * refreshed correctly.
   */
  const { messages: refreshMessages, begin: beginRefresh } =
    useRefreshFailures();
  const [busy, setBusy] = React.useState<
    "create" | "approve" | "run" | "discard" | null
  >(null);
  const [runResult, setRunResult] = React.useState<ZtRunAiResponse | null>(
    null,
  );
  /**
   * THE TARGET THE CONTROL SHOWS IS DERIVED, NOT REMEMBERED (#385).
   *
   * Three pieces, and only the third is ever rendered:
   *
   *   `targetStage`    the COMMITTED target -- what `initialLoad`, create and
   *                    discard put here from the assessment. Never written by
   *                    the picker's failure path, because that path has no
   *                    value to write that is not already derivable.
   *   `pendingTarget`  the picker request currently in flight, or null.
   *   `shownTarget`    what the consultant sees, computed at render.
   *
   * The first version of this fix remembered the control's previous value and
   * wrote it back on failure. That is a SYNCHRONIZATION, and it reintroduced
   * the defect it was written to close: `previous` is the LABEL's last value,
   * so at stage 2 a pick of 3 followed by a pick of 4 captures `previous = 3`
   * -- and when 4 fails it reverts the control to 3 while the rows are still
   * stage 2's, under a message asserting nothing changed. Three independent
   * adversarial reviews found four distinct interleavings of that shape and
   * all three proposed the same remedy, which is this one.
   *
   * `CLAUDE.md`: prefer a derivation over a synchronization. A derived value
   * cannot be out of sync; a synchronized one merely is not, right now.
   */
  const [targetStage, setTargetStage] = React.useState(3);
  const [pendingTarget, setPendingTarget] = React.useState<number | null>(null);

  // Monotonic per-PICKER-REQUEST sequence, deliberately separate from the
  // `"gap"` refresh token. The refresh token orders GAP WRITES and can be
  // taken by a `refreshScoreAndGap` carrying an OLDER target -- "newest
  // token, stalest data" -- so it is the wrong thing to ask "is my request
  // still the one the consultant is waiting for".
  const targetReqSeq = React.useRef(0);

  /**
   * MONOTONIC ORDER OVER EVERY WRITE TO `gap`, whoever makes it (#385 round 2).
   *
   * `refreshScoreAndGap`'s success path wrote `setGap` unguarded, so a slow
   * refresh could land rows for an older target on top of newer ones. Before
   * the control was derived, that produced a VISIBLE mislabel. After it, the
   * label followed the stale rows down and the consultant's target selection
   * was discarded in silence, with `gapAttempt.clear()` removing the only
   * banner -- an end state byte-identical to "they picked the old target".
   *
   * That is strictly worse than the defect it came from IN THE DIMENSION THAT
   * MATTERS: the old one could be seen. A trade like that does not get made
   * in a test comment, so it is not made at all -- a stale write simply does
   * not land.
   *
   * Deliberately NOT the `"gap"` refresh token: that token is per SOURCE and
   * the picker owns a different source, so the two writers were never ordered
   * against each other. This ticket is per WRITE and every writer takes one.
   */
  const gapWriteSeq = React.useRef(0);

  /**
   * WHAT THE PICKER SHOWS. A pure function of `(pendingTarget, gap)`.
   *
   * ## The invariant, stated at the width it actually holds
   *
   *     WHEN NOTHING IS PENDING, the control shows the rows' own target.
   *
   * and no wider. An earlier draft of this comment claimed "there is no
   * window in which the label and the rows can disagree", which is FALSE:
   * the PENDING window is exactly such a window, deliberately. The consultant
   * picks 4, `pendingTarget` is 4, and the rows are still stage 2's until the
   * fetch lands.
   *
   * That overstatement is the same shape that produced #385's reincarnation
   * -- a sentence true of the cell its author was thinking about and false of
   * the one they were not -- so it is corrected rather than softened.
   *
   * With nothing pending this IS `gap.target_stage`, so at rest the control
   * cannot name a target the rows were not computed for. A failed change
   * "reverts" by `pendingTarget` being withdrawn; there is no revert
   * statement to get wrong.
   *
   * ## THE PENDING WINDOW IS LEFT UNMARKED, and that is a decision
   *
   * During it the screen reads new-label-over-old-rows, which is #385's own
   * shape differing only in being brief and intended. It is left unmarked
   * because the gap fetch is a single request behind a control the consultant
   * just operated, so the window is the latency of one call and a marker
   * would flicker on every pick. If that stops being true -- a slower
   * endpoint, a batched fetch -- this is the decision to revisit, and the
   * honest marker is on the ROWS ("showing stage N while stage M loads"),
   * never on the control, because relabelling the control is the defect.
   *
   * ## What `targetStage` is doing at the end of the chain
   *
   * It is the COMMITTED target, written only by `initialLoad`,
   * `onCreateAssessment` and `onDiscard` from the assessment's
   * `client_target_stage` via `normalizeTarget`. It is reached only when
   * `gap` is null -- before the first gap has ever loaded, or after a discard
   * clears it. That state IS reachable: `initialLoad`'s gap fetch can fail,
   * leaving no rows at all.
   *
   * So in that one state the control is NOT derived from rendered data, for
   * the sufficient reason that there is none. It shows what was asked for,
   * beside a gap panel that says it could not load; it does not name a target
   * some OTHER rows were computed for, which is the thing #385 is about.
   *
   * `gap` before `targetStage` on purpose: once rows exist they are the truth
   * about what is displayed, and the committed value is only the answer
   * before the first fetch lands.
   */
  const shownTarget = pendingTarget ?? gap?.target_stage ?? targetStage;

  /**
   * The live `shownTarget`, for callers that read it AFTER an await.
   *
   * It exists because `onAnswerUpdate` and `onRunAi` both await before they
   * call `refreshScoreAndGap`, so the target they closed over belongs to the
   * render the ACTION began in. Refreshing that refetches the old target, and
   * because the control is derived from the rows it drags the selector down
   * with it -- silently undoing a selection made while the action was in
   * flight.
   *
   * ## The window, named rather than implied
   *
   * Assigning this during render has NO window and is what the first version
   * did. `react-hooks/refs` rejects it outright ("Cannot access refs during
   * render") and `pnpm -F web lint` is a CI gate, so it is an effect instead
   * and the value therefore lags by ONE COMMIT: the update that closes the
   * gap is this effect, and the gap is the interval between React committing
   * a new `shownTarget` and flushing passive effects.
   *
   * What that can cost is bounded and is NOT a mislabel: a refresh starting
   * inside that interval fetches the target that was correct one commit ago,
   * and the derivation then moves the label to match whatever rows arrive.
   * The #385 invariant is held by `shownTarget` itself, which is computed at
   * render and has no window at all; this ref only decides which target a
   * background refresh asks for.
   */
  const shownTargetRef = React.useRef(shownTarget);
  React.useEffect(() => {
    shownTargetRef.current = shownTarget;
  }, [shownTarget]);

  // Monotonic request sequence: only the newest assessment-producing operation
  // may write `assessment`. Without this, a slow mount-time load resolving
  // AFTER the user starts an assessment, edits an answer, or runs the AI would
  // setAssessment(stale) and clobber the newer state (the T8 stale-fetch race).
  // Every mutation bumps the sequence before it writes, so any in-flight load
  // is discarded on arrival.
  const assessmentSeq = React.useRef(0);

  const answersByCode = React.useMemo(() => {
    const out: Record<string, ZtAnswer> = {};
    if (assessment) {
      for (const a of assessment.answers) {
        out[a.capability_code] = a;
      }
    }
    return out;
  }, [assessment]);

  const refreshScoreAndGap = React.useCallback(
    async (currentTarget: number) => {
      // ONE SOURCE KEY PER PANEL, minted before any await.
      //
      // NON-BLOCKING IS NOT SILENT (#292): a panel's own loading state cannot
      // be told apart from a slow network, so a failure is recorded rather
      // than swallowed. That half is settled.
      //
      // What is new here is that the two fetches are no longer COUPLED (#185).
      // They ran under one `Promise.all` keyed on one source, so a gap
      // rejection discarded the maturity score's GOOD RESULT -- and the score
      // does not depend on the target stage at all. `allSettled` gives each
      // outcome its own branch; two keys let one panel clear while the other
      // reports.
      //
      // The mint-before-await rule is `useRefreshFailures`' own: a token minted
      // below an await is ordered by when that await RESOLVED, which inverts
      // the guard. Both are minted here, above `allSettled`.
      const scoreAttempt = beginRefresh("score");
      const gapAttempt = beginRefresh("gap");
      const gapWrite = ++gapWriteSeq.current;
      const [scoreOutcome, gapOutcome] = await Promise.allSettled([
        fetchScore(serviceId),
        fetchGapAnalysis(serviceId, { targetStage: currentTarget }),
      ]);

      if (scoreOutcome.status === "fulfilled") {
        setScore(scoreOutcome.value);
        scoreAttempt.clear();
      } else {
        scoreAttempt.note(
          serverReason(scoreOutcome.reason) ??
            "Couldn't refresh the maturity panel. The figures shown may be out of date; reload to try again.",
        );
      }

      // THE SERVER'S OWN SENTENCE WHERE THERE IS ONE. `/gap-analysis` answers
      // a typed 422 for a target the framework lacks -- "dod_ztra has stages
      // 1-3; target_stage=4 is not one of them." -- and that precision (#125)
      // was being replaced by a fixed generic, so the consultant was told the
      // panel was stale without being told the one thing that would fix it.
      // That sentence names the framework AND the offending value; the generic
      // named neither.
      //
      // `serverReason` never returns `err.message`: the proxy class discards
      // its reason into `ZT proxy <status>` and keeps the real payload, so
      // reading the envelope is the only way to get client-usable copy.
      //
      // A schema-level 422 would ride the internal "Request validation
      // failed." here, and this route deliberately does NOT use
      // `Query(ge=, le=)` bounds -- it refuses with a typed reason instead --
      // so an integer from `normalizeTarget` cannot produce one.
      if (gapOutcome.status === "fulfilled") {
        // A STALE SUCCESS IS DISCARDED, not written. See `gapWriteSeq`.
        if (gapWrite === gapWriteSeq.current) setGap(gapOutcome.value);
        gapAttempt.clear();
      } else {
        gapAttempt.note(
          serverReason(gapOutcome.reason) ??
            "Couldn't refresh the gap panel. The figures shown may be out of date; reload to try again.",
        );
      }
    },
    [serviceId, beginRefresh],
  );

  const initialLoad = React.useCallback(async () => {
    const seq = ++assessmentSeq.current;
    // EVERY token this function will use is minted HERE, before any await.
    // See `useRefreshFailures`: mint below an await and the tokens are ordered
    // by RESOLUTION, so an initialLoad started FIRST whose earlier fetch is
    // slow issues the LATER token and overwrites a newer load's record.
    //
    // The `seq` early-return below does NOT close this. It narrows the window:
    // a load that PASSES that check can still be overtaken while it awaits
    // `refreshScoreAndGap`, and would then mint after the newer load did.
    const deliverableAttempt = beginRefresh("deliverable");
    let cat: ZtCatalog;
    try {
      cat = await fetchCatalog(framework);
      setCatalog(cat);
    } catch (err) {
      setLoadError(describeError(err));
      return;
    }
    try {
      const a = await fetchLatestAssessment(serviceId);
      if (seq !== assessmentSeq.current) {
        console.debug(
          `[ZtWorkspace] discarded stale assessment load (seq ${seq}, latest ${assessmentSeq.current})`,
        );
        return;
      }
      setAssessment(a);
      if (a) {
        // Default the gap target to the client's chosen stage (set at intake).
        // `cat`, not the `catalog` state: setCatalog has not re-rendered yet.
        const t = normalizeTarget(a.client_target_stage, cat.stages);
        setTargetStage(t);
        await refreshScoreAndGap(t);
        try {
          const d = await fetchLatestDeliverable(serviceId);
          setDeliverable(d);
          deliverableAttempt.clear();
        } catch {
          // A FALSE NEGATIVE, not a stale panel, and the first version of this
          // fix gave it the generic "part of this workspace" message -- a
          // half-fix, because `ZtDeliverableCard` renders "Not finalized yet"
          // exactly as its CSF and Tech Debt twins do. That is a claim ABOUT
          // THE SERVER made on the strength of a request that failed, and a
          // consultant can act on it by finalizing a second time.
          //
          // Missing data defaults to UNCONFIRMED, never to a known negative.
          deliverableAttempt.note(
            "Couldn't check for a finalized deliverable. The deliverable card below is not a statement about whether one exists.",
          );
        }
      }
    } catch (err) {
      setLoadError(describeError(err));
    }
  }, [serviceId, framework, refreshScoreAndGap, beginRefresh]);

  React.useEffect(() => {
    void (async () => {
      await initialLoad();
    })();
  }, [initialLoad]);

  async function onCreateAssessment(): Promise<void> {
    setBusy("create");
    assessmentSeq.current += 1;
    try {
      const next = await createAssessment(serviceId);
      setAssessment(next);
      const t = normalizeTarget(next.client_target_stage, catalog?.stages);
      setTargetStage(t);
      await refreshScoreAndGap(t);
    } catch (err) {
      setLoadError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  async function onAnswerUpdate(
    answerId: string,
    patch: ZtAnswerPatch,
  ): Promise<void> {
    // Optimistic update. The bump invalidates any in-flight load so its late
    // arrival cannot clobber this edit.
    assessmentSeq.current += 1;
    setAssessment((curr) => {
      if (!curr) return curr;
      return {
        ...curr,
        answers: curr.answers.map((a) =>
          a.id === answerId ? { ...a, ...patch } : a,
        ),
      };
    });
    try {
      const next = await patchAnswer(answerId, patch);
      setAssessment((curr) => {
        if (!curr) return curr;
        return {
          ...curr,
          answers: curr.answers.map((a) => (a.id === answerId ? next : a)),
        };
      });
      await refreshScoreAndGap(shownTargetRef.current);
    } catch (err) {
      setLoadError(describeError(err));
      // Roll back by re-fetching, guarded so a newer edit still wins.
      const seq = ++assessmentSeq.current;
      const a = await fetchLatestAssessment(serviceId);
      if (seq === assessmentSeq.current) setAssessment(a);
    }
  }

  async function onApprove(): Promise<void> {
    if (!assessment) return;
    setBusy("approve");
    assessmentSeq.current += 1;
    try {
      const next = await approveAssessment(assessment.id);
      setAssessment(next);
    } catch (err) {
      setLoadError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  async function onDiscard(): Promise<void> {
    if (!assessment) return;
    setBusy("discard");
    const seq = ++assessmentSeq.current;
    try {
      await discardAssessment(assessment.id);
      // Refetch latest, guarded: any in-flight load holding the pre-discard
      // draft is discarded on arrival. 404 → null (empty state, Start live
      // again) or the prior approved version.
      const a = await fetchLatestAssessment(serviceId);
      if (seq === assessmentSeq.current) {
        setAssessment(a);
        if (a) {
          const t = normalizeTarget(a.client_target_stage, catalog?.stages);
          setTargetStage(t);
          await refreshScoreAndGap(t);
        } else {
          setScore(null);
          setGap(null);
          setDeliverable(null);
        }
      }
    } catch (err) {
      setLoadError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  /**
   * THE LABEL FOLLOWS THE DATA. THE DATA IS NEVER RELABELLED (#385).
   *
   * This handler used to set the label and await the gap fetch with no catch,
   * so a rejection left the PREVIOUS target's rows under the NEW target's
   * heading. The ruling is that the CONTROL gives way: if rows for the new
   * target cannot be fetched, the honest screen is the old target with its
   * own rows. Marking the card stale was considered and REJECTED -- it leaves
   * the heading wrong, which is the defect rather than a disclosure of it.
   *
   * ## The truth table, written before this logic and not after it
   *
   * `A` is this attempt, for `next`. `B` is any other gap write in flight --
   * `refreshScoreAndGap(t_B)` from an answer edit, a Run-AI or a discard,
   * where `t_B` is whatever THAT call site closed over and may be the OLD
   * target with a NEWER token. Cells are (control, rows) at rest:
   *
   *   |                | B absent | B(next) ok | B(base) ok   | B fails |
   *   | A succeeds     | next,next| next,next  | next,base *  | next,next|
   *   | A fails        | base,base| next,next  | base,base    | base,base|
   *   | A pending      | pending  | next,next  | pending,base | pending  |
   *
   * and the two-picker sequences the first version of this fix got wrong:
   *
   *   base 2, pick 3 (slow), pick 4, 4 FAILS   -> must rest at (2, 2)
   *   base 2, pick 3, pick 4, BOTH fail        -> must rest at (2, 2)
   *   base 2, pick 3 (slow ok), pick 4 (ok)    -> must rest at (4, 4)
   *
   * Every cell is satisfied by the derivation above rather than by a branch
   * here, which is the point: `shownTarget` with nothing pending IS
   * `gap.target_stage`, so no RESTING cell can disagree -- the pending row is
   * a genuine disagreement and is the optimistic UI. The starred cell
   * degrades to (base, base) -- a stale refresh moves the label WITH its
   * rows, correct-but-stale instead of mislabelled.
   *
   * ## Why the gap token is not the guard
   *
   * `beginRefresh("gap")` orders GAP WRITES. It cannot answer "is my request
   * still the one being waited on", because `refreshScoreAndGap` mints the
   * same key for a different target. Gating the revert on it let an ordinary
   * answer edit suppress both the revert and its message. So the picker gets
   * `targetReqSeq` for its own ordering, and `"gap-target"` for its own
   * message -- a source `refreshScoreAndGap` never mints, so it cannot be
   * swallowed. It is self-clearing: the next picker attempt supersedes it.
   *
   * ## The copy claims only what the derivation guarantees
   *
   * It used to say "The target stage is unchanged", which the 2 -> 3 -> 4
   * cell makes false. And its remedy was "Reload to try again" -- but
   * `initialLoad` re-reads `client_target_stage`, so a reload retries the
   * ASSESSMENT's target, never the one that failed (the D-076 shape: a
   * user-facing string must name a control that works today). Picking the
   * stage again does retry it.
   */
  async function onChangeTargetStage(next: number): Promise<void> {
    const mine = ++targetReqSeq.current;
    setPendingTarget(next);
    if (!assessment) {
      // No rows exist, so nothing can be mislabelled and nothing is fetched.
      // The committed value is the only thing `shownTarget` can fall back to.
      setTargetStage(next);
      setPendingTarget(null);
      return;
    }
    // NOTHING BETWEEN `setPendingTarget` AND THE `try` MAY THROW. Both
    // statements below are a ref bump and an object construction, so neither
    // can -- and that is load-bearing rather than incidental: a throw here
    // skips the `finally`, and `pendingTarget` then sticks on a target whose
    // fetch is gone, with no message and no way back except another pick.
    // Flagged by review while this window held one statement; it now holds
    // two, so it is written down rather than re-derived.
    const attempt = beginRefresh("gap-target");
    const gapWrite = ++gapWriteSeq.current;
    try {
      const g = await fetchGapAnalysis(serviceId, { targetStage: next });
      // ONE GUARD, NOT TWO. A `mine !== targetReqSeq.current` return sat
      // above this and red-on-revert could not kill it: every newer pick
      // bumps BOTH sequences, and a newer refresh bumps this one, so the
      // ticket below already refuses everything the other refused. Deleted
      // rather than kept as decoration -- the same unpinned-conditional shape
      // this branch has now produced twice.
      if (gapWrite !== gapWriteSeq.current) return; // a newer gap write won
      // NOTHING COMMITS `targetStage` HERE, and that is the point. After a
      // successful pick the ONLY thing carrying the new target is `gap`, so
      // `shownTarget` reads it from the rows rather than from a second copy
      // that could disagree with them.
      setGap(g);
      attempt.clear();
    } catch (err) {
      // NO SEQUENCE CHECK HERE, and its absence is measured rather than
      // assumed. A `mine !== targetReqSeq.current` return sat here and
      // red-on-revert could not kill it: the only write in this branch is
      // `attempt.note`, and `useRefreshFailures` already makes that a no-op
      // once a later attempt on the same source has begun. An unpinned
      // conditional that duplicates a guard one layer down is the shape this
      // repo keeps finding, so it is deleted rather than left as decoration.
      // The `finally` below DOES check, because `setPendingTarget` is state
      // the token knows nothing about.
      // THE MESSAGE CLAIMS NOTHING ABOUT THE SCREEN. It used to say the
      // selector "has gone back to the stage these gap rows were computed
      // for", which the truth table's own `A fails / B(next) succeeds` cell
      // makes FALSE: a concurrent refresh can land the new target's rows
      // while this request fails, leaving the selector on `next` under a
      // warning saying it went back. What is true in every cell is that THIS
      // REQUEST failed, so that is all it says.
      const reason = serverReason(err);
      attempt.note(
        reason
          ? `${reason} Target stage ${next} could not be loaded; pick a stage again to retry.`
          : `Couldn't load gap rows for target stage ${next}. Pick a stage again to retry.`,
      );
    } finally {
      // WITHDRAWING THE PENDING VALUE *IS* THE REVERT. `shownTarget` falls
      // back to the rows' own target the moment this clears, on the success
      // path too (where `setGap` has already made them agree).
      if (mine === targetReqSeq.current) setPendingTarget(null);
    }
  }

  async function onRunAi(): Promise<void> {
    setBusy("run");
    // LOAD-BEARING for accessibility, not just for clearing the panel.
    // This unmounts the accounting subtree, so the next render creates the
    // live region fresh. `ZtRunAiAccounting`'s headline switches between
    // role="alert" and aria-live="polite"; swapping that attribute on a
    // PERSISTENT node is the least reliable live-region transition there is.
    // Keeping the panel mounted across a re-run would silently break the
    // announcement without breaking a single test.
    setRunResult(null);
    const seq = ++assessmentSeq.current;
    try {
      const result = await runZtAi(serviceId);
      setRunResult(result);
      // Re-pull so the questionnaire + score reflect the AI's suggestions,
      // guarded so a concurrent edit that started meanwhile still wins.
      const a = await fetchLatestAssessment(serviceId);
      if (seq === assessmentSeq.current) setAssessment(a);
      await refreshScoreAndGap(shownTargetRef.current);
    } catch (err) {
      setLoadError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  const readOnly =
    assessment?.status === "approved" || assessment?.status === "released";

  const answeredCount =
    assessment?.answers.filter(
      (a) =>
        a.maturity_stage !== null ||
        a.notes !== null ||
        a.evidence_artifact_id !== null,
    ).length ?? 0;
  const discardSummary = `${answeredCount} answer${
    answeredCount === 1 ? "" : "s"
  }, including client-entered data, will be discarded.`;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">
            {FRAMEWORK_NAME[framework]}
          </p>
          <h1 className="text-3xl font-semibold text-ink-primary">
            {serviceTitle}
          </h1>
          <p className="max-w-prose text-sm text-ink-secondary">
            Score each capability against the 4-stage maturity model. Coverage +
            per-pillar rollup update on every edit; prioritized remediation gaps
            surface alongside the score.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {assessment ? (
            <StatusPill
              tone={
                assessment.status === "approved" ||
                assessment.status === "released"
                  ? "success"
                  : assessment.status === "submitted"
                    ? "warning"
                    : "info"
              }
              withDot
            >
              {assessment.status === "draft"
                ? `Draft v${assessment.version}`
                : assessment.status === "submitted"
                  ? `Submitted v${assessment.version}`
                  : assessment.status === "approved"
                    ? `Approved v${assessment.version}`
                    : `Released v${assessment.version}`}
            </StatusPill>
          ) : (
            <StatusPill tone="neutral" withDot>
              No assessment yet
            </StatusPill>
          )}
          {assessment ? null : (
            <button
              type="button"
              onClick={() => void onCreateAssessment()}
              disabled={busy !== null || !catalog}
              className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy === "create" ? "Creating…" : "Start assessment"}
            </button>
          )}
          {assessment ? (
            <DiscardDraftButton
              status={assessment.status}
              destructionSummary={discardSummary}
              onConfirm={onDiscard}
              disabled={busy !== null}
            />
          ) : null}
        </div>
      </header>

      {stagesPhase === "ready" && serviceStages ? (
        <ProgressStages
          stages={serviceStages.stages}
          kind={serviceStages.kind}
          version={serviceStages.version}
        />
      ) : null}

      {assessment?.status === "submitted" ? (
        <div className="rounded-md border border-status-warning-border bg-status-warning-bg px-4 py-3 text-sm text-status-warning-fg">
          <span className="font-semibold">
            Client self-assessment submitted.
          </span>{" "}
          Review and edit their answers below for completeness and accuracy,
          then <span className="font-medium">Approve client inputs</span> and
          send for evaluation in the deliverable section.
        </div>
      ) : null}

      {refreshMessages.length > 0 ? (
        <div
          className="space-y-2 rounded-md border border-status-warning-border bg-status-warning-bg p-3 text-sm text-status-warning-fg"
          role="status"
          data-testid="zt-refresh-error"
        >
          {refreshMessages.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      ) : null}

      {loadError ? (
        <Card>
          <CardHeader>
            <CardTitle>Couldn&apos;t load the assessment</CardTitle>
          </CardHeader>
          <CardBody>
            <p className="text-sm text-status-danger-fg" role="alert">
              {loadError}
            </p>
          </CardBody>
        </Card>
      ) : null}

      {!catalog ? (
        <p className="text-sm text-ink-tertiary" aria-live="polite">
          Loading catalog…
        </p>
      ) : !assessment ? (
        <EmptyState
          title="No Zero Trust assessment yet"
          description="Click 'Start assessment' to create a fresh v1 with one empty answer per capability."
        />
      ) : (
        <>
          {/* Ordered the way the work is done. This page used to run Run AI ->
              score -> messages -> gaps -> roadmap -> deliverable ->
              QUESTIONNAIRE, so the capability review — the actual work — sat at
              the very bottom, below the deliverable. Analysis output (score,
              gaps, roadmap) and the message thread are reference and now sit
              after the numbered path. */}
          <WorkflowStep
            number={1}
            title="Draft the maturity scoring with AI"
            description="Claude suggests a current and target maturity stage for each capability on this framework's scale. It drafts; you decide. An offline run leaves alone locked rows, and any answer the AI did not write — a client submission, or one still in progress. It does NOT leave alone an unlocked row the AI wrote: that row stays AI-owned even after you correct it, so running offline again can redraft your correction. A live run may draft over any unlocked row, and shows you the diff."
            // Not `runResult !== null`: a run that applied NOTHING put a green
            // success badge and a "— done" heading directly above "AI applied 0
            // of 74". The step is complete when the AI actually drafted
            // something, not merely when a request returned.
            // This rule has now been wrong in three different ways, so it is
            // written as the three conditions it actually needs rather than as
            // whichever disjunct fixed the last bug:
            //
            //   1. a run happened at all;
            //   2. the response carried suggestions — `received === 0` is a
            //      wholly-lost response, and because every drop path also
            //      increments `received`, `dropped` is then necessarily empty,
            //      so a "nothing was lost" test passes vacuously and marks the
            //      step DONE over the red "returned no suggestions at all"
            //      alert. That was round 4 re-opening round 3's defect;
            //   3. either the AI drafted something, or nothing was lost — an
            //      offline run over a fully client-submitted assessment applies
            //      nothing and preserves everything, which is success. Gating
            //      on `applied > 0` alone left Step 1 permanently un-done for
            //      that workflow, which was round 3's defect.
            done={
              runResult !== null &&
              runResult.suggestions_received > 0 &&
              (runResult.suggestions_applied > 0 ||
                lostValueCount(runResult) === 0)
            }
          >
            <div className="flex flex-col gap-3">
              {/* Issue 2: warn before producing canned output when no key is
                  loaded. The guard shipped on the ATT&CK workspace only, so a
                  fixture run here silently overwrote a real client
                  self-assessment in the 2026-08-04 review. */}
              <RunAiGuard onProceed={() => void onRunAi()}>
                {({ onClick }) => (
                  <div>
                    <button
                      type="button"
                      onClick={onClick}
                      disabled={busy !== null || readOnly}
                      className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {busy === "run" ? "Running…" : "Run AI"}
                    </button>
                  </div>
                )}
              </RunAiGuard>
              <AiPreviewButton serviceId={serviceId} disabled={busy !== null} />
              {/* Replaces the old "Updated N fields across M capabilities"
                  line, which reported only what LANDED — a run that lost every
                  suggestion rendered identically to one the model had nothing
                  to say about (W1, issue #44). The accounting states the same
                  change counts and the shortfall alongside them. */}
              {runResult ? <ZtRunAiAccounting result={runResult} /> : null}
              {/* Sibling, not a child: the accounting component's severity
                  logic stays untouched (#68). */}
              {runResult ? <AiDraftProvenanceNotice /> : null}
              {runResult?.preserved_client_answers ? (
                /* The skip must be visible, not silent. The population is every
                   answer the AI did not write — `protected_keys` keys on
                   `answer_source !== "ai"`, which also covers in-progress
                   self-assessments and rows a consultant typed, since
                   `update_answer` never writes that field. */
                <p
                  className="text-sm text-status-warning-fg"
                  aria-live="polite"
                >
                  {runResult.preserved_client_answers} answer
                  {runResult.preserved_client_answers === 1 ? "" : "s"} not
                  written by the AI — submitted, still in progress, or
                  consultant-entered —{" "}
                  {runResult.preserved_client_answers === 1 ? "was" : "were"}{" "}
                  left untouched by this offline run. Rows you also locked are
                  reported above as locked rather than preserved, so this count
                  and the skipped lines above overlap without matching. A run
                  with a real API key will draft over{" "}
                  {runResult.preserved_client_answers === 1 ? "it" : "them"} —
                  except any row you locked, which is respected in every mode.
                </p>
              ) : null}
            </div>
          </WorkflowStep>

          <WorkflowStep
            number={2}
            title="Review every capability and adjust"
            description="Work through the pillars and set the maturity stage you can defend. Where the client filled in their own self-assessment, this is where you check it for completeness and accuracy — their answers are what the report rests on."
            done={
              assessment.status !== "draft" && assessment.status !== "submitted"
            }
          >
            <ZtQuestionnaire
              catalog={catalog}
              answersByCode={answersByCode}
              readOnly={readOnly}
              onAnswerUpdate={onAnswerUpdate}
            />
          </WorkflowStep>

          <WorkflowStep
            number={3}
            title={
              assessment.status === "submitted"
                ? "Approve the client's inputs"
                : "Approve the assessment"
            }
            description="Locks the scoring so the deliverable is generated from a fixed set of answers. Approving does not send anything to the client — that is the last step."
            done={
              assessment.status === "approved" ||
              assessment.status === "released"
            }
          >
            <button
              type="button"
              onClick={() => void onApprove()}
              disabled={
                busy !== null ||
                (assessment.status !== "draft" &&
                  assessment.status !== "submitted")
              }
              className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {assessment.status === "approved"
                ? "Approved"
                : assessment.status === "released"
                  ? "Released"
                  : busy === "approve"
                    ? "Approving…"
                    : assessment.status === "submitted"
                      ? "Approve client inputs"
                      : "Approve"}
            </button>
          </WorkflowStep>

          <WorkflowStep
            number={4}
            title="Generate and release the deliverable"
            description="Renders the report from the approved assessment. Nothing reaches the client until you release it — generating is safe, releasing is the point of no return."
            blockedReason={
              assessment.status === "draft" || assessment.status === "submitted"
                ? "Approve the assessment in step 3 before generating a deliverable from it."
                : null
            }
          >
            <div className="flex flex-col gap-3">
              <StaleDocsNudge stale={assessment.documents_stale} />
              <ZtDeliverableCard
                serviceId={serviceId}
                assessmentStatus={assessment.status}
                deliverable={deliverable}
                onChange={setDeliverable}
              />
            </div>
          </WorkflowStep>

          {/* Reference, not steps: analysis output and the thread are useful
              throughout and required at no particular point. */}
          <ZtScoreCard score={score} />
          <ZtGapList
            analysis={gap}
            targetStage={shownTarget}
            onChangeTargetStage={(s) => void onChangeTargetStage(s)}
            stages={catalog.stages}
          />
          <ZtRoadmapCard analysis={gap} />
          <MessageThread serviceId={serviceId} />
        </>
      )}
    </div>
  );
}
