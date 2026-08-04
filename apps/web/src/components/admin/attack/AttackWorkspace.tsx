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
  AttackProxyError,
  createAssessment,
  discardAssessment,
  fetchCatalog,
  fetchHeatmap,
  fetchLatestAssessment,
  fetchLatestDeliverable,
  patchCoverage,
  runAttackAi,
} from "@/lib/attack/client";
import type {
  AttackAssessment,
  AttackCatalog,
  AttackCoveragePatch,
  AttackCoverageRow,
  AttackDeliverable,
  AttackHeatmap,
  AttackRunAiResponse,
  CatalogTechnique,
  TacticHeatmapEntry,
} from "@/lib/attack/types";

import { MessageThread } from "@/components/messages/MessageThread";
import { StaleDocsNudge } from "@/components/admin/StaleDocsNudge";
import { AiPreviewButton } from "@/components/admin/AiPreviewButton";
import { DiscardDraftButton } from "@/components/admin/DiscardDraftButton";

import { AttackDeliverableCard } from "./AttackDeliverableCard";
import { AttackHeatmapCard } from "./AttackHeatmapCard";
import { AttackMatrix } from "./AttackMatrix";
import { AttackTechniquePanel } from "./AttackTechniquePanel";

import type { JSX } from "react";

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

export function AttackWorkspace({
  serviceId,
  serviceTitle,
}: AttackWorkspaceProps): JSX.Element {
  const [catalog, setCatalog] = React.useState<AttackCatalog | null>(null);
  const [assessment, setAssessment] = React.useState<AttackAssessment | null>(
    null,
  );
  const [heatmap, setHeatmap] = React.useState<AttackHeatmap | null>(null);
  const [deliverable, setDeliverable] =
    React.useState<AttackDeliverable | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<
    "create" | "approve" | "run" | "discard" | null
  >(null);
  const [runResult, setRunResult] = React.useState<AttackRunAiResponse | null>(
    null,
  );
  const [selectedCode, setSelectedCode] = React.useState<string | null>(null);
  const [showSubs, setShowSubs] = React.useState(false);

  // Monotonic request sequence: only the newest assessment-producing operation
  // may write `assessment`. Without this, a slow mount-time load resolving
  // AFTER the user starts an assessment, patches coverage, or runs the AI would
  // setAssessment(stale) and clobber the newer state (the T8 stale-fetch race).
  // Every mutation bumps the sequence before it writes, so any in-flight load
  // is discarded on arrival.
  const assessmentSeq = React.useRef(0);

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
    try {
      const next = await fetchHeatmap(serviceId);
      setHeatmap(next);
    } catch {
      // non-blocking
    }
  }, [serviceId]);

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
        } catch {
          // non-blocking
        }
      }
    } catch (err) {
      setLoadError(describeError(err));
    }
  }, [serviceId, refreshHeatmap]);

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
      await refreshHeatmap();
    } catch (err) {
      setLoadError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  async function onPatch(
    coverageId: string,
    patch: AttackCoveragePatch,
  ): Promise<void> {
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
    try {
      const next = await patchCoverage(coverageId, patch);
      setAssessment((curr) => {
        if (!curr) return curr;
        return {
          ...curr,
          coverage: curr.coverage.map((c) => (c.id === coverageId ? next : c)),
        };
      });
      await refreshHeatmap();
    } catch (err) {
      setLoadError(describeError(err));
      // Roll back by re-fetching, guarded so a newer patch still wins.
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
      setLoadError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  async function onRunAi(): Promise<void> {
    setBusy("run");
    setRunResult(null);
    const seq = ++assessmentSeq.current;
    try {
      const result = await runAttackAi(serviceId);
      setRunResult(result);
      // Re-pull the assessment so the matrix reflects the AI's suggestions,
      // guarded so a concurrent patch that started meanwhile still wins.
      const a = await fetchLatestAssessment(serviceId);
      if (seq === assessmentSeq.current) setAssessment(a);
      await refreshHeatmap();
    } catch (err) {
      setLoadError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  const readOnly =
    assessment?.status === "approved" || assessment?.status === "released";

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
          {assessment ? (
            <button
              type="button"
              onClick={() => void onApprove()}
              disabled={busy !== null || assessment.status !== "draft"}
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
          <AttackHeatmapCard heatmap={heatmap} />
          <Card>
            <CardHeader>
              <CardTitle>Run AI (mitre_map)</CardTitle>
            </CardHeader>
            <CardBody className="flex flex-col gap-3">
              <p className="text-sm text-ink-secondary">
                Suggest a coverage status and the detection / prevention /
                response tooling per technique from this client&apos;s Tech Debt
                capability list. Locked rows are left untouched; you stay in
                control of the final call.
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
                  {new Set(runResult.changed.map((c) => c.technique_code)).size}{" "}
                  technique
                  {new Set(runResult.changed.map((c) => c.technique_code))
                    .size === 1
                    ? ""
                    : "s"}
                  .{" "}
                  {runResult.tools_available === 0
                    ? "No tools were available from the Tech Debt list, so only statuses were inferred."
                    : `${runResult.tools_available} tool${runResult.tools_available === 1 ? "" : "s"} available for mapping.`}
                </p>
              ) : null}
            </CardBody>
          </Card>
          <StaleDocsNudge stale={assessment.documents_stale} />
          <AttackDeliverableCard
            serviceId={serviceId}
            assessmentStatus={assessment.status}
            deliverable={deliverable}
            onChange={setDeliverable}
          />
          <MessageThread serviceId={serviceId} />
          <AttackTechniquePanel
            technique={selectedTechnique}
            coverage={selectedCoverage}
            coverageDefinitions={catalog.coverage_definitions}
            readOnly={readOnly}
            onPatch={(patch) => {
              if (!selectedCoverage) return;
              return onPatch(selectedCoverage.id, patch);
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
        </>
      )}
    </div>
  );
}
