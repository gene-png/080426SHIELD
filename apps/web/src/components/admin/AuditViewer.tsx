"use client";
import * as React from "react";

import {
  DataTable,
  EmptyState,
  type DataTableColumn,
} from "@shield/design-system";

import {
  describeAuditError,
  fetchAuditEntries,
  fetchLlmCalls,
  type AuditEntryRow,
  type LlmCallRow,
} from "@/lib/admin/audit";

import type { JSX } from "react";

/**
 * Admin audit viewer (Master Spec §11, Sprint 5 T7): a read-only two-tab window
 * onto the two append-only stores — Activity (audit_entries) and AI calls
 * (llm_calls). There are NO mutation affordances: the stores are append-only
 * (DB trigger + before_flush guard), so this surface only reads and filters.
 *
 * Correlation-id click-through links the tabs: clicking a correlation id in one
 * table pins that id as a filter and jumps to the other tab.
 */

type Tab = "activity" | "ai";

function fmtTime(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

function shortId(value: string | null): string {
  if (!value) return "—";
  return value.length > 8 ? `${value.slice(0, 8)}…` : value;
}

const PAGE = 25;

export function AuditViewer(): JSX.Element {
  const [tab, setTab] = React.useState<Tab>("activity");

  // Shared correlation filter — the click-through link between the two tabs.
  const [correlationId, setCorrelationId] = React.useState("");

  // Activity filters (draft = the inputs, applied = what's fetched).
  const [actionDraft, setActionDraft] = React.useState("");
  const [targetTypeDraft, setTargetTypeDraft] = React.useState("");
  const [activityApplied, setActivityApplied] = React.useState({
    action: "",
    target_type: "",
  });

  // AI filters.
  const [purposeDraft, setPurposeDraft] = React.useState("");
  const [providerDraft, setProviderDraft] = React.useState("");
  const [statusDraft, setStatusDraft] = React.useState("");
  const [aiApplied, setAiApplied] = React.useState({
    purpose: "",
    provider: "",
    status: "",
  });

  const [entries, setEntries] = React.useState<AuditEntryRow[]>([]);
  const [calls, setCalls] = React.useState<LlmCallRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  // Stale-fetch guard (reqSeq): only the newest request may write state.
  const seqRef = React.useRef(0);

  React.useEffect(() => {
    const seq = ++seqRef.current;
    // Wrapped in an async IIFE (same shape as MessageThread) so no setState is
    // called synchronously in the effect body — react-hooks v6
    // set-state-in-effect flags that. Timing is unchanged: the IIFE runs
    // synchronously up to the first await, so the spinner still shows at once.
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        if (tab === "activity") {
          const r = await fetchAuditEntries({
            action: activityApplied.action || undefined,
            target_type: activityApplied.target_type || undefined,
            correlation_id: correlationId || undefined,
            limit: PAGE,
          });
          if (seq === seqRef.current) setEntries(r.entries);
        } else {
          const r = await fetchLlmCalls({
            purpose: aiApplied.purpose || undefined,
            provider: aiApplied.provider || undefined,
            status: aiApplied.status || undefined,
            correlation_id: correlationId || undefined,
            limit: PAGE,
          });
          if (seq === seqRef.current) setCalls(r.calls);
        }
      } catch (err) {
        if (seq === seqRef.current) setError(describeAuditError(err));
      } finally {
        if (seq === seqRef.current) setLoading(false);
      }
    })();
  }, [tab, activityApplied, aiApplied, correlationId]);

  function jumpToCorrelation(target: Tab, id: string | null): void {
    if (!id) return;
    setCorrelationId(id);
    setTab(target);
  }

  const corrLink = (target: Tab, id: string | null): JSX.Element =>
    id ? (
      <button
        type="button"
        onClick={() => jumpToCorrelation(target, id)}
        data-testid="audit-corr-link"
        className="font-mono text-xs text-brand-600 underline decoration-dotted hover:text-brand-700"
        title={id}
      >
        {shortId(id)}
      </button>
    ) : (
      <span className="text-xs text-ink-tertiary">—</span>
    );

  // NOT RECORDED rather than an empty cell, for the reason the redaction
  // column already applies: a blank reads as "nothing was discarded" when it
  // means "nothing was recorded", and those are different facts. An EMPTY
  // object is a THIRD state -- the writer looked and had nothing to say --
  // and is rendered as such rather than folded into either.
  function renderDetails(
    details: Record<string, unknown> | null,
  ): React.ReactNode {
    if (details === null || details === undefined) {
      return <span className="text-ink-tertiary italic">not recorded</span>;
    }
    const pairs = Object.entries(details);
    if (pairs.length === 0) {
      return <span className="text-ink-tertiary italic">none recorded</span>;
    }
    // TRUNCATED, and the cap is not cosmetic.
    //
    // `routes/risk.py`'s audit row carries `rejected_enum_values` and
    // `dropped_link_values` -- RAW MODEL-AUTHORED STRINGS. `_coerce_enum`
    // ends `return None, raw` with `raw = str(value).strip()` and no length
    // bound, and `_record` dedupes without capping either the string or the
    // list. The model was fed the client's own technique and control
    // inventory, so a client-specific name that fails to resolve is stored
    // verbatim.
    //
    // CSF and ZT hold the opposite constraint and TEST it --
    // `test_csf_run_ai_audit_row_carries_counts_but_no_model_content` asserts
    // client content is absent, on the stated ground that the audit row is a
    // durable store outside the artifact mechanism. Whether `risk.py` is
    // exempt is a decision nobody has written down; it is filed, not settled
    // here.
    //
    // What this component can do is refuse to be the surface that makes an
    // unbounded blob a layout problem. The cap is a render boundary, not a
    // fix: the write side is where the constraint belongs.
    const MAX_VALUE = 200;
    const MAX_PAIRS = 24;
    const shown = pairs.slice(0, MAX_PAIRS);
    const render = (v: unknown): string => {
      const text =
        typeof v === "object" && v !== null ? JSON.stringify(v) : String(v);
      return text.length > MAX_VALUE
        ? `${text.slice(0, MAX_VALUE)}… (${text.length} chars)`
        : text;
    };
    return (
      <dl className="font-mono text-xs text-ink-secondary">
        {shown.map(([k, v]) => (
          <div key={k} className="flex gap-1">
            <dt className="text-ink-tertiary">{k}:</dt>
            <dd className="break-all">{render(v)}</dd>
          </div>
        ))}
        {pairs.length > MAX_PAIRS ? (
          <div className="text-ink-tertiary italic">
            and {pairs.length - MAX_PAIRS} more keys not shown
          </div>
        ) : null}
      </dl>
    );
  }

  const activityColumns: DataTableColumn<AuditEntryRow>[] = [
    {
      key: "at",
      header: "When",
      cell: (e) => (
        <span className="whitespace-nowrap text-ink-secondary">
          {fmtTime(e.at)}
        </span>
      ),
    },
    {
      key: "action",
      header: "Action",
      cell: (e) => (
        <span className="font-medium text-ink-primary">{e.action}</span>
      ),
    },
    {
      key: "target",
      header: "Target",
      cell: (e) => (
        <span className="text-ink-secondary">
          {e.target_type}
          {e.target_id ? ` · ${shortId(e.target_id)}` : ""}
        </span>
      ),
    },
    {
      key: "actor",
      header: "Actor",
      cell: (e) => (
        <span className="font-mono text-xs text-ink-tertiary">
          {shortId(e.actor_user_id)}
        </span>
      ),
    },
    {
      key: "details",
      header: "Details",
      // #322. Every discard counter this repo has added lands in `details`:
      // #122's entries_received / entries_written / discarded_entries /
      // entries_write_check, #132's dropped_link_values and
      // entries_unlinked_after_drops, and earlier rejected_enum_values,
      // entries_without_tier, batches_failed.
      //
      // All of it was reachable through /admin/audit-entries and none of it
      // through here -- the row already carried `details` and this component
      // dropped it, so "now visible" was true of the API and false of the UI.
      // A consultant looking at this tab after a run that discarded every
      // entry saw a row identical to a clean one.
      //
      // Rendered as key/value pairs rather than a summary, deliberately: the
      // payload's shape differs per action, and a component that knows which
      // keys matter is a second place to update every time a counter is
      // added. Whatever the API records, a person can read.
      cell: (e) => renderDetails(e.details),
    },
    {
      key: "correlation",
      header: "Correlation",
      cell: (e) => corrLink("ai", e.correlation_id),
    },
  ];

  const aiColumns: DataTableColumn<LlmCallRow>[] = [
    {
      key: "requested_at",
      header: "When",
      cell: (r) => (
        <span className="whitespace-nowrap text-ink-secondary">
          {fmtTime(r.requested_at)}
        </span>
      ),
    },
    {
      key: "purpose",
      header: "Purpose",
      cell: (r) => (
        <span className="font-medium text-ink-primary">{r.purpose}</span>
      ),
    },
    {
      key: "provider",
      header: "Provider",
      cell: (r) => (
        <span className="text-ink-secondary">
          {r.provider} / {r.mode}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (r) => <span className="text-ink-secondary">{r.status}</span>,
    },
    {
      key: "tokens",
      header: "Tokens (in/out)",
      align: "center",
      cell: (r) => (
        <span className="tabular-nums text-ink-secondary">
          {r.input_tokens ?? "—"}/{r.output_tokens ?? "—"}
        </span>
      ),
    },
    {
      key: "redaction",
      header: "Redaction",
      cell: (r) => {
        // Three states, and NULL is not a fourth spelling of "strict". A row
        // written before migration 0046 has an unknown mode, and the column
        // exists to prove what happened -- so it says so rather than guessing.
        if (r.redaction_mode === null) {
          return (
            <span
              className="text-ink-tertiary"
              title="This call predates the redaction-mode column (migration 0046). The mode it ran under was never captured and cannot be recovered."
            >
              not recorded
            </span>
          );
        }
        // `off` means the redactor returned the payload unchanged: client data
        // egressed to the provider verbatim. That is the state #144 exists to
        // make visible, so it is the one state that is styled to be noticed.
        const off = r.redaction_mode === "off";
        return (
          <span
            className={
              off ? "font-semibold text-status-danger-fg" : "text-ink-secondary"
            }
            title={
              off
                ? "The redactor was disabled for this call. The payload reached the provider unredacted."
                : undefined
            }
          >
            {r.redaction_mode}
          </span>
        );
      },
    },
    {
      key: "correlation",
      header: "Correlation",
      cell: (r) => corrLink("activity", r.correlation_id),
    },
  ];

  const tabButton = (id: Tab, label: string): JSX.Element => (
    <button
      type="button"
      onClick={() => setTab(id)}
      data-testid={`audit-tab-${id}`}
      aria-current={tab === id ? "page" : undefined}
      className={
        "rounded-md px-3 py-1.5 text-sm font-medium " +
        (tab === id
          ? "bg-brand-50 text-brand-600"
          : "text-ink-secondary hover:bg-surface-sunken hover:text-ink-primary")
      }
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2" role="tablist">
        {tabButton("activity", "Activity")}
        {tabButton("ai", "AI calls")}
      </div>

      {correlationId ? (
        <div className="flex items-center gap-2 text-xs text-ink-secondary">
          <span>
            Filtered by correlation{" "}
            <span className="font-mono text-ink-primary">{correlationId}</span>
          </span>
          <button
            type="button"
            onClick={() => setCorrelationId("")}
            data-testid="audit-clear-correlation"
            className="rounded border border-border px-2 py-0.5 font-medium text-brand-600 hover:bg-surface-sunken"
          >
            Clear
          </button>
        </div>
      ) : null}

      {tab === "activity" ? (
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setActivityApplied({
              action: actionDraft.trim(),
              target_type: targetTypeDraft.trim(),
            });
          }}
        >
          <label className="flex flex-col gap-1 text-xs text-ink-secondary">
            Action (prefix)
            <input
              value={actionDraft}
              onChange={(e) => setActionDraft(e.target.value)}
              data-testid="audit-filter-action"
              placeholder="e.g. deliverable"
              className="rounded-md border border-border bg-surface-card px-2 py-1 text-sm text-ink-primary"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-secondary">
            Target type
            <input
              value={targetTypeDraft}
              onChange={(e) => setTargetTypeDraft(e.target.value)}
              data-testid="audit-filter-target-type"
              placeholder="e.g. client"
              className="rounded-md border border-border bg-surface-card px-2 py-1 text-sm text-ink-primary"
            />
          </label>
          <button
            type="submit"
            data-testid="audit-apply-activity"
            className="rounded-md bg-brand-500 px-3 py-1.5 text-sm font-semibold text-ink-on-accent hover:bg-brand-600"
          >
            Apply
          </button>
        </form>
      ) : (
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setAiApplied({
              purpose: purposeDraft.trim(),
              provider: providerDraft.trim(),
              status: statusDraft.trim(),
            });
          }}
        >
          <label className="flex flex-col gap-1 text-xs text-ink-secondary">
            Purpose
            <input
              value={purposeDraft}
              onChange={(e) => setPurposeDraft(e.target.value)}
              data-testid="audit-filter-purpose"
              placeholder="e.g. csf_score"
              className="rounded-md border border-border bg-surface-card px-2 py-1 text-sm text-ink-primary"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-secondary">
            Provider
            <input
              value={providerDraft}
              onChange={(e) => setProviderDraft(e.target.value)}
              data-testid="audit-filter-provider"
              placeholder="e.g. anthropic"
              className="rounded-md border border-border bg-surface-card px-2 py-1 text-sm text-ink-primary"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-secondary">
            Status
            <input
              value={statusDraft}
              onChange={(e) => setStatusDraft(e.target.value)}
              data-testid="audit-filter-status"
              placeholder="e.g. completed"
              className="rounded-md border border-border bg-surface-card px-2 py-1 text-sm text-ink-primary"
            />
          </label>
          <button
            type="submit"
            data-testid="audit-apply-ai"
            className="rounded-md bg-brand-500 px-3 py-1.5 text-sm font-semibold text-ink-on-accent hover:bg-brand-600"
          >
            Apply
          </button>
        </form>
      )}

      {loading ? (
        <p className="text-sm text-ink-tertiary">Loading…</p>
      ) : error ? (
        <p className="text-sm text-status-danger-fg" role="alert">
          {error}
        </p>
      ) : tab === "activity" ? (
        <div data-testid="audit-activity-table">
          <DataTable
            caption="Append-only activity log — read-only."
            columns={activityColumns}
            rows={entries}
            rowKey={(e) => e.id}
            emptyState={
              <EmptyState
                title="No activity"
                description="No audit entries match these filters."
              />
            }
          />
        </div>
      ) : (
        <div data-testid="audit-ai-table">
          <DataTable
            caption="Append-only AI egress log — read-only."
            columns={aiColumns}
            rows={calls}
            rowKey={(r) => r.id}
            emptyState={
              <EmptyState
                title="No AI calls"
                description="No AI egress rows match these filters."
              />
            }
          />
        </div>
      )}
    </div>
  );
}
