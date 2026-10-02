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
import { hasAcknowledgedOffline, useAiStatus } from "@/lib/admin/aiStatus";
import type { AiServes } from "@/lib/aiRuns/types";
import { useAiRun } from "@/lib/aiRuns/useAiRun";
import { AiRunStatus } from "@/components/admin/AiRunStatus";
import { splitLines } from "@/lib/text";
import { RedactionDisclosure } from "@/components/intake/RedactionDisclosure";
import {
  addCapabilityComponents,
  bulkSetDisposition,
  confirmExcludedRow,
  includeExcludedRow,
  approveCapabilityList,
  discardCapabilityList,
  extractCapabilities,
  fetchTechDebtRun,
  fetchTechDebtRunSummary,
  fetchConsolidationPlan,
  fetchLatestDeliverable,
  fetchLatestList,
  fetchOverlapAnalysis,
  proxyMessage,
  TechDebtProxyError,
} from "@/lib/tech_debt/client";
import type { TechDebtRun } from "@/lib/tech_debt/client";
import type {
  CapabilityDisposition,
  CapabilityItem,
  ExcludedRow,
  CapabilityList,
  ConsolidationPlanSummary,
  Deliverable,
  OverlapAnalysis,
} from "@/lib/tech_debt/types";
import { draftSourceArtifactId } from "@/lib/tech_debt/draftSource";

import { ConsolidationPlanCard } from "./ConsolidationPlanCard";
import { DeliverableCard } from "./DeliverableCard";
import { WorkflowStep } from "@/components/admin/WorkflowStep";
import { DiscardDraftButton } from "./DiscardDraftButton";
import { DispositionHelp } from "./DispositionHelp";
import { EditableCapabilityTable } from "./EditableCapabilityTable";
import { IntakeDocumentsPanel } from "./IntakeDocumentsPanel";
import { OverlapDashboard } from "./OverlapDashboard";

import type { JSX } from "react";
import { ProgressStages } from "./ProgressStages";
import { SecurityClassificationQueue } from "./SecurityClassificationQueue";
import { useServiceStages } from "@/lib/stages/client";
import { useRefreshFailures } from "@/components/admin/useRefreshFailures";
import { isUpstreamOutcomeUnknown } from "@/lib/describe-save-error";

/**
 * #550: what to say when the proxy never saw the extraction's answer. Not a
 * failure: #550 measured the api finishing anyway and creating the draft, and
 * a retry sends the client's inventory out again. Names where the draft would
 * appear and that extraction stays off.
 */
const EXTRACT_OUTCOME_UNKNOWN =
  "We couldn't confirm whether the extraction finished. It may still complete and create a draft capability list. Reload the page later and check step 2, Review and correct the extracted list, before extracting again. Extracting stays off on this page until you reload.";

export interface TechDebtWorkspaceProps {
  serviceId: string;
  serviceTitle: string;
}

/**
 * #177/#193: whether the list's excluded count is unknown, from the api's one
 * reader (`exclusion_count_state`). Absent reads as unknown when a
 * reconciliation is on record: never as exact by default.
 */
function exclusionUnknown(list: CapabilityList): boolean {
  if (typeof list.source_rows_total !== "number") return false;
  return list.exclusion_count_state !== "exact";
}

/** "N rows received · M included · K excluded", or, when the count is
 *  unknown, "… · excluded count unknown (at least K)" -- K is a floor then. */
function reconciliationHeading(list: CapabilityList): string {
  const received = list.source_rows_total ?? 0;
  const included = list.items.filter((i) => !i.parent_item_id).length;
  const floor = Math.max(received - included, 0);
  const head = `${received} rows received · ${included} included · `;
  if (exclusionUnknown(list)) {
    return `${head}excluded count unknown${floor > 0 ? ` (at least ${floor})` : ""}`;
  }
  return `${head}${floor} excluded`;
}

export function TechDebtWorkspace({
  serviceId,
  serviceTitle,
}: TechDebtWorkspaceProps): JSX.Element {
  const [list, setList] = React.useState<CapabilityList | null>(null);
  // Derived six-stage progress. Re-reads when this workspace's own
  // state moves, since the derivation is computed from that same state.
  const { phase: stagesPhase, stages: serviceStages } = useServiceStages(
    serviceId,
    `${list?.status ?? ""}:${list?.version ?? ""}`,
  );
  const [overlap, setOverlap] = React.useState<OverlapAnalysis | null>(null);
  const [overlapError, setOverlapError] = React.useState<string | null>(null);
  const [overlapLoading, setOverlapLoading] = React.useState(false);
  const [plan, setPlan] = React.useState<ConsolidationPlanSummary | null>(null);
  const [deliverable, setDeliverable] = React.useState<Deliverable | null>(
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
   * opposite directions; see `useRefreshFailures`. This file never cleared,
   * and its plan-refresh write was also the one unguarded write in a function
   * whose every other write is sequence-guarded -- see `refreshOverlap`.
   */
  const { messages: refreshMessages, begin: beginRefresh } =
    useRefreshFailures();
  const { settled: aiSettled } = useAiStatus();
  const [extracting, setExtracting] = React.useState(false);
  const [splitError, setSplitError] = React.useState<string | null>(null);
  const [extractError, setExtractError] = React.useState<string | null>(null);
  // #550: set once an extraction's outcome is unknown and never cleared; a
  // reload clears it, which the copy says. The ref is what `runExtraction`
  // reads, because the upload's automatic extraction calls it from a closure
  // created before the state changed.
  const [extractOutcomeUnknown, setExtractOutcomeUnknown] =
    React.useState(false);
  const extractLocked = React.useRef(false);
  const [approveError, setApproveError] = React.useState<string | null>(null);
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
    // BOTH sequence numbers are taken HERE, before any await, and the token is
    // one of them. See `useRefreshFailures`: minting after an await orders the
    // tokens by RESOLUTION rather than by INVOCATION, which inverts the guard
    // for exactly the interleaving it exists to stop. The first version of
    // this fix minted it below the overlap fetch and was weaker than the
    // hand-rolled `seq` it replaced.
    const seq = ++overlapSeq.current;
    const overlapAttempt = beginRefresh("overlap-plan");
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
      if (seq === overlapSeq.current) {
        setPlan(nextPlan);
      }
      // The hook sequences this one itself now. `seq` still guards `setPlan`
      // above, because that is component state the hook knows nothing about.
      overlapAttempt.clear();
    } catch {
      // NON-BLOCKING IS NOT SILENT. The old comment was true and is
      // why this survived: a panel's own loading state cannot be told
      // apart from a slow network.
      //
      // SEQUENCE-GUARDED, and the guard now lives in the hook rather than
      // here. An edit fires refresh #1; a second edit ~200ms later fires #2,
      // which completes, so `plan` is current and correct; #1 then rejects.
      // An unguarded write put a permanent "may be out of date" warning over
      // figures that were up to date -- a superseded request describing the
      // state of a newer one.
      //
      // This was the ONLY guarded write in the first version of the fix, and
      // the review found every other one unguarded. A rule applied at four
      // sites diverges at four sites, so it moved into `useRefreshFailures`
      // and there is no longer an unsequenced way to write.
      overlapAttempt.note(
        "Couldn't refresh the overlap figures. What is shown may be out of date.",
      );
    }
  }, [serviceId, beginRefresh]);

  const refresh = React.useCallback(async () => {
    // Before any await, for the reason above. This one sat below TWO of them
    // -- `fetchLatestList` and the whole of `refreshOverlap` -- so a mount
    // whose list fetch was slow could mint its deliverable token after a later
    // `refresh` had already minted and cleared one.
    const seq = ++listSeq.current;
    const deliverableAttempt = beginRefresh("deliverable");
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
      deliverableAttempt.clear();
    } catch {
      // A FALSE NEGATIVE, not an ambiguity: the old comment stated
      // the defect as if it were the mitigation. "Not finalized yet"
      // is a claim ABOUT THE SERVER made on the strength of a request
      // that failed, and a consultant can act on it by finalizing a
      // second time. Missing data defaults to UNCONFIRMED, never to a
      // known negative.
      deliverableAttempt.note(
        "Couldn't check for a finalized deliverable. The section below is not a statement about whether one exists.",
      );
    }
  }, [serviceId, refreshOverlap, beginRefresh]);

  React.useEffect(() => {
    void (async () => {
      await refresh();
    })();
  }, [refresh]);

  /**
   * UX finding 5: a bundled licence such as Microsoft 365 E5 extracted as one
   * line, hiding the Defender / Entra capabilities that overlap separately
   * licensed tools. The CONSULTANT names what is inside — the model is never
   * asked, because inventing bundle contents is exactly the fabricated detail
   * the AI seam exists to prevent.
   */
  /**
   * UX finding 4 (second half): disclosure alone told the consultant nine rows
   * were dropped without letting them do anything about it. A row the extractor
   * wrongly skipped is recoverable; one it correctly skipped can be
   * acknowledged so it stops reading as outstanding.
   */
  async function onIncludeRow(row: ExcludedRow): Promise<void> {
    if (!list) return;
    const name = window.prompt(
      `Include this row as a capability?

${row.summary}

Name it:`,
      "",
    );
    if (name === null || !name.trim()) return;
    const category = window.prompt("Category (optional):", "") ?? undefined;
    setSplitError(null);
    // Every list-producing operation bumps `listSeq`, so an earlier read still
    // in flight (mount, or the post-edit re-read) cannot overwrite this result.
    listSeq.current += 1;
    try {
      setList(
        await includeExcludedRow(list.id, row.index, {
          name: name.trim(),
          category: category?.trim() || undefined,
        }),
      );
    } catch (err) {
      setSplitError(
        err instanceof Error ? err.message : "Couldn't include that row.",
      );
    }
  }

  async function onConfirmRow(row: ExcludedRow): Promise<void> {
    if (!list) return;
    setSplitError(null);
    listSeq.current += 1;
    try {
      setList(await confirmExcludedRow(list.id, row.index));
    } catch (err) {
      setSplitError(
        err instanceof Error ? err.message : "Couldn't confirm that row.",
      );
    }
  }

  async function onSplitBundle(item: CapabilityItem): Promise<void> {
    const raw = window.prompt(
      `What does "${item.name}" include?

One capability per line, e.g.
Microsoft Defender for Endpoint
Microsoft Entra ID P2

Components carry no cost of their own — this licence keeps its full value.`,
      "",
    );
    if (raw === null) return;
    const names = splitLines(raw);
    if (names.length === 0) return;
    setSplitError(null);
    listSeq.current += 1;
    try {
      const next = await addCapabilityComponents(
        item.id,
        names.map((name) => ({ name })),
      );
      setList(next);
    } catch (err) {
      setSplitError(
        err instanceof Error ? err.message : "Couldn't add components.",
      );
    }
  }

  // #645. An extraction found in progress on load ends here: read the list it
  // wrote, as `runExtraction` does for one this page started.
  const onRunFinishedElsewhere = React.useCallback(
    (run: TechDebtRun) => {
      if (run.status !== "completed") return;
      const seq = ++listSeq.current;
      void fetchLatestList(serviceId)
        .then((next) => {
          if (seq === listSeq.current) setList(next);
          return refreshOverlap();
        })
        .catch((err: unknown) =>
          setExtractError(
            proxyMessage(
              err,
              "The extraction finished, but its list could not be loaded. Reload to see it.",
            ),
          ),
        );
    },
    [serviceId, refreshOverlap],
  );
  const aiRun = useAiRun({
    serviceId,
    fetchSummary: fetchTechDebtRunSummary,
    fetchRun: fetchTechDebtRun,
    onFinished: onRunFinishedElsewhere,
  });

  // Artifacts whose extraction has started on this page. The upload's
  // deferred auto-extraction consults it: a user who clicked "Extract from
  // this" while the AI status was still settling must not get a second
  // extraction once it settles (found by the e2e suite on #472).
  const extractionStarted = React.useRef(new Set<string>());

  async function runExtraction(
    artifactId: string,
    serves: AiServes,
  ): Promise<void> {
    if (extractLocked.current) {
      console.warn(
        `[tech-debt] not extracting ${artifactId}: an earlier extraction's outcome is unknown (#550)`,
      );
      return;
    }
    extractionStarted.current.add(artifactId);
    setExtracting(true);
    setExtractError(null);
    const seq = ++listSeq.current;
    try {
      const answer = await extractCapabilities(serviceId, artifactId, serves);
      if ("run_id" in answer) {
        // #645: a run. The list exists once it completes; a failed run's
        // reason is `AiRunStatus`'s to show.
        const finished = await aiRun.follow(answer);
        if (finished.status !== "completed") return;
        // A separate try (#550 review, finding 1): only the POST's own
        // rejection can mean the extraction's outcome is unknown. This read
        // happens after the run is known to have completed.
        try {
          const next = await fetchLatestList(serviceId);
          if (seq === listSeq.current) setList(next);
        } catch (err) {
          setExtractError(
            proxyMessage(
              err,
              "The extraction finished, but its list could not be loaded. Reload to see it.",
            ),
          );
          return;
        }
      } else {
        // The open draft from this same document, returned as it stands.
        setList(answer);
      }
      await refreshOverlap();
    } catch (err) {
      if (isUpstreamOutcomeUnknown(err)) {
        extractLocked.current = true;
        setExtractOutcomeUnknown(true);
        // #645: a run may have started. Look once, and follow it if so; the
        // lock and the copy above stand either way.
        void aiRun.reconcile();
      } else if (err instanceof TechDebtProxyError) {
        setExtractError(
          proxyMessage(err, `Extraction failed (${err.status}).`),
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

  async function onBulkDisposition(
    itemIds: string[],
    disposition: CapabilityDisposition | null,
  ): Promise<void> {
    if (!list) return;
    listSeq.current += 1;
    let next: CapabilityList;
    try {
      next = await bulkSetDisposition(list.id, itemIds, disposition);
    } catch (err) {
      // Rethrown, not swallowed: the TABLE owns this refusal's display (beside
      // the bulk bar, with the selection kept for a retry), and a rejection is
      // how it learns nothing was applied. Logged here so the refusal is on
      // record even if a future caller forgets to render it.
      console.warn(
        `[TechDebtWorkspace] bulk disposition refused: ${proxyMessage(err, "no message")}`,
      );
      throw err;
    }
    setList(next);
    // Dispositions drive the consolidation plan; refresh it in the background.
    void refreshOverlap();
  }

  function onItemUpdate(next: CapabilityItem): void {
    // Optimistic per-row merge; the bump invalidates any in-flight mount load.
    listSeq.current += 1;
    const wasApproved = list?.status === "approved";
    setList((curr) => {
      if (!curr) return curr;
      return {
        ...curr,
        items: curr.items.map((i) => (i.id === next.id ? next : i)),
      };
    });
    // Inline edits change the overlap math; refresh in the background.
    void refreshOverlap();
    // #640, advisor review of #730 (F2): the PATCH answers with one item and no
    // approval state, so an edit to an APPROVED list would leave step 3 showing
    // "Approved" and disabled while finalize refuses the stale approval. Only
    // the server knows whether the edit made the approval stale (locking a row
    // does not), so re-read the list rather than guessing here.
    if (wasApproved) void reloadListAfterEdit();
  }

  async function reloadListAfterEdit(): Promise<void> {
    // Minted before the await, like `refresh`: a later list-producing
    // operation (another edit, approve) must win over this read.
    const seq = ++listSeq.current;
    const attempt = beginRefresh("approval-after-edit");
    try {
      const fresh = await fetchLatestList(serviceId);
      if (seq === listSeq.current) {
        setList(fresh);
      } else {
        console.debug(
          `[TechDebtWorkspace] discarded stale post-edit list read (seq ${seq}, latest ${listSeq.current})`,
        );
      }
      attempt.clear();
    } catch (err) {
      // Not swallowed: the page still shows the pre-edit approval state, so
      // say it could not be confirmed. Non-blocking (the edit itself saved),
      // and finalize refuses a stale approval on the server either way.
      attempt.note(
        `Your edit was saved, but the approval state could not be re-checked (${proxyMessage(err, "the list could not be reloaded")}). Reload the page before step 4.`,
      );
    }
  }

  async function onApprove(): Promise<void> {
    if (!list) return;
    setApproving(true);
    setApproveError(null);
    // Minted before the await. Approve's response is the only list a write
    // returns that can say "approved and current", so it must not land over a
    // newer operation: an edit committed after the approve makes that answer
    // stale (independent review of #730, finding 4). Overtaken, it is not
    // applied and the list is read again, so the server decides what shows.
    const seq = ++listSeq.current;
    try {
      const next = await approveCapabilityList(list.id);
      if (seq === listSeq.current) {
        setList(next);
      } else {
        console.debug(
          `[TechDebtWorkspace] approve response overtaken (seq ${seq}, latest ${listSeq.current}); re-reading the list`,
        );
        await refresh();
      }
    } catch (err) {
      // The 409 the API raises when the list was discarded carries a typed
      // `{reason, message}` naming the remedy that exists ("upload a
      // replacement list"). This handler had no `catch` at all -- the only
      // mutating handler in the file without one -- so the promise rejected
      // unhandled, the button went from "Approving..." back to "Approve list",
      // and the consultant was shown nothing. `TechDebtProxyError.message` is
      // "Tech-debt proxy 409", so `err.message` would not have surfaced it
      // either: the message is on the payload.
      setApproveError(proxyMessage(err, "Approving the list failed."));
      // And re-read the list rather than keeping the stale one. The button is
      // enabled on `list.status === "draft"`, which is exactly the value that
      // has just been proved wrong; without this the consultant can click it
      // again forever.
      await refresh();
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
      // The extract refusal (#644) names "Discard draft" as its remedy. Once
      // that has succeeded, a red alert still saying a draft is open would
      // contradict the screen (#691 round 1).
      setExtractError(null);
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
  // #640. The approval holds while the list is RELEASED, or APPROVED with no
  // step-2 edit since (`approval_current`). An APPROVED list edited afterwards
  // is stale: step 3 shows not-done and offers "Approve again".
  const approvalHolds =
    list?.status === "released" ||
    (list?.status === "approved" && list.approval_current);
  const approvalStale = list?.status === "approved" && !list.approval_current;
  const approvable = list?.status === "draft" || list?.status === "approved";

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
              tone={
                // `released` is approved-or-better, so it reads "success" like
                // its siblings do. Previously unreachable, so a released list
                // showed a blue "info" pill saying "Released".
                approvalHolds ? "success" : approvalStale ? "warning" : "info"
              }
              withDot
            >
              {list.status === "draft"
                ? `Draft v${list.version}`
                : approvalStale
                  ? `Edited since approval v${list.version}`
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

      {stagesPhase === "ready" && serviceStages ? (
        <ProgressStages
          stages={serviceStages.stages}
          kind={serviceStages.kind}
          version={serviceStages.version}
        />
      ) : null}

      {/* Ordered and labelled the way the work is done. The sequence here was
          already close to right; what was missing was any statement of what to
          do first, what each stage is for, or what "done" looks like. Analysis
          output (consolidation plan, overlap) moves below the numbered path. */}
      <WorkflowStep
        number={1}
        title="Upload the inventory and extract"
        description="Drop the client's software inventory. The redactor strips PII before anything leaves the platform, then Claude extracts one capability per row. Rows it cannot name are reported as exclusions rather than silently dropped."
        done={list !== null}
      >
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
                // Issue 2: uploading auto-started an AI extraction with no click
                // to intercept, so an offline run could produce canned output
                // unannounced. When AI is not live (and the admin hasn't already
                // acknowledged it) the file is just listed — the guarded
                // "Extract from this" button below is then the way in.
                //
                // #509: decided on a SETTLED status. This read `status`, null
                // while the request is in flight, and a null ran the extraction
                // -- reachable since #472 made the first status read slow. A
                // status that cannot be read at all does not auto-run either;
                // the guarded button remains, and it too is off until a status
                // read succeeds (#645: RunAiGuard fails closed).
                void aiSettled().then((s) => {
                  if (s === null) {
                    console.warn(
                      "[tech-debt] AI status unreadable; not auto-extracting",
                    );
                    return;
                  }
                  if (!s.ready && !hasAcknowledgedOffline(s)) return;
                  if (extractionStarted.current.has(a.id)) return;
                  void runExtraction(a.id, s.ready ? "live" : "offline");
                });
              }}
              accept=".csv,.xlsx,.xls,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
            />
            <AiRunStatus run={aiRun} />
            {extracting && !aiRun.running ? (
              <p className="text-sm text-ink-tertiary" aria-live="polite">
                Extracting capability list…
              </p>
            ) : null}
            {extractError ? (
              <p className="text-sm text-status-danger-fg" role="alert">
                {extractError}
              </p>
            ) : null}
            {extractOutcomeUnknown ? (
              <p className="text-sm text-status-warning-fg" role="alert">
                {EXTRACT_OUTCOME_UNKNOWN}
              </p>
            ) : null}
          </CardBody>
        </Card>

        <IntakeDocumentsPanel
          onExtract={(id, serves) => void runExtraction(id, serves)}
          extracting={extracting || aiRun.running !== null}
          extractBlocked={extractOutcomeUnknown}
          reloadKey={docsReloadKey}
          draftSourceId={draftSourceArtifactId(list)}
        />
      </WorkflowStep>

      {refreshMessages.length > 0 ? (
        <div
          className="space-y-2 rounded-md border border-status-warning-border bg-status-warning-bg p-3 text-sm text-status-warning-fg"
          role="status"
          data-testid="techdebt-refresh-error"
        >
          {refreshMessages.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      ) : null}

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
        <WorkflowStep
          number={2}
          title="Review and correct the extracted list"
          description="Check what the extraction produced against what the client actually runs: fix names and costs, split bundles into their components, and confirm or overturn the security classification on each row. That classification decides what the ATT&CK mapping is allowed to cite, so an error here becomes a fabricated gap there."
          done={approvalHolds}
        >
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
                <DiscardDraftButton
                  status={list.status}
                  destructionSummary={discardSummary}
                  onConfirm={onDiscard}
                  disabled={approving || extracting || discarding}
                />
              </div>
            </header>

            {/* Sign-off queue for negative security classifications. The
              extraction is portfolio-wide, so the security call is a property
              of each row rather than a filter — and it decides what ATT&CK may
              cite. Nothing leaves that subset without a human agreeing. */}
            <SecurityClassificationQueue
              list={list}
              onUpdated={(next) => {
                listSeq.current += 1;
                setList(next);
              }}
              // #640: classifications stay editable until release; an edit
              // to an approved list sends step 3 back to not-done.
              editable={list.status === "draft" || list.status === "approved"}
            />

            {/* UX finding 4: rows the extraction could not turn into a
              capability at all — notes, headers, duplicates. Rare now that the
              prompt keeps the whole portfolio, but "rare" is not "never", and
              reporting the survivors as the portfolio hid 45% of the uploaded
              spend in the 2026-08-04 review. */}
            {/* Gate on the exclusion RECORD, not on a count comparison. The old
              test was `source_rows_total > items.length`, which used "fewer
              items than source rows" as a proxy for "rows were excluded".
              Splitting a bundle ADDS child items — 26 became 32 against 28
              source rows — so `28 > 32` went false and this whole block
              unmounted, permanently. The disclosure disappeared exactly when a
              consultant used a first-class feature, and stayed gone across a
              reload (2026-08-07 review). Excluded rows are what makes this
              honest; count them directly.

              `included` likewise counts SOURCE-derived rows only, so
              decomposition can never move the reconciliation arithmetic. */}
            {/* Gate on the DERIVED count, not on the named list. `reconcile.py`
              withholds the names when the provider did not attribute every item
              to a source row — so `excluded_rows` is empty in exactly the case
              where rows WERE excluded and nobody can say which, and measuring
              the named list concluded nothing was excluded. That is the
              2026-08-04 defect reachable through the mechanism added to prevent
              it. The count is `received - source-derived items`, which is exact
              only when attribution was complete; otherwise it is a floor and
              the box says the count is unknown (#193, `exclusionUnknown`). The
              exporter decides it the same way. */}
            {typeof list.source_rows_total === "number" &&
            (exclusionUnknown(list) ||
              list.source_rows_total -
                list.items.filter((i) => !i.parent_item_id).length >
                0) ? (
              <div
                className="rounded-md border border-status-warning-border bg-status-warning-bg p-3 text-sm"
                role="status"
                aria-label="Extraction reconciliation"
              >
                <p className="font-semibold text-status-warning-fg">
                  {reconciliationHeading(list)}
                </p>
                {exclusionUnknown(list) ? (
                  <p className="mt-1 text-ink-secondary">
                    The AI could not match every extracted capability to one
                    uploaded row, so the excluded rows cannot be listed and how
                    many there were is not known exactly.
                  </p>
                ) : null}
                <p className="mt-1 text-ink-secondary">
                  Totals below cover the included rows only, not the whole
                  upload.
                </p>
                {list.excluded_rows && list.excluded_rows.length > 0 ? (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs font-medium text-ink-tertiary hover:text-ink-secondary">
                      Show the {list.excluded_rows.length} excluded row
                      {list.excluded_rows.length === 1 ? "" : "s"}
                    </summary>
                    <ul className="mt-2 flex flex-col gap-1">
                      {list.excluded_rows.map((row) => (
                        <li
                          key={row.index}
                          className="flex flex-wrap items-center gap-2 text-xs text-ink-secondary"
                        >
                          <span className="font-mono text-ink-tertiary">
                            row {row.index + 1}
                          </span>
                          <span className="min-w-0 flex-1">{row.summary}</span>
                          {row.confirmed ? (
                            <span className="text-status-success-fg">
                              ✓ correctly excluded
                            </span>
                          ) : readOnly ? null : (
                            <>
                              <button
                                type="button"
                                onClick={() => void onIncludeRow(row)}
                                className="font-medium text-brand-600 underline hover:text-brand-700"
                              >
                                Include…
                              </button>
                              <button
                                type="button"
                                onClick={() => void onConfirmRow(row)}
                                className="text-ink-tertiary underline hover:text-ink-secondary"
                              >
                                Correctly excluded
                              </button>
                            </>
                          )}
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : (
                  <p className="mt-1 text-xs text-ink-tertiary">
                    The provider did not attribute every capability to a source
                    row, so the excluded rows can&apos;t be listed individually.
                  </p>
                )}
              </div>
            ) : null}
            <DispositionHelp />
            <EditableCapabilityTable
              items={list.items}
              onItemUpdate={onItemUpdate}
              onBulkDisposition={readOnly ? undefined : onBulkDisposition}
              readOnly={readOnly}
              onSplitBundle={readOnly ? undefined : onSplitBundle}
            />
            {splitError ? (
              <p className="text-sm text-status-danger-fg" role="alert">
                {splitError}
              </p>
            ) : null}
          </section>
        </WorkflowStep>
      ) : (
        <EmptyState
          title="No capability list yet"
          description="Upload an inventory above to run the first AI extraction."
        />
      )}

      {list ? (
        <>
          <WorkflowStep
            number={3}
            title="Approve the capability list"
            description="Records that the inventory was reviewed, so the deliverable is generated from rows a consultant signed off. Any later edit in step 2 means approving again. Approving does not send anything to the client — that is the last step."
            done={approvalHolds}
          >
            <button
              type="button"
              onClick={() => void onApprove()}
              disabled={approving || !approvable || approvalHolds}
              className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {list.status === "released"
                ? "Released"
                : approving
                  ? "Approving…"
                  : approvalHolds
                    ? "Approved"
                    : approvalStale
                      ? "Approve again"
                      : "Approve list"}
            </button>
            {approveError ? (
              <p className="mt-2 text-sm text-status-danger-fg" role="alert">
                {approveError}
              </p>
            ) : null}
          </WorkflowStep>

          <WorkflowStep
            number={4}
            title="Generate and release the deliverable"
            description="Renders the PDF, XLSX and DOCX from the approved list. Nothing reaches the client until you release it — generating is safe, releasing is the point of no return."
            blockedReason={
              list.status === "draft"
                ? "Approve the capability list in step 3 before generating a deliverable from it."
                : approvalStale
                  ? "The list was edited after it was approved. Approve it again in step 3 before generating a deliverable from it."
                  : null
            }
          >
            <DeliverableCard
              serviceId={serviceId}
              capabilityListStatus={list.status}
              deliverable={deliverable}
              onChange={setDeliverable}
            />
          </WorkflowStep>

          {/* Reference, not steps: analysis output, useful throughout. */}
          <ConsolidationPlanCard summary={plan} />
          <OverlapDashboard
            analysis={overlap}
            loading={overlapLoading && overlap === null}
            error={overlapError}
          />
        </>
      ) : null}
    </div>
  );
}
