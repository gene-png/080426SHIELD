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
  CsfProxyError,
  discardAssessment,
  fetchCatalog,
  fetchGapAnalysis,
  fetchInterviewQuestionnaire,
  fetchLatestAssessment,
  fetchLatestDeliverable,
  fetchScore,
  patchAnswer,
} from "@/lib/csf/client";
import type {
  CsfAnswer,
  CsfAnswerPatch,
  CsfAssessment,
  CsfCatalog,
  CsfDeliverable,
  CsfInterviewQuestion,
  CsfScoreSummary,
  GapAnalysis,
} from "@/lib/csf/types";

import { MessageThread } from "@/components/messages/MessageThread";
import { StaleDocsNudge } from "@/components/admin/StaleDocsNudge";
import { WorkflowStep } from "@/components/admin/WorkflowStep";
import { DiscardDraftButton } from "@/components/admin/DiscardDraftButton";
import { useRefreshFailures } from "@/components/admin/useRefreshFailures";
import { serverReason } from "@/lib/describe-save-error";
import { MIN_TARGET_TIER } from "@/lib/assessment-targets";

import { CsfDeliverableCard } from "./CsfDeliverableCard";
import { CsfGapList } from "./CsfGapList";
import { CsfPlaybookPanel } from "./CsfPlaybookPanel";
import { CsfQuestionnaire } from "./CsfQuestionnaire";
import { CsfScoreCard } from "./CsfScoreCard";

import type { JSX } from "react";
import { ProgressStages } from "../ProgressStages";
import { useServiceStages } from "@/lib/stages/client";

export interface CsfWorkspaceProps {
  serviceId: string;
  serviceTitle: string;
}

/**
 * Clamp a stored target tier to the selectable 2-4 range; default 3.
 *
 * DELIBERATELY LEFT FRAMEWORK-BLIND, and stated so it does not read as the
 * half of a twin-fix that someone forgot.
 *
 * `ZtWorkspace.tsx`'s `normalizeTarget` was this function, character for
 * character, and it had to change: DoD ZTRA ends at Stage 3 while the ZT
 * ladder this shape assumes runs to 4, so a stored 4 on a DoD engagement
 * produced a request the API refuses and blanked two cards (#125).
 *
 * CSF has exactly one ladder and its ceiling IS 4, so no tier in 2-4 can be
 * absent here and the hardcoded range cannot currently be wrong. That is
 * safety by COINCIDENCE rather than by construction -- the same standing
 * assumption #184 records for `csf/playbook.py`'s clamp, and it expires under
 * the same condition: a CSF variant, or any second ladder, whose ceiling falls
 * below 4. Should that arrive, this function needs the ZT treatment (derive
 * the selectable set from the catalog the dropdown is built from) and #184
 * needs re-labelling on the same day.
 *
 * Not fixed pre-emptively because deriving from a catalog that has exactly one
 * shape adds a moving part with no case to answer, and an unexercised branch
 * is its own hazard.
 */
function normalizeTarget(value: number | null | undefined): number {
  // THE FLOOR COMES FROM `MIN_TARGET_TIER`; THE CEILING IS STILL HARDCODED,
  // and the asymmetry is deliberate rather than half-finished (#194).
  //
  // The floor is the same product rule the four other pickers use, so it has
  // one home. The ceiling is a property of the CSF ladder, which the docstring
  // above deliberately does not derive from the catalog -- deriving from a
  // catalog with exactly one shape adds a moving part with no case to answer.
  // That exemption is unchanged and is tracked against #184.
  //
  // Behaviour is IDENTICAL to the membership test this replaces: `Number.
  // isInteger` plus the two bounds admits exactly 2, 3 and 4, so `2.5` is
  // still refused and `3.0` still accepted. Checked against the old predicate
  // over 15 inputs including null, NaN, "3" and true.
  //
  // Written as a range because `value === 2 || value === 3 || value === 4`
  // states the floor with NO comparison operator beside a ladder noun, which is
  // why #194's sweep -- a grep for exactly that -- walked past this file while
  // wiring its ZT twin in the same commit.
  return typeof value === "number" &&
    Number.isInteger(value) &&
    value >= MIN_TARGET_TIER &&
    value <= 4
    ? value
    : 3;
}

function describeError(err: unknown): string {
  if (err instanceof CsfProxyError) {
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

export function CsfWorkspace({
  serviceId,
  serviceTitle,
}: CsfWorkspaceProps): JSX.Element {
  const [catalog, setCatalog] = React.useState<CsfCatalog | null>(null);
  const [assessment, setAssessment] = React.useState<CsfAssessment | null>(
    null,
  );
  // Derived six-stage progress. Re-reads when this workspace's own
  // state moves, since the derivation is computed from that same state.
  const { phase: stagesPhase, stages: serviceStages } = useServiceStages(
    serviceId,
    `${assessment?.status ?? ""}:${assessment?.version ?? ""}`,
  );
  const [score, setScore] = React.useState<CsfScoreSummary | null>(null);
  const [gap, setGap] = React.useState<GapAnalysis | null>(null);
  const [deliverable, setDeliverable] = React.useState<CsfDeliverable | null>(
    null,
  );
  const [loadError, setLoadError] = React.useState<string | null>(null);
  /**
   * SUPPLEMENTARY fetches that failed, keyed by source (#292). Distinct from
   * `loadError`, which renders "Couldn't load the assessment" -- a blocking
   * card that would misdescribe these: the assessment loaded, a side panel did
   * not.
   *
   * It exists because `null` was doing two jobs. `score`, `gap`, `deliverable`
   * and the interview map are all `T | null`, and a bare `} catch {}` left
   * them null on failure -- byte-identical to still-loading. `CLAUDE.md`: a
   * value that is `null` for BOTH "still loading" and "request failed" makes
   * its callers conflate the two.
   *
   * Keyed rather than a single string because a single slot was wrong in two
   * opposite directions; see `useRefreshFailures`. Here it was the eager half:
   * `initialLoad` notes a failed interview fetch and then, three statements
   * later, a SUCCESSFUL score/gap refresh cleared it.
   */
  const { messages: refreshMessages, begin: beginRefresh } =
    useRefreshFailures();
  const [busy, setBusy] = React.useState<
    "create" | "approve" | "discard" | null
  >(null);
  /**
   * THE TARGET THE CONTROL SHOWS IS DERIVED, NOT REMEMBERED (#385).
   *
   * The ZT twin, `ZtWorkspace`, carries the reasoning and the truth table in
   * full. In brief: remembering the control's previous value and writing it
   * back on failure is a synchronization, and it reintroduced #385 -- the
   * remembered value is the LABEL's, so it can name a tier no rows were ever
   * fetched for. `shownTier` is computed instead.
   */
  const [targetTier, setTargetTier] = React.useState(3);
  const [pendingTarget, setPendingTarget] = React.useState<number | null>(null);

  // Separate from the `"gap"` refresh token on purpose: that token orders gap
  // WRITES and can be taken by a `refreshScoreAndGap` carrying an older tier.
  const targetReqSeq = React.useRef(0);

  /**
   * Monotonic order over every write to `gap`, whoever makes it. The ZT twin
   * carries the reasoning: an unguarded stale success used to relabel the
   * rows, and once the control was derived from them it discarded the
   * consultant's tier selection in silence instead.
   */
  const gapWriteSeq = React.useRef(0);

  /** What the picker shows: a pure function of `(pendingTarget, gap)`. */
  const shownTier = pendingTarget ?? gap?.target_tier ?? targetTier;

  /**
   * The live `shownTier`, for callers that read it after an await --
   * `onAnswerUpdate` closes over the tier from the render its edit began in.
   *
   * An effect rather than a render-time assignment because
   * `react-hooks/refs` rejects the latter and `pnpm -F web lint` is a CI
   * gate, so this lags by one commit. The ZT twin states what that window can
   * and cannot cost; in short it cannot produce a mislabel, because the label
   * comes from `shownTier`, which is computed at render.
   */
  const shownTierRef = React.useRef(shownTier);
  React.useEffect(() => {
    shownTierRef.current = shownTier;
  }, [shownTier]);
  const [interviewByCode, setInterviewByCode] = React.useState<
    Record<string, CsfInterviewQuestion[]>
  >({});

  // Monotonic request sequence: only the newest assessment-producing operation
  // may write `assessment`. Without this, a slow mount-time load (StrictMode
  // duplicates, next-dev queuing) resolving AFTER the user starts an assessment
  // or edits an answer would setAssessment(stale) and clobber the newer state
  // (the T8 stale-fetch race). Every mutation bumps the sequence before it
  // writes, so any in-flight load is discarded on arrival.
  const assessmentSeq = React.useRef(0);

  const answersByCode = React.useMemo(() => {
    const out: Record<string, CsfAnswer> = {};
    if (assessment) {
      for (const a of assessment.answers) {
        out[a.subcategory_code] = a;
      }
    }
    return out;
  }, [assessment]);

  const refreshScoreAndGap = React.useCallback(
    async (currentTarget: number) => {
      // ONE SOURCE KEY PER PANEL, minted before any await.
      //
      // NON-BLOCKING IS NOT THE SAME AS SILENT (#292): a panel's own loading
      // state cannot be told apart from a slow network, so a failure is
      // recorded rather than swallowed. That half is settled.
      //
      // What is new here is that the two fetches are no longer COUPLED (#185).
      // They ran under one `Promise.all` keyed on one source, so a gap
      // rejection discarded the score's GOOD RESULT -- and the score does not
      // depend on the target at all. `allSettled` gives each outcome its own
      // branch; two keys let one panel clear while the other reports.
      //
      // The mint-before-await rule is `useRefreshFailures`' own: a token minted
      // below an await is ordered by when that await RESOLVED, which inverts
      // the guard. Both are minted here, above `allSettled`.
      const scoreAttempt = beginRefresh("score");
      const gapAttempt = beginRefresh("gap");
      const gapWrite = ++gapWriteSeq.current;
      const [scoreOutcome, gapOutcome] = await Promise.allSettled([
        fetchScore(serviceId),
        fetchGapAnalysis(serviceId, { targetTier: currentTarget }),
      ]);

      if (scoreOutcome.status === "fulfilled") {
        setScore(scoreOutcome.value);
        scoreAttempt.clear();
      } else {
        scoreAttempt.note(
          serverReason(scoreOutcome.reason) ??
            "Couldn't refresh the score panel. The figures shown may be out of date; reload to try again.",
        );
      }

      // THE SERVER'S OWN SENTENCE WHERE THERE IS ONE. `/gap-analysis` answers
      // a typed 422 for an out-of-range target -- "CSF 2.0 has tiers 1-4;
      // target_tier=9 is not one of them." -- and that precision (#125) was
      // being replaced by a fixed generic, so the consultant was told the
      // panel was stale without being told the one thing that would fix it.
      //
      // `serverReason` never returns `err.message`: the proxy class discards
      // its reason into `CSF proxy <status>` and keeps the real payload, so
      // reading the envelope is the only way to get client-usable copy.
      //
      // A schema-level 422 would ride the internal "Request validation
      // failed." here, and this route deliberately does NOT use
      // `Query(ge=, le=)` bounds -- it refuses with a typed reason instead --
      // so an integer from the tier picker cannot produce one.
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
    const interviewAttempt = beginRefresh("interview");
    const deliverableAttempt = beginRefresh("deliverable");
    try {
      const cat = await fetchCatalog();
      setCatalog(cat);
    } catch (err) {
      setLoadError(describeError(err));
      return;
    }
    try {
      const q = await fetchInterviewQuestionnaire(serviceId);
      if (q) {
        const map: Record<string, CsfInterviewQuestion[]> = {};
        for (const question of q.questions) {
          for (const code of question.csf_subcategories) {
            (map[code] ??= []).push(question);
          }
        }
        setInterviewByCode(map);
      }
      interviewAttempt.clear();
    } catch {
      // Supplemental, and still not silent: the prompts simply do not appear,
      // which reads as "this subcategory has none" rather than "we could not
      // fetch them".
      interviewAttempt.note(
        "Couldn't load the interview prompts. Subcategories will show none, which is not the same as having none.",
      );
    }
    try {
      const a = await fetchLatestAssessment(serviceId);
      if (seq !== assessmentSeq.current) {
        console.debug(
          `[CsfWorkspace] discarded stale assessment load (seq ${seq}, latest ${assessmentSeq.current})`,
        );
        return;
      }
      setAssessment(a);
      if (a) {
        // Default the gap target to the client's chosen tier (set at intake).
        const t = normalizeTarget(a.client_target_tier);
        setTargetTier(t);
        await refreshScoreAndGap(t);
        try {
          const d = await fetchLatestDeliverable(serviceId);
          setDeliverable(d);
          deliverableAttempt.clear();
        } catch {
          // THE SHARPEST OF THE THREE, and the old comment states the defect
          // as if it were the mitigation: "deliverable card shows 'not
          // finalized yet'". That card is then asserting a FACT ABOUT THE
          // SERVER -- that no deliverable has been finalized -- on the
          // strength of a request that failed. A consultant can act on it by
          // finalizing a second time.
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
  }, [serviceId, refreshScoreAndGap, beginRefresh]);

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
      const t = normalizeTarget(next.client_target_tier);
      setTargetTier(t);
      await refreshScoreAndGap(t);
    } catch (err) {
      setLoadError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  async function onAnswerUpdate(
    answerId: string,
    patch: CsfAnswerPatch,
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
      // Re-fetch derived data; cheap.
      await refreshScoreAndGap(shownTierRef.current);
    } catch (err) {
      setLoadError(describeError(err));
      // Roll back by re-fetching authoritative answers, guarded so a newer
      // edit that started meanwhile still wins.
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
          const t = normalizeTarget(a.client_target_tier);
          setTargetTier(t);
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
   * The ZT twin, `ZtWorkspace.onChangeTargetStage`, carries the truth table
   * and the full reasoning; this is the same shape over tiers. The revert is
   * `pendingTarget` being withdrawn, so `shownTier` falls back to the tier
   * the rendered rows were computed for -- there is no revert statement that
   * could name a different one.
   *
   * `"gap-target"` rather than `"gap"`: the shared key let an ordinary
   * `refreshScoreAndGap` supersede this attempt and swallow both the revert
   * and its message.
   *
   * Duplicated rather than shared, as the two workspaces' tests already are:
   * separate components, separate clients, separate copy, and a shared helper
   * would hide exactly the divergence the twin-sweep rule exists to catch.
   */
  async function onChangeTargetTier(next: number): Promise<void> {
    const mine = ++targetReqSeq.current;
    setPendingTarget(next);
    if (!assessment) {
      setTargetTier(next);
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
      const g = await fetchGapAnalysis(serviceId, { targetTier: next });
      // ONE GUARD, NOT TWO. A `mine !== targetReqSeq.current` return sat
      // above this and red-on-revert could not kill it: every newer pick
      // bumps BOTH sequences, and a newer refresh bumps this one, so the
      // ticket below already refuses everything the other refused. Deleted
      // rather than kept as decoration -- the same unpinned-conditional shape
      // this branch has now produced twice.
      if (gapWrite !== gapWriteSeq.current) return; // a newer gap write won
      // Nothing commits `targetTier` here: after a successful pick the only
      // thing carrying the new tier is `gap`, which is what `shownTier`
      // reads.
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
      // Claims nothing about the screen -- see the ZT twin: a concurrent
      // refresh can land the new tier's rows while this request fails, so
      // "the selector has gone back" is false in a cell the truth table
      // enumerates. What is true in every cell is that this request failed.
      const reason = serverReason(err);
      attempt.note(
        reason
          ? `${reason} Target tier ${next} could not be loaded; pick a tier again to retry.`
          : `Couldn't load gap rows for target tier ${next}. Pick a tier again to retry.`,
      );
    } finally {
      if (mine === targetReqSeq.current) setPendingTarget(null);
    }
  }

  const readOnly =
    assessment?.status === "approved" || assessment?.status === "released";

  const answeredCount =
    assessment?.answers.filter(
      (a) =>
        a.maturity_tier !== null ||
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
            NIST CSF 2.0 service
          </p>
          <h1 className="text-3xl font-semibold text-ink-primary">
            {serviceTitle}
          </h1>
          <p className="max-w-prose text-sm text-ink-secondary">
            Score each of the 106 subcategories against the 4-tier maturity
            model. Coverage + per-function rollup update on every edit;
            prioritized remediation gaps surface alongside the score.
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
          data-testid="csf-refresh-error"
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
          Loading CSF 2.0 catalog…
        </p>
      ) : !assessment ? (
        <EmptyState
          title="No CSF assessment yet"
          description="Click 'Start assessment' to create a fresh v1 with 106 empty subcategory rows."
        />
      ) : (
        <>
          {/* Ordered the way the work is done. This page used to run score ->
              playbook -> messages -> gaps -> deliverable -> QUESTIONNAIRE, so
              the 106-subcategory review — the actual work — sat at the very
              bottom, below the deliverable. Score, gaps and the thread are
              reference and now sit after the numbered path. */}
          <WorkflowStep
            number={1}
            title="Work the Playbook and draft with AI"
            description="The 10-step CSF 2.0 Playbook builds the working profiles, and Run AI drafts a tier per subcategory from them. It drafts; you decide."
          >
            <CsfPlaybookPanel serviceId={serviceId} readOnly={readOnly} />
          </WorkflowStep>

          <WorkflowStep
            number={2}
            title="Review every subcategory and adjust"
            description="Work through all 106 subcategories and set the tier you can defend. Where the client filled in their own responses, this is where you check them for completeness and accuracy — their answers are what the report rests on."
            done={
              assessment.status !== "draft" && assessment.status !== "submitted"
            }
          >
            <CsfQuestionnaire
              catalog={catalog}
              answersByCode={answersByCode}
              questionsByCode={interviewByCode}
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
            description="Locks the tiers so the deliverable is generated from a fixed set of answers. Approving does not send anything to the client — that is the last step."
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
              <CsfDeliverableCard
                serviceId={serviceId}
                assessmentStatus={assessment.status}
                deliverable={deliverable}
                onChange={setDeliverable}
              />
            </div>
          </WorkflowStep>

          {/* Reference, not steps. */}
          <CsfScoreCard score={score} />
          <CsfGapList
            analysis={gap}
            targetTier={shownTier}
            onChangeTargetTier={(t) => void onChangeTargetTier(t)}
          />
          <MessageThread serviceId={serviceId} />
        </>
      )}
    </div>
  );
}
