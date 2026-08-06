"use client";
import * as React from "react";

import { fulfillServiceRequest } from "@/lib/admin/client";

/**
 * Create several workspaces in one action (UX finding 15).
 *
 * An intake with four services meant four separate publish actions, each of
 * which had to be found on its own card further down the page. That is not just
 * tedious — it makes PARTIAL processing likely, where two services are opened
 * and two are quietly forgotten, and nothing on the page says so.
 *
 * Individual publish controls stay on every card. Bulk is for the common case,
 * not a replacement: a request that needs a closer look before publishing still
 * gets one.
 */

export interface BulkPublishBarProps {
  /** Requests eligible for bulk publish — no workspace yet, not declined. */
  eligibleIds: string[];
  selected: Set<string>;
  onSelectionChange: (next: Set<string>) => void;
  onPublished: () => void;
}

export function BulkPublishBar({
  eligibleIds,
  selected,
  onSelectionChange,
  onPublished,
}: BulkPublishBarProps): React.ReactElement | null {
  const [busy, setBusy] = React.useState(false);
  const [failures, setFailures] = React.useState<string[]>([]);
  const [done, setDone] = React.useState<number | null>(null);

  // One eligible request needs no bulk affordance — its own card already has
  // the button, and a "select all" over a single item is noise.
  if (eligibleIds.length < 2) return null;

  const allSelected = eligibleIds.every((id) => selected.has(id));
  const count = eligibleIds.filter((id) => selected.has(id)).length;

  function toggleAll(checked: boolean): void {
    onSelectionChange(checked ? new Set(eligibleIds) : new Set());
    setDone(null);
    setFailures([]);
  }

  async function publishSelected(): Promise<void> {
    setBusy(true);
    setFailures([]);
    setDone(null);
    const failed: string[] = [];
    let succeeded = 0;

    // Sequential on purpose. Each publish opens a workspace and writes an audit
    // row; firing them at once makes the failure story ambiguous, and there are
    // at most a handful.
    for (const id of eligibleIds.filter((i) => selected.has(i))) {
      try {
        await fulfillServiceRequest(id);
        succeeded += 1;
      } catch {
        failed.push(id);
      }
    }

    setBusy(false);
    setDone(succeeded);
    setFailures(failed);
    // Keep the ones that failed selected so a retry is one click, and clear the
    // rest. Reporting "3 of 4" and leaving all four ticked would invite
    // re-publishing the three that already worked.
    onSelectionChange(new Set(failed));
    onPublished();
  }

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border border-border-subtle bg-surface-sunken px-4 py-3">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={allSelected}
          onChange={(e) => toggleAll(e.target.checked)}
          disabled={busy}
        />
        <span className="text-ink-secondary">
          Select all {eligibleIds.length} without a workspace
        </span>
      </label>

      <button
        type="button"
        onClick={() => void publishSelected()}
        disabled={busy || count === 0}
        className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {busy
          ? "Creating…"
          : `Create ${count === 0 ? "" : count + " "}selected workspace${count === 1 ? "" : "s"}`}
      </button>

      {/* FAIL LOUDLY: a partial run has to name what did not happen, or the
          page looks identical to a clean run and two services sit unopened. */}
      <span role="status" className="text-sm">
        {failures.length > 0 ? (
          <span className="font-medium text-status-danger-fg">
            {done} created, {failures.length} failed — the failed ones are still
            selected. Try again, or publish them individually to see the error.
          </span>
        ) : done !== null ? (
          <span className="text-status-success-fg">
            {done} workspace{done === 1 ? "" : "s"} created.
          </span>
        ) : null}
      </span>
    </div>
  );
}
