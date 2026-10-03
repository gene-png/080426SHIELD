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
  reviewComputedStatuses,
  AttackProxyError,
  createAssessment,
  discardAssessment,
  fetchCatalog,
  fetchHeatmap,
  fetchLatestAssessment,
  fetchLatestDeliverable,
  confirmCoverageCitations,
  fetchAttackRun,
  fetchAttackRunSummary,
  patchCoverage,
  runAttackAi,
} from "@/lib/attack/client";
import type { AttackRun, ComputedStatusReview } from "@/lib/attack/client";
import type { AiServes } from "@/lib/aiRuns/types";
import { useAiRun } from "@/lib/aiRuns/useAiRun";
import type {
  AttackAssessment,
  AttackCatalog,
  AttackCoveragePatch,
  AttackCoverageRow,
  AttackDeliverable,
  AttackHeatmap,
  CatalogTechnique,
  TacticHeatmapEntry,
} from "@/lib/attack/types";

import { MessageThread } from "@/components/messages/MessageThread";
import { StaleDocsNudge } from "@/components/admin/StaleDocsNudge";
import { WorkflowStep } from "@/components/admin/WorkflowStep";
import { AiPreviewButton } from "@/components/admin/AiPreviewButton";
import { AiRunStatus, LastRunNote } from "@/components/admin/AiRunStatus";
import { DiscardDraftButton } from "@/components/admin/DiscardDraftButton";
import { RunAiGuard } from "@/components/admin/RunAiGuard";

import { AttackAiInputsPanel } from "./AttackAiInputsPanel";
import { AttackCitationAccounting } from "./AttackCitationAccounting";
import { AttackComputedReviewPanel } from "./AttackComputedReviewPanel";
import { AttackDeliverableCard } from "./AttackDeliverableCard";
import { AttackHeatmapCard } from "./AttackHeatmapCard";
import { AttackMatrix } from "./AttackMatrix";
import { AttackTechniquePanel } from "./AttackTechniquePanel";

import type { JSX } from "react";
import { ProgressStages } from "../ProgressStages";
import { useServiceStages } from "@/lib/stages/client";
import { useRefreshFailures } from "@/components/admin/useRefreshFailures";
import { isUpstreamOutcomeUnknown } from "@/lib/describe-save-error";
import { AiSourceNote } from "@/components/AiSourceNote";

export interface AttackWorkspaceProps {
  serviceId: string;
  serviceTitle: string;
}

function describeError(err: unknown): string {
  if (err instanceof AttackProxyError) {
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

/**
 * #550: what to say when the proxy never saw Run AI's answer. Not "failed":
 * the api may have finished and written the rows. It names where to look and
 * that the button stays off, because a retry sends the client's data out again.
 */
const RUN_OUTCOME_UNKNOWN =
  "We couldn't confirm whether the AI run finished. It may still complete and fill in technique rows. Reload the page later and check step 2, Review every technique and adjust, before running it again. Run AI stays off on this page until you reload.";

/**
 * #554 R3: what the review panel says after it re-read itself because what it
 * showed went stale -- a computed status moved, or a row left the queue -- between
 * loading and the click. Approved by the advisor 01:35Z (#808 copy, item 4 and
 * A11).
 */
function reviewRefreshedMessage(
  reason: string,
  codes: string[],
  refreshed: boolean,
): string {
  const shown = codes.slice(0, 10).join(", ");
  const more = codes.length > 10 ? ` and ${codes.length - 10} more` : "";
  const what =
    reason === "codes_not_in_review_queue"
      ? `Some techniques are no longer awaiting review (${shown}${more}).`
      : `The computed status of some techniques changed after the panel loaded (${shown}${more}).`;
  // The failed re-read's ending: approved by the advisor 02:10Z.
  return refreshed
    ? `${what} The panel has been refreshed; review again.`
    : `${what} The panel could not be refreshed; reload the page and review again.`;
}

/** The machine-readable `reason` on a typed error envelope (D-016), if present. */
function errorReason(err: unknown): string | null {
  if (!(err instanceof AttackProxyError)) return null;
  const payload = err.payload as { error?: { reason?: string } } | undefined;
  return payload?.error?.reason ?? null;
}

/** The patch fields that feed a computed parent's derived state (#620 round 2):
 *  its status and reason, and -- through the children's pending review -- the
 *  tool lists. Notes and narrative feed nothing derived. */
const PARENT_INPUTS: readonly (keyof AttackCoveragePatch)[] = [
  "status",
  "reason_code",
  "detection_tools",
  "prevention_tools",
  "response_tools",
];

export function AttackWorkspace({
  serviceId,
  serviceTitle,
}: AttackWorkspaceProps): JSX.Element {
  const [catalog, setCatalog] = React.useState<AttackCatalog | null>(null);
  const [assessment, setAssessment] = React.useState<AttackAssessment | null>(
    null,
  );
  // Derived six-stage progress. Re-reads when this workspace's own
  // state moves, since the derivation is computed from that same state.
  const { phase: stagesPhase, stages: serviceStages } = useServiceStages(
    serviceId,
    `${assessment?.status ?? ""}:${assessment?.version ?? ""}`,
  );
  const [heatmap, setHeatmap] = React.useState<AttackHeatmap | null>(null);
  const [deliverable, setDeliverable] =
    React.useState<AttackDeliverable | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  /**
   * #622 round 1: what the LAST action (create, edit, confirm, approve,
   * discard, run) failed or was refused with. Distinct from `loadError`, which
   * says the workspace could not load: an approve refused for a reasonless
   * Partial went into that card and nothing ever cleared it, so it stayed
   * beside "Approved" after the consultant fixed the rows. Cleared when any
   * action starts, so it always describes the action just taken.
   */
  const [actionError, setActionError] = React.useState<string | null>(null);
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
   * opposite directions; see `useRefreshFailures`. This file had BOTH halves
   * of the second one: it never cleared, and its two catches wrote the
   * IDENTICAL sentence, so a failed heatmap and a failed deliverable check
   * were the same bytes in the same slot with no way to tell them apart.
   */
  const { messages: refreshMessages, begin: beginRefresh } =
    useRefreshFailures();
  const [busy, setBusy] = React.useState<
    "create" | "approve" | "review" | "run" | "discard" | null
  >(null);
  // Set when the API REFUSES a run (typed 409). Distinct from loadError: the
  // page is fine, the prerequisite is not.
  const [runBlocked, setRunBlocked] = React.useState<string | null>(null);
  // #550: set once a run's outcome is unknown, never cleared. A reload clears
  // it, which the copy says; nothing on this page can know the run finished.
  const [runOutcomeUnknown, setRunOutcomeUnknown] = React.useState(false);
  const [selectedCode, setSelectedCode] = React.useState<string | null>(null);
  const [showSubs, setShowSubs] = React.useState(false);

  // Monotonic request sequence: only the newest assessment-producing operation
  // may write `assessment`. Without this, a slow mount-time load resolving
  // AFTER the user starts an assessment, patches coverage, or runs the AI would
  // setAssessment(stale) and clobber the newer state (the T8 stale-fetch race).
  // Every mutation bumps the sequence before it writes, so any in-flight load
  // is discarded on arrival.
  const assessmentSeq = React.useRef(0);
  // #620 round 2, finding 7. A parent is recomputed on the server by a child's
  // write, so after one the workspace re-reads the assessment. That re-read is
  // only true if no OTHER edit is mid-flight: one that started before it reads
  // the server before that edit lands, and would put the edit's old value back
  // on screen. So the re-read waits until no edit is in flight, and is taken
  // again if an edit started while it was out.
  const editsInFlight = React.useRef(0);
  const editsStarted = React.useRef(0);
  const refetchWanted = React.useRef(false);

  const coverageByCode = React.useMemo(() => {
    const out: Record<string, AttackCoverageRow> = {};
    if (assessment) {
      for (const row of assessment.coverage) {
        out[row.technique_code] = row;
      }
    }
    return out;
  }, [assessment]);

  const techniqueByCode = React.useMemo(() => {
    const out: Record<string, CatalogTechnique> = {};
    if (catalog) {
      for (const t of catalog.techniques) {
        out[t.id] = t;
      }
    }
    return out;
  }, [catalog]);

  const heatmapByTactic = React.useMemo(() => {
    const out: Record<string, TacticHeatmapEntry> = {};
    if (heatmap) {
      for (const t of heatmap.by_tactic) {
        out[t.tactic_id] = t;
      }
    }
    return out;
  }, [heatmap]);

  const refreshHeatmap = React.useCallback(async () => {
    const heatmapAttempt = beginRefresh("heatmap");
    try {
      const next = await fetchHeatmap(serviceId);
      setHeatmap(next);
      heatmapAttempt.clear();
    } catch (err) {
      // NON-BLOCKING IS NOT SILENT. The old comment was true and is
      // why this survived: a panel's own loading state cannot be told
      // apart from a slow network.
      //
      // #556: an assessment scored against another ATT&CK catalog is REFUSED
      // (409 `attack_catalog_mismatch`), and "reload to try again" would be
      // false advice for it -- no reload fixes a stale assessment. Keyed on the
      // reason's VALUE, never its presence (CLAUDE.md, #317), so every other
      // failure keeps the sentence below.
      heatmapAttempt.note(
        errorReason(err) === "attack_catalog_mismatch"
          ? describeError(err)
          : "Couldn't refresh the coverage heatmap. What is shown may be out of date; reload to try again.",
      );
    }
  }, [serviceId, beginRefresh]);

  const initialLoad = React.useCallback(async () => {
    const seq = ++assessmentSeq.current;
    // A load that runs again says what THIS load found (#622 round 1 sweep).
    setLoadError(null);
    // EVERY token this function will use is minted HERE, before any await.
    // See `useRefreshFailures`: mint below an await and the tokens are ordered
    // by RESOLUTION, so an initialLoad started FIRST whose earlier fetch is
    // slow issues the LATER token and overwrites a newer load's record.
    //
    // The `seq` early-return below does NOT close this. It narrows the window:
    // a load that PASSES that check can still be overtaken while it awaits
    // `refreshScoreAndGap`, and would then mint after the newer load did.
    const deliverableAttempt = beginRefresh("deliverable");
    try {
      const cat = await fetchCatalog();
      setCatalog(cat);
    } catch (err) {
      setLoadError(describeError(err));
      return;
    }
    try {
      const a = await fetchLatestAssessment(serviceId);
      if (seq !== assessmentSeq.current) {
        console.debug(
          `[AttackWorkspace] discarded stale assessment load (seq ${seq}, latest ${assessmentSeq.current})`,
        );
        return;
      }
      setAssessment(a);
      if (a) {
        await refreshHeatmap();
        try {
          const d = await fetchLatestDeliverable(serviceId);
          setDeliverable(d);
          deliverableAttempt.clear();
        } catch {
          // A FALSE NEGATIVE, not a stale panel, and the first version of this
          // fix gave it the generic "part of this workspace" message -- a
          // half-fix, because `AttackDeliverableCard` renders "Not finalized
          // yet" exactly as its CSF and Tech Debt twins do. That is a claim
          // ABOUT THE SERVER made on the strength of a request that failed,
          // and a consultant can act on it by finalizing a second time.
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
  }, [serviceId, refreshHeatmap, beginRefresh]);

  React.useEffect(() => {
    void (async () => {
      await initialLoad();
    })();
  }, [initialLoad]);

  // #645. A run this page did not start -- found in progress on load -- ends
  // here: re-read what it applied, as `onRunAiWrite` does for its own.
  const onRunFinishedElsewhere = React.useCallback(
    (run: AttackRun) => {
      if (run.status !== "completed") return;
      const seq = ++assessmentSeq.current;
      void fetchLatestAssessment(serviceId)
        .then((a) => {
          if (seq === assessmentSeq.current) setAssessment(a);
          return refreshHeatmap();
        })
        .catch((err: unknown) => setActionError(describeError(err)));
    },
    [serviceId, refreshHeatmap],
  );
  const aiRun = useAiRun({
    serviceId,
    // #271: only this assessment's runs describe it. `null` until it loads.
    subjectId: assessment?.id ?? null,
    fetchSummary: fetchAttackRunSummary,
    fetchRun: fetchAttackRun,
    onFinished: onRunFinishedElsewhere,
  });

  function onCreateAssessment(): Promise<void> {
    return trackWrite(() => onCreateAssessmentWrite());
  }

  async function onCreateAssessmentWrite(): Promise<void> {
    setActionError(null);
    setBusy("create");
    assessmentSeq.current += 1;
    try {
      const next = await createAssessment(serviceId);
      setAssessment(next);
      await refreshHeatmap();
    } catch (err) {
      setActionError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  /** Whether `code` has a parent whose status is computed from it (D-094).
   *  From the catalog's parent links, the same structure the API computes
   *  over -- not from the code's spelling. */
  function hasComputedParent(code: string): boolean {
    const parentId = techniqueByCode[code]?.parent_id ?? null;
    return parentId !== null;
  }

  /** Re-read the assessment once no write is in flight (#620 round 2,
   *  finding 7). NEVER throws: it runs after a write that already landed, so
   *  a failed re-read is reported as that -- a saved change whose parent may
   *  be stale -- and never as a failed save or an unhandled rejection. */
  async function refetchWhenQuiet(): Promise<void> {
    if (!refetchWanted.current || editsInFlight.current > 0) return;
    refetchWanted.current = false;
    const attempt = beginRefresh("assessment");
    const started = editsStarted.current;
    const seq = ++assessmentSeq.current;
    let a: Awaited<ReturnType<typeof fetchLatestAssessment>>;
    try {
      a = await fetchLatestAssessment(serviceId);
    } catch {
      attempt.note(
        // Copy for the advisor (#808 round 5): general, because a review now
        // asks for this re-read too, not only a parent's recompute.
        "Your change was saved, but the assessment could not be re-read, so what is shown may be out of date. Reload to see it.",
      );
      return;
    }
    attempt.clear();
    if (editsStarted.current !== started) {
      // An edit began while this was out, so `a` may predate it. Drop it; that
      // edit's own completion takes the re-read again.
      refetchWanted.current = true;
      await refetchWhenQuiet();
      return;
    }
    if (seq === assessmentSeq.current) setAssessment(a);
  }

  /**
   * #620 round 3, finding 3. Every action that writes and then re-pulls the
   * assessment is counted here, not only panel edits: a parent re-read taken
   * while Run AI, approve, discard or create is out reads the server before
   * that action lands, and would overwrite its result (and its own re-pull
   * would then be dropped as out of date). The re-read waits for all of them.
   */
  async function trackWrite(fn: () => Promise<void>): Promise<void> {
    editsStarted.current += 1;
    editsInFlight.current += 1;
    try {
      await fn();
    } finally {
      editsInFlight.current -= 1;
    }
    await refetchWhenQuiet();
  }

  async function onPatch(
    coverageId: string,
    patch: AttackCoveragePatch,
  ): Promise<void> {
    setActionError(null);
    editsStarted.current += 1;
    editsInFlight.current += 1;
    // Optimistic. The bump invalidates any in-flight load so its late arrival
    // cannot clobber this edit.
    assessmentSeq.current += 1;
    setAssessment((curr) => {
      if (!curr) return curr;
      return {
        ...curr,
        coverage: curr.coverage.map((c) =>
          c.id === coverageId ? { ...c, ...patch } : c,
        ),
      };
    });
    let ok = false;
    try {
      const next = await patchCoverage(coverageId, patch);
      setAssessment((curr) => {
        if (!curr) return curr;
        return {
          ...curr,
          coverage: curr.coverage.map((c) => (c.id === coverageId ? next : c)),
        };
      });
      // #554 (D-094): a sub-technique's write recomputes its PARENT on the
      // server, and the PATCH returns only the child. Every field that feeds
      // the parent's derived state triggers a re-read: status and reason (its
      // status), and the tool lists (its children's pending review, and so its
      // own).
      if (
        hasComputedParent(next.technique_code) &&
        PARENT_INPUTS.some((k) => k in patch)
      ) {
        refetchWanted.current = true;
      }
      ok = true;
    } catch (err) {
      setActionError(describeError(err));
      // Roll back by re-fetching, guarded so a newer patch still wins.
      const seq = ++assessmentSeq.current;
      const a = await fetchLatestAssessment(serviceId);
      if (seq === assessmentSeq.current) setAssessment(a);
    } finally {
      editsInFlight.current -= 1;
    }
    // On BOTH paths: if this was the last edit in flight, a re-read another
    // edit asked for would otherwise never run. A no-op when none is wanted.
    await refetchWhenQuiet();
    if (ok) await refreshHeatmap();
  }

  /**
   * #101 / #102. Vouch for a technique's outstanding citations so its status may
   * score again.
   *
   * No optimistic update, unlike `onPatch`. `pending_review` is DERIVED
   * server-side from the row's citations and its tool lists, so guessing the new
   * value here would mean reimplementing the rule in the browser -- a second,
   * laxer answer to the question `app/attack/pending.py` exists to answer once.
   * The round trip is one request on a deliberate click.
   */
  async function onConfirmCitations(coverageId: string): Promise<void> {
    setActionError(null);
    editsStarted.current += 1;
    editsInFlight.current += 1;
    assessmentSeq.current += 1;
    let ok = false;
    try {
      const next = await confirmCoverageCitations(coverageId);
      setAssessment((curr) =>
        curr
          ? {
              ...curr,
              coverage: curr.coverage.map((c) =>
                c.id === coverageId ? next : c,
              ),
            }
          : curr,
      );
      // #620 round 2, finding 6: confirming a child's evidence can clear its
      // parent's pending state, which lives only on the server.
      if (hasComputedParent(next.technique_code)) refetchWanted.current = true;
      ok = true;
    } catch (err) {
      setActionError(describeError(err));
    } finally {
      editsInFlight.current -= 1;
    }
    await refetchWhenQuiet(); // on both paths, as in `onPatch`
    // The whole point is that the score changes at this moment and not before.
    if (ok) await refreshHeatmap();
  }

  function onApprove(): Promise<void> {
    return trackWrite(() => onApproveWrite());
  }

  async function onApproveWrite(): Promise<void> {
    if (!assessment) return;
    setActionError(null);
    setBusy("approve");
    // Same shape as the review's snapshot (a concurrent edit can be reverted on
    // screen); filed as #809.
    assessmentSeq.current += 1;
    try {
      const next = await approveAssessment(assessment.id);
      setAssessment(next);
    } catch (err) {
      setActionError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  function onReview(reviews: ComputedStatusReview[]): Promise<void> {
    return trackWrite(() => onReviewWrite(reviews));
  }

  /** #554 R3: record the review of what the panel showed. */
  async function onReviewWrite(reviews: ComputedStatusReview[]): Promise<void> {
    if (!assessment) return;
    setActionError(null);
    setBusy("review");
    // Bumped so a load already in flight (the page's own, or one started by
    // `onRunFinishedElsewhere`) cannot overwrite the review's result when it
    // lands late. The result itself is applied unconditionally, like approve's:
    // a row edit made while the review is in flight also bumps the counter, and
    // guarding on it would drop a review the server recorded (#808 round 3).
    assessmentSeq.current += 1;
    // The snapshot applied below may predate a row edit -- one in flight when
    // the review was clicked, or one made since -- and would then revert it on
    // screen. So after ANY review write, ask for one quiet re-read once every
    // write is done (`trackWrite`'s trailing `refetchWhenQuiet`): one extra GET
    // per review, correct in every interleaving (#808 rounds 4 and 5).
    const rereadAfter = () => {
      refetchWanted.current = true;
    };
    try {
      const next = await reviewComputedStatuses(assessment.id, reviews);
      setAssessment(next);
      rereadAfter();
    } catch (err) {
      const reason = errorReason(err);
      if (
        reason === "computed_status_changed" ||
        reason === "codes_not_in_review_queue"
      ) {
        // What the panel showed is stale, so it re-reads itself rather than
        // telling the consultant to find a reload control.
        const codes = (
          (err as AttackProxyError).payload as { error?: { codes?: string[] } }
        ).error?.codes;
        // The re-read can fail too, and must say so: an unhandled rejection
        // here would leave stale statuses and an enabled button, every click
        // silent.
        try {
          const latest = await fetchLatestAssessment(serviceId);
          setAssessment(latest);
          rereadAfter();
          setActionError(reviewRefreshedMessage(reason, codes ?? [], true));
        } catch {
          setActionError(reviewRefreshedMessage(reason, codes ?? [], false));
        }
      } else {
        setActionError(describeError(err));
      }
    } finally {
      setBusy(null);
    }
  }

  function onDiscard(): Promise<void> {
    return trackWrite(() => onDiscardWrite());
  }

  async function onDiscardWrite(): Promise<void> {
    if (!assessment) return;
    setActionError(null);
    setBusy("discard");
    const seq = ++assessmentSeq.current;
    try {
      await discardAssessment(assessment.id);
      // Refetch latest, guarded: any in-flight load holding the pre-discard
      // draft is discarded on arrival, so it can't resurrect it. 404 → null
      // (empty state, Start live again) or the prior approved version.
      const a = await fetchLatestAssessment(serviceId);
      if (seq === assessmentSeq.current) {
        setAssessment(a);
        if (a) {
          await refreshHeatmap();
        } else {
          setHeatmap(null);
          setDeliverable(null);
        }
      }
    } catch (err) {
      setActionError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  function onRunAi(serves: AiServes): Promise<void> {
    return trackWrite(() => onRunAiWrite(serves));
  }

  async function onRunAiWrite(serves: AiServes): Promise<void> {
    setActionError(null);
    setBusy("run");
    const seq = ++assessmentSeq.current;
    try {
      // #550 review, finding 1: two tries, not one. Only the POST's own
      // rejection can mean "the run's outcome is unknown"; a re-read that
      // fails after the run answered is that re-read's error and must not
      // lock Run AI.
      let started: Awaited<ReturnType<typeof runAttackAi>>;
      try {
        started = await runAttackAi(serviceId, serves);
      } catch (err) {
        // A refused run is guidance, not a broken page. Mapping with an empty
        // capability list would report every technique as a gap, so the API
        // blocks it — render that as something to act on rather than as a red
        // "failed to load" banner that reads like an outage.
        if (errorReason(err) === "no_security_capabilities") {
          setRunBlocked(describeError(err));
        } else if (isUpstreamOutcomeUnknown(err)) {
          // Its own alert beside the button, not `actionError`: that card is
          // headed "That didn't go through", which is the claim this is not
          // allowed to make, and any later action clears it.
          setRunOutcomeUnknown(true);
          // #645: a run may have started. Look once, and follow it if so; the
          // lock and the copy above stand either way.
          void aiRun.reconcile();
        } else {
          setActionError(describeError(err));
        }
        return;
      }
      setRunBlocked(null);
      // #645: the POST started the run; the write lasts until the run ends, so
      // the re-read guard in `trackWrite` still counts it as one write.
      const finished = await aiRun.follow(started);
      if (finished.status !== "completed") return; // `AiRunStatus` says why
      try {
        // Re-pull the assessment so the matrix reflects the AI's suggestions,
        // guarded so a concurrent patch that started meanwhile still wins.
        const a = await fetchLatestAssessment(serviceId);
        if (seq === assessmentSeq.current) setAssessment(a);
        await refreshHeatmap();
      } catch (err) {
        setActionError(describeError(err));
      }
    } finally {
      setBusy(null);
    }
  }

  const readOnly =
    assessment?.status === "approved" || assessment?.status === "released";
  /** #645: a run holds the edit lock; the api refuses edits until it ends. */
  const runInProgress = aiRun.running !== null;
  /**
   * What the last COMPLETED run did, read from the run itself, so it survives
   * a reload (#271). It used to live only in this component's state, and a
   * refresh left a partial run looking complete.
   */
  const runResult = aiRun.lastCompleted?.result ?? null;

  const scoredCount =
    assessment?.coverage.filter((c) => c.status !== null).length ?? 0;
  const discardSummary = `${scoredCount} scored technique${
    scoredCount === 1 ? "" : "s"
  } will be discarded.`;

  const selectedTechnique = selectedCode
    ? (techniqueByCode[selectedCode] ?? null)
    : null;
  const selectedCoverage = selectedCode
    ? (coverageByCode[selectedCode] ?? null)
    : null;
  // #554 (D-094): derived from the catalog, the same parent/child structure
  // the API computes over, never a second list.
  const selectedSubTechniqueCount = selectedCode
    ? (catalog?.techniques.filter((t) => t.parent_id === selectedCode).length ??
      0)
    : 0;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">
            MITRE ATT&amp;CK Coverage
          </p>
          <h1 className="text-3xl font-semibold text-ink-primary">
            {serviceTitle}
          </h1>
          <p className="max-w-prose text-sm text-ink-secondary">
            Walk the Enterprise matrix and set defensive coverage status per
            technique. The heatmap updates live; cells that show as Gap drive
            the deliverable&apos;s remediation priorities.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {assessment ? (
            <StatusPill
              tone={
                assessment.status === "approved" ||
                assessment.status === "released"
                  ? "success"
                  : "info"
              }
              withDot
            >
              {assessment.status === "draft"
                ? `Draft v${assessment.version}`
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
              // #645: NOT locked by a run. D-031: a discard racing a run
              // wins, and the run then ends without applying anything.
              disabled={busy !== null && busy !== "run"}
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

      {refreshMessages.length > 0 ? (
        <div
          className="space-y-2 rounded-md border border-status-warning-border bg-status-warning-bg p-3 text-sm text-status-warning-fg"
          role="status"
          data-testid="attack-refresh-error"
        >
          {refreshMessages.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      ) : null}

      {actionError ? (
        <Card>
          <CardHeader>
            <CardTitle>That didn&apos;t go through</CardTitle>
          </CardHeader>
          <CardBody>
            <p
              className="text-sm text-status-danger-fg"
              role="alert"
              data-testid="attack-action-error"
            >
              {actionError}
            </p>
          </CardBody>
        </Card>
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
          Loading ATT&amp;CK matrix…
        </p>
      ) : !assessment ? (
        <EmptyState
          title="No coverage assessment yet"
          description="Click 'Start assessment' to pre-seed an unscored coverage row for every technique in the Enterprise matrix."
        />
      ) : (
        <>
          {/* Ordered the way the work is actually done. This page used to run
              heatmap → Run AI → deliverable → messages → matrix, so the matrix —
              the longest task and the whole point of the page — sat at the
              bottom below the message thread, and nothing said what to do
              first. Reference material (the rollup, the thread) now sits after
              the steps rather than between them. */}
          <WorkflowStep
            number={1}
            title="Draft the mapping with AI"
            description="Claude suggests a coverage status and the detection / prevention / response tooling for each technique, using only this client's approved Tech Debt capability list. It drafts; you decide. Locked rows are never touched."
            done={runResult !== null || scoredCount > 0}
            blockedReason={
              assessment.catalog_current !== true
                ? "This assessment was scored against a different ATT&CK catalog than the current one, so the AI cannot draft over it."
                : null
            }
          >
            <div className="flex flex-col gap-3">
              {/* Issue 2: warn before producing canned output when no key is
                  loaded. Passes straight through when AI is live. */}
              <RunAiGuard onProceed={(serves) => void onRunAi(serves)}>
                {({ onClick, statusUnknown }) => (
                  <div>
                    <button
                      type="button"
                      onClick={onClick}
                      disabled={
                        // #645: an unreadable AI status fails closed.
                        statusUnknown ||
                        busy !== null ||
                        runInProgress ||
                        readOnly ||
                        runOutcomeUnknown ||
                        // #556: the API refuses it; the step says why.
                        assessment.catalog_current !== true
                      }
                      className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {busy === "run" || runInProgress ? "Running…" : "Run AI"}
                    </button>
                  </div>
                )}
              </RunAiGuard>
              {runOutcomeUnknown ? (
                <p className="text-sm text-status-warning-fg" role="alert">
                  {RUN_OUTCOME_UNKNOWN}
                </p>
              ) : null}
              <AiPreviewButton serviceId={serviceId} disabled={busy !== null} />
              {/* Beside the preview, not a second surface. The preview
                  answers "what will be sent?" (redacted); this answers
                  "what will NOT be sent, and where did the rest come
                  from?" -- the question nothing on this page answered, and
                  the one behind a run that reports a filtered-out tool as a
                  gap. Read-only and not rate-limited, so it loads on mount. */}
              <AttackAiInputsPanel serviceId={serviceId} />
              <AiRunStatus run={aiRun} />
              {/* #646: the assessment's AI source, from the derivation the
                  deliverable and the client dashboard call. */}
              {assessment ? (
                <AiSourceNote source={assessment.ai_source} />
              ) : null}
              <LastRunNote run={aiRun.lastCompleted} />
              {runResult ? (
                <p className="text-sm text-ink-secondary" aria-live="polite">
                  Updated{" "}
                  <span className="font-semibold text-ink-primary">
                    {runResult.changed.length}
                  </span>{" "}
                  field
                  {runResult.changed.length === 1 ? "" : "s"} across{" "}
                  {new Set(runResult.changed.map((c) => c.technique_code)).size}{" "}
                  technique
                  {new Set(runResult.changed.map((c) => c.technique_code))
                    .size === 1
                    ? ""
                    : "s"}
                  .{" "}
                  {`${runResult.tools_available} tool${runResult.tools_available === 1 ? "" : "s"} available for mapping.`}
                </p>
              ) : null}
              {runResult ? (
                <AttackCitationAccounting result={runResult} />
              ) : null}
              {runBlocked ? (
                <p
                  className="text-sm text-status-warning-fg"
                  role="status"
                  data-testid="attack-run-blocked"
                >
                  {runBlocked}
                </p>
              ) : null}
            </div>
          </WorkflowStep>

          <WorkflowStep
            number={2}
            title="Review every technique and adjust"
            description="Click any cell to set its coverage status, cite the tooling that provides it, and record your rationale. This is the judgement the client is paying for — the AI draft is a starting point, not an answer. Lock a row to protect it from future AI runs."
            done={assessment.status !== "draft"}
          >
            {assessment.catalog_current !== true ? (
              // #556: the rows are keyed by technique ID, and an ID can mean a
              // different technique in the current catalog (T1558 and T1649
              // swapped names in the list this replaced). Drawing them into the
              // current matrix would relabel answers by ID (D-091), and codes the
              // catalog no longer has would silently vanish from the grid.
              <p
                role="status"
                data-testid="attack-stale-catalog"
                className="rounded-md border border-status-warning-fg/40 bg-surface-sunken p-3 text-sm text-status-warning-fg"
              >
                {`This assessment was scored against ${
                  assessment.catalog_version
                    ? `ATT&CK v${assessment.catalog_version}`
                    : "an ATT&CK catalog that was never recorded"
                }, not the current one. Its ${assessment.coverage.length} rows are not shown against the current technique names, because a technique ID can name a different technique in the current catalog.`}
              </p>
            ) : (
              <div className="flex flex-col gap-4">
                <AttackTechniquePanel
                  technique={selectedTechnique}
                  subTechniqueCount={selectedSubTechniqueCount}
                  coverage={selectedCoverage}
                  coverageDefinitions={catalog.coverage_definitions}
                  reasonCodes={catalog.reason_codes}
                  toolRetirement={assessment.tool_retirement}
                  readOnly={readOnly || runInProgress}
                  onPatch={(patch) => {
                    if (!selectedCoverage) return;
                    return onPatch(selectedCoverage.id, patch);
                  }}
                  onConfirmCitations={() => {
                    if (!selectedCoverage) return;
                    return onConfirmCitations(selectedCoverage.id);
                  }}
                />
                <AttackMatrix
                  catalog={catalog}
                  coverageByCode={coverageByCode}
                  heatmapByTactic={heatmapByTactic}
                  onSelectTechnique={(code) => setSelectedCode(code)}
                  selectedCode={selectedCode}
                  showSubTechniques={showSubs}
                  onToggleSubTechniques={setShowSubs}
                />
              </div>
            )}
          </WorkflowStep>

          <WorkflowStep
            number={3}
            title="Approve the assessment"
            description="Locks the coverage matrix so the deliverable is generated from a fixed set of scores. Approving does not release anything to the client — that is the last step."
            done={assessment.status !== "draft"}
            blockedReason={
              // #556: the API refuses to approve an assessment scored against
              // another ATT&CK catalog; say so here instead of offering a button
              // whose only outcome is that refusal. `!== true` on purpose: an
              // absent field reads as NOT current -- missing data defaults to
              // unconfirmed, never to confirmed.
              assessment.catalog_current !== true
                ? "This assessment was scored against a different ATT&CK catalog than the current one, so it cannot be approved."
                : scoredCount === 0
                  ? "Nothing has been scored yet. Run the AI draft or score techniques by hand in step 2 first."
                  : null
            }
          >
            <button
              type="button"
              onClick={() => void onApprove()}
              disabled={
                busy !== null ||
                runInProgress ||
                assessment.status !== "draft" ||
                scoredCount === 0 ||
                assessment.catalog_current !== true
              }
              className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {assessment.status === "approved"
                ? "Approved"
                : assessment.status === "released"
                  ? "Released"
                  : busy === "approve"
                    ? "Approving…"
                    : "Approve"}
            </button>
          </WorkflowStep>

          <WorkflowStep
            number={4}
            title="Generate and release the deliverable"
            description="Renders the PDF and XLSX from the approved assessment. Nothing reaches the client until you release it — generating is safe, releasing is the point of no return."
            blockedReason={
              assessment.catalog_current !== true
                ? "This assessment was scored against a different ATT&CK catalog than the current one, so no deliverable can be generated or released from it."
                : assessment.status === "draft"
                  ? "Approve the assessment in step 3 before generating a deliverable from it."
                  : null
            }
          >
            <div className="flex flex-col gap-3">
              {/* #554 R3: the release gate's review queue, named by the release
                  refusal, so it sits in the step where that refusal is met. */}
              <AttackComputedReviewPanel
                assessment={assessment}
                busy={busy !== null || runInProgress}
                onReview={onReview}
              />
              <StaleDocsNudge stale={assessment.documents_stale} />
              <AttackDeliverableCard
                serviceId={serviceId}
                assessmentStatus={assessment.status}
                deliverable={deliverable}
                onChange={setDeliverable}
                catalogStale={assessment.catalog_current !== true}
              />
            </div>
          </WorkflowStep>

          {/* Reference, not steps: useful throughout, required at no particular
              point. Kept below the flow so the numbered path stays unbroken. */}
          <AttackHeatmapCard heatmap={heatmap} />
          <MessageThread serviceId={serviceId} />
        </>
      )}
    </div>
  );
}
