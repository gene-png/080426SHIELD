"use client";
import * as React from "react";

import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  NumberCard,
  StatusPill,
} from "@shield/design-system";

import { Dropzone } from "@/components/intake/Dropzone";
import { RedactionDisclosure } from "@/components/intake/RedactionDisclosure";
import {
  approveCapabilityList,
  discardCapabilityList,
  extractCapabilities,
  fetchConsolidationPlan,
  fetchLatestDeliverable,
  fetchLatestList,
  fetchOverlapAnalysis,
  TechDebtProxyError,
} from "@/lib/tech_debt/client";
import type {
  CapabilityItem,
  CapabilityList,
  ConsolidationPlanSummary,
  Deliverable,
  OverlapAnalysis,
} from "@/lib/tech_debt/types";

import { AiStatusBanner } from "./AiStatusBanner";
import { ConsolidationPlanCard } from "./ConsolidationPlanCard";
import { DeliverableCard } from "./DeliverableCard";
import { DiscardDraftButton } from "./DiscardDraftButton";
import { EditableCapabilityTable } from "./EditableCapabilityTable";
import { IntakeDocumentsPanel } from "./IntakeDocumentsPanel";
import { OverlapDashboard } from "./OverlapDashboard";

import type { JSX } from "react";

export interface TechDebtWorkspaceProps {
  serviceId: string;
  serviceTitle: string;
}

export function TechDebtWorkspace({
  serviceId,
  serviceTitle,
}: TechDebtWorkspaceProps): JSX.Element {
  const [list, setList] = React.useState<CapabilityList | null>(null);
  const [overlap, setOverlap] = React.useState<OverlapAnalysis | null>(null);
  const [overlapError, setOverlapError] = React.useState<string | null>(null);
  const [overlapLoading, setOverlapLoading] = React.useState(false);
  const [plan, setPlan] = React.useState<ConsolidationPlanSummary | null>(null);
  const [deliverable, setDeliverable] = React.useState<Deliverable | null>(
    null,
  );
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [extracting, setExtracting] = React.useState(false);
  const [extractError, setExtractError] = React.useState<string | null>(null);
  const [approving, setApproving] = React.useState(false);
  const [discarding, setDiscarding] = React.useState(false);
  const [docsReloadKey, setDocsReloadKey] = React.useState(0);

  // Monotonic request sequences guard two independently-clobberable states.
  // `listSeq`: only the newest list-producing operation may write `list` — a
  // fresh extraction / inline edit / approve that fires while the mount load is
  // in flight bumps it, so the late fetchLatestList is discarded. `overlapSeq`:
  // refreshOverlap fires from mount AND from every inline edit, so overlapping
  // fetches can resolve out of order; only the newest may write overlap/plan
  // (the T8 stale-fetch race).
  const listSeq = React.useRef(0);
  const overlapSeq = React.useRef(0);

  const refreshOverlap = React.useCallback(async () => {
    const seq = ++overlapSeq.current;
    setOverlapLoading(true);
    try {
      const next = await fetchOverlapAnalysis(serviceId);
      if (seq === overlapSeq.current) {
        setOverlap(next);
        setOverlapError(null);
      }
    } catch (err) {
      if (seq === overlapSeq.current) {
        setOverlapError(
          err instanceof Error ? err.message : "Failed to load overlap.",
        );
      }
    } finally {
      if (seq === overlapSeq.current) setOverlapLoading(false);
    }
    try {
      const nextPlan = await fetchConsolidationPlan(serviceId);
      if (seq === overlapSeq.current) setPlan(nextPlan);
    } catch {
      // non-blocking; dashboard already shows the overlap.
    }
  }, [serviceId]);

  const refresh = React.useCallback(async () => {
    const seq = ++listSeq.current;
    try {
      const next = await fetchLatestList(serviceId);
      if (seq === listSeq.current) {
        setList(next);
        setLoadError(null);
      } else {
        console.debug(
          `[TechDebtWorkspace] discarded stale list load (seq ${seq}, latest ${listSeq.current})`,
        );
      }
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to load list.");
    }
    await refreshOverlap();
    try {
      const deliv = await fetchLatestDeliverable(serviceId);
      setDeliverable(deliv);
    } catch {
      // non-blocking; deliverable section will just show "not finalized yet".
    }
  }, [serviceId, refreshOverlap]);

  React.useEffect(() => {
    void (async () => {
      await refresh();
    })();
  }, [refresh]);

  async function runExtraction(artifactId: string): Promise<void> {
    setExtracting(true);
    setExtractError(null);
    listSeq.current += 1;
    try {
      const next = await extractCapabilities(serviceId, artifactId);
      setList(next);
      await refreshOverlap();
    } catch (err) {
      if (err instanceof TechDebtProxyError) {
        const payload = err.payload as
          { error?: { message?: string }; detail?: string } | undefined;
        setExtractError(
          payload?.error?.message ??
            payload?.detail ??
            `Extraction failed (${err.status}).`,
        );
      } else {
        setExtractError(
          err instanceof Error ? err.message : "Extraction failed.",
        );
      }
    } finally {
      setExtracting(false);
    }
  }

  function onItemUpdate(next: CapabilityItem): void {
    // Optimistic per-row merge; the bump invalidates any in-flight mount load.
    listSeq.current += 1;
    setList((curr) => {
      if (!curr) return curr;
      return {
        ...curr,
        items: curr.items.map((i) => (i.id === next.id ? next : i)),
      };
    });
    // Inline edits change the overlap math; refresh in the background.
    void refreshOverlap();
  }

  async function onApprove(): Promise<void> {
    if (!list) return;
    setApproving(true);
    listSeq.current += 1;
    try {
      const next = await approveCapabilityList(list.id);
      setList(next);
    } finally {
      setApproving(false);
    }
  }

  async function onDiscard(): Promise<void> {
    if (!list) return;
    setDiscarding(true);
    // Bump BEFORE the discard so any in-flight mount fetch still holding the
    // pre-discard draft is invalidated on arrival and can't resurrect it.
    listSeq.current += 1;
    try {
      await discardCapabilityList(list.id);
      // Refetch latest (also bumps the seq): now 404 → empty upload state, or
      // the prior approved version where one exists. Extract is live again.
      await refresh();
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "Failed to discard draft.",
      );
    } finally {
      setDiscarding(false);
    }
  }

  const totalCost =
    list?.items.reduce((acc, i) => acc + (i.annual_cost_usd ?? 0), 0) ?? 0;
  const lowConfidence =
    list?.items.filter(
      (i) => i.confidence_pct !== null && i.confidence_pct < 70,
    ).length ?? 0;
  const readOnly = list?.status === "released";

  const itemCount = list?.items.length ?? 0;
  const discardSummary = `${itemCount} capability item${
    itemCount === 1 ? "" : "s"
  } will be discarded.`;

  const dispositionCounts = (list?.items ?? []).reduce(
    (acc, i) => {
      if (i.disposition) acc[i.disposition] += 1;
      return acc;
    },
    { keep: 0, consolidate: 0, cut: 0 },
  );
  const categoryCount = new Set(
    (list?.items ?? []).map((i) => i.category).filter(Boolean),
  ).size;
  const costFmt = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(totalCost);

  return (
    <div className="flex flex-col gap-6">
      <AiStatusBanner />
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">
            Tech Debt service
          </p>
          <h1 className="text-3xl font-semibold text-ink-primary">
            {serviceTitle}
          </h1>
          <p className="max-w-prose text-sm text-ink-secondary">
            Upload an inventory CSV or XLSX; the AI extracts a structured
            capability list. Edit any cell to clear that row&apos;s AI
            confidence badge and mark it human-curated. Approve when the list is
            ready for the consolidation plan.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {list ? (
            <StatusPill
              tone={list.status === "approved" ? "success" : "info"}
              withDot
            >
              {list.status === "draft"
                ? `Draft v${list.version}`
                : list.status === "approved"
                  ? `Approved v${list.version}`
                  : `Released v${list.version}`}
            </StatusPill>
          ) : (
            <StatusPill tone="neutral" withDot>
              No list yet
            </StatusPill>
          )}
        </div>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Upload inventory and extract</CardTitle>
          <CardDescription>
            Drop the inventory CSV or XLSX. The redactor strips PII before the
            AI sees the rows. Each extraction creates a new versioned list;
            previous versions stay in the audit log.
          </CardDescription>
        </CardHeader>
        <CardBody className="flex flex-col gap-4">
          <RedactionDisclosure />
          <Dropzone
            onUploaded={(a) => {
              setDocsReloadKey((k) => k + 1);
              void runExtraction(a.id);
            }}
            accept=".csv,.xlsx,.xls,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
          />
          {extracting ? (
            <p className="text-sm text-ink-tertiary" aria-live="polite">
              Extracting capability list…
            </p>
          ) : null}
          {extractError ? (
            <p className="text-sm text-status-danger-fg" role="alert">
              {extractError}
            </p>
          ) : null}
        </CardBody>
      </Card>

      <IntakeDocumentsPanel
        onExtract={(id) => void runExtraction(id)}
        extracting={extracting}
        reloadKey={docsReloadKey}
      />

      {loadError ? (
        <Card>
          <CardHeader>
            <CardTitle>Couldn&apos;t load the capability list</CardTitle>
          </CardHeader>
          <CardBody>
            <p className="text-sm text-status-danger-fg">{loadError}</p>
          </CardBody>
        </Card>
      ) : null}

      {list ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          <NumberCard label="Capabilities" value={list.items.length} />
          <NumberCard label="Annual cost" value={costFmt} />
          <NumberCard label="Categories" value={categoryCount} />
          <NumberCard
            label="To consolidate / cut"
            value={dispositionCounts.consolidate + dispositionCounts.cut}
            deltaTone="negative"
          />
          <NumberCard
            label="Low-confidence rows"
            value={lowConfidence}
            hint="AI confidence < 70%"
          />
        </div>
      ) : null}

      {list ? (
        <section aria-labelledby="cap-list" className="flex flex-col gap-3">
          <header className="flex flex-wrap items-end justify-between gap-2">
            <h2
              id="cap-list"
              className="text-lg font-semibold text-ink-primary"
            >
              Capability list v{list.version}
            </h2>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <StatusPill tone="info">{list.items.length} items</StatusPill>
              <StatusPill tone={lowConfidence === 0 ? "success" : "warning"}>
                {lowConfidence === 0
                  ? "All rows ≥ 70% confident"
                  : `${lowConfidence} low-confidence rows`}
              </StatusPill>
              <StatusPill tone="neutral">
                Total cost: ${totalCost.toLocaleString()}
              </StatusPill>
              <button
                type="button"
                onClick={() => void onApprove()}
                disabled={approving || list.status !== "draft"}
                className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {list.status === "approved"
                  ? "Approved"
                  : list.status === "released"
                    ? "Released"
                    : approving
                      ? "Approving…"
                      : "Approve list"}
              </button>
              <DiscardDraftButton
                status={list.status}
                destructionSummary={discardSummary}
                onConfirm={onDiscard}
                disabled={approving || extracting || discarding}
              />
            </div>
          </header>
          <EditableCapabilityTable
            items={list.items}
            onItemUpdate={onItemUpdate}
            readOnly={readOnly}
          />
        </section>
      ) : (
        <EmptyState
          title="No capability list yet"
          description="Upload an inventory above to run the first AI extraction."
        />
      )}

      {list ? (
        <>
          <ConsolidationPlanCard summary={plan} />
          <OverlapDashboard
            analysis={overlap}
            loading={overlapLoading && overlap === null}
            error={overlapError}
          />
          <DeliverableCard
            serviceId={serviceId}
            capabilityListStatus={list.status}
            deliverable={deliverable}
            onChange={setDeliverable}
          />
        </>
      ) : null}
    </div>
  );
}
