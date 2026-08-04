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
  ZtCatalog,
  ZtDeliverable,
  ZtFramework,
  ZtRunAiResponse,
  ZtScoreSummary,
} from "@/lib/zt/types";

import { MessageThread } from "@/components/messages/MessageThread";
import { StaleDocsNudge } from "@/components/admin/StaleDocsNudge";
import { AiPreviewButton } from "@/components/admin/AiPreviewButton";
import { DiscardDraftButton } from "@/components/admin/DiscardDraftButton";

import { ZtDeliverableCard } from "./ZtDeliverableCard";
import { ZtGapList } from "./ZtGapList";
import { ZtRoadmapCard } from "./ZtRoadmapCard";
import { ZtQuestionnaire } from "./ZtQuestionnaire";
import { ZtScoreCard } from "./ZtScoreCard";

import type { JSX } from "react";

export interface ZtWorkspaceProps {
  serviceId: string;
  framework: ZtFramework;
  serviceTitle: string;
}

/** Clamp a stored target stage to the selectable 2-4 range; default 3. */
function normalizeTarget(value: number | null | undefined): number {
  return value === 2 || value === 3 || value === 4 ? value : 3;
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
  const [score, setScore] = React.useState<ZtScoreSummary | null>(null);
  const [gap, setGap] = React.useState<GapAnalysis | null>(null);
  const [deliverable, setDeliverable] = React.useState<ZtDeliverable | null>(
    null,
  );
  const [loadError, setLoadError] = React.useState<string | null>(null);
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
      try {
        const [s, g] = await Promise.all([
          fetchScore(serviceId),
          fetchGapAnalysis(serviceId, { targetStage: currentTarget }),
        ]);
        setScore(s);
        setGap(g);
      } catch {
        // Non-blocking; cards show their own loading state.
      }
    },
    [serviceId],
  );

  const initialLoad = React.useCallback(async () => {
    const seq = ++assessmentSeq.current;
    try {
      const cat = await fetchCatalog(framework);
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
        const t = normalizeTarget(a.client_target_stage);
        setTargetStage(t);
        await refreshScoreAndGap(t);
        try {
          const d = await fetchLatestDeliverable(serviceId);
          setDeliverable(d);
        } catch {
          // non-blocking
        }
      }
    } catch (err) {
      setLoadError(describeError(err));
    }
  }, [serviceId, framework, refreshScoreAndGap]);

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
      const t = normalizeTarget(next.client_target_stage);
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
          const t = normalizeTarget(a.client_target_stage);
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

  async function onChangeTargetStage(next: number): Promise<void> {
    setTargetStage(next);
    if (assessment) {
      const g = await fetchGapAnalysis(serviceId, { targetStage: next });
      setGap(g);
    }
  }

  async function onRunAi(): Promise<void> {
    setBusy("run");
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
          {assessment ? (
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
          ) : (
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
          Loading catalog…
        </p>
      ) : !assessment ? (
        <EmptyState
          title="No Zero Trust assessment yet"
          description="Click 'Start assessment' to create a fresh v1 with one empty answer per capability."
        />
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Run AI (zt_score)</CardTitle>
            </CardHeader>
            <CardBody className="flex flex-col gap-3">
              <p className="text-sm text-ink-secondary">
                Suggest a current and target maturity stage per capability (on
                this framework&apos;s scale) plus per-pillar narratives. Locked
                rows are left untouched.
              </p>
              <div>
                <button
                  type="button"
                  onClick={() => void onRunAi()}
                  disabled={busy !== null || readOnly}
                  className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {busy === "run" ? "Running…" : "Run AI"}
                </button>
              </div>
              <AiPreviewButton serviceId={serviceId} disabled={busy !== null} />
              {runResult ? (
                <p className="text-sm text-ink-secondary" aria-live="polite">
                  Updated{" "}
                  <span className="font-semibold text-ink-primary">
                    {runResult.changed.length}
                  </span>{" "}
                  field
                  {runResult.changed.length === 1 ? "" : "s"} across{" "}
                  {
                    new Set(runResult.changed.map((c) => c.capability_code))
                      .size
                  }{" "}
                  capabilit
                  {new Set(runResult.changed.map((c) => c.capability_code))
                    .size === 1
                    ? "y"
                    : "ies"}
                  .
                </p>
              ) : null}
            </CardBody>
          </Card>
          <ZtScoreCard score={score} />
          <MessageThread serviceId={serviceId} />
          <ZtGapList
            analysis={gap}
            targetStage={targetStage}
            onChangeTargetStage={(s) => void onChangeTargetStage(s)}
            stages={catalog.stages}
          />
          <ZtRoadmapCard analysis={gap} />
          <StaleDocsNudge stale={assessment.documents_stale} />
          <ZtDeliverableCard
            serviceId={serviceId}
            assessmentStatus={assessment.status}
            deliverable={deliverable}
            onChange={setDeliverable}
          />
          <ZtQuestionnaire
            catalog={catalog}
            answersByCode={answersByCode}
            readOnly={readOnly}
            onAnswerUpdate={onAnswerUpdate}
          />
        </>
      )}
    </div>
  );
}
