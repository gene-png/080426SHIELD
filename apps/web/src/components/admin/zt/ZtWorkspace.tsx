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
  const [targetStage, setTargetStage] = React.useState(3);

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
        setGap(gapOutcome.value);
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
      await refreshScoreAndGap(targetStage);
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
   * This handler used to set the label first and then await the gap fetch
   * with no catch at all. On a rejection the PREVIOUS target's rows stayed on
   * screen under the NEW target's heading -- a number the consultant never
   * asked for, presented as one they did, with nothing on screen saying so.
   *
   * The card's job is to show gap rows FOR A TARGET. If rows for the new
   * target cannot be fetched, the honest screen is the old target with its
   * own rows, so the CONTROL reverts. Marking the card stale was considered
   * and REJECTED: it leaves the heading wrong, which is the defect rather
   * than a disclosure of it.
   *
   * `CLAUDE.md`: prefer a derivation over a synchronization. Reverting makes
   * the label follow the data instead of being kept in step with it.
   *
   * ## Why the revert needs the token, and why it is the SAME source key
   *
   * `beginRefresh("gap")` is minted above the await, per `useRefreshFailures`
   * -- a token minted below one is ordered by when that await RESOLVED, which
   * inverts the guard.
   *
   * `superseded()` is checked around `setGap` and `setTargetStage` because
   * neither goes through the token. Without it, two quick changes 3 -> 4 -> 5
   * where the 4 fetch fails after the 5 fetch succeeds would revert the
   * control to 3 while the 5 rows are on screen -- the same mislabelling,
   * arrived at from the other direction.
   *
   * The key is the gap panel's own, not a new one, so an ordinary
   * `refreshScoreAndGap` that lands afterwards clears this message once the
   * panel is fresh again. A second key would need clearing alongside it,
   * which is the single-slot defect `useRefreshFailures` records.
   *
   * ## The reverting is not silent
   *
   * A control that snaps back on its own reads as a misclick. The server's
   * own sentence is preferred where there is one -- `/gap-analysis` answers a
   * typed 422 naming the framework and the offending value -- and either way
   * the message states that the target is unchanged, because that is the
   * thing the consultant just watched happen.
   */
  async function onChangeTargetStage(next: number): Promise<void> {
    const previous = targetStage;
    setTargetStage(next);
    if (!assessment) return;
    const attempt = beginRefresh("gap");
    try {
      const g = await fetchGapAnalysis(serviceId, { targetStage: next });
      if (attempt.superseded()) return; // a later target owns the rows
      setGap(g);
      attempt.clear();
    } catch (err) {
      if (attempt.superseded()) return; // a later target owns the control
      setTargetStage(previous);
      const reason = serverReason(err);
      attempt.note(
        reason
          ? `${reason} The target stage is unchanged.`
          : "Couldn't load gap rows for that target stage, so the target stage is unchanged. Reload to try again.",
      );
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
      await refreshScoreAndGap(targetStage);
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
            targetStage={targetStage}
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
