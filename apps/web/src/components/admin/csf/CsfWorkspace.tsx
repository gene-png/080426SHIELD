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
  return value === 2 || value === 3 || value === 4 ? value : 3;
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
  const [busy, setBusy] = React.useState<
    "create" | "approve" | "discard" | null
  >(null);
  const [targetTier, setTargetTier] = React.useState(3);
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
      try {
        const [s, g] = await Promise.all([
          fetchScore(serviceId),
          fetchGapAnalysis(serviceId, { targetTier: currentTarget }),
        ]);
        setScore(s);
        setGap(g);
      } catch {
        // Non-blocking; the score/gap panels show their own loading state.
      }
    },
    [serviceId],
  );

  const initialLoad = React.useCallback(async () => {
    const seq = ++assessmentSeq.current;
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
    } catch {
      // Non-blocking: interview prompts are supplemental context.
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
        } catch {
          // non-blocking; deliverable card shows "not finalized yet".
        }
      }
    } catch (err) {
      setLoadError(describeError(err));
    }
  }, [serviceId, refreshScoreAndGap]);

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
      await refreshScoreAndGap(targetTier);
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

  async function onChangeTargetTier(next: number): Promise<void> {
    setTargetTier(next);
    if (assessment) {
      const g = await fetchGapAnalysis(serviceId, { targetTier: next });
      setGap(g);
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
            targetTier={targetTier}
            onChangeTargetTier={(t) => void onChangeTargetTier(t)}
          />
          <MessageThread serviceId={serviceId} />
        </>
      )}
    </div>
  );
}
