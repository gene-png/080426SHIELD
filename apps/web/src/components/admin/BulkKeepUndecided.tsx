"use client";
import * as React from "react";

import { Modal } from "@shield/design-system";

import { proxyMessage } from "@/lib/tech_debt/client";
import type { CapabilityItem } from "@/lib/tech_debt/types";

import type { JSX } from "react";

/**
 * TD-11 (for #1055): keep every undecided row in one step.
 *
 * Copy approved on #736 (6205607786, ruled 6206818759 item 6): the button,
 * the confirm question, and the bulk bar's existing result line. "Cancel" and
 * the failure fallback are the app's existing strings (DiscardDraftButton,
 * EditableCapabilityTable).
 *
 * The rows sent are exactly the ones undecided on this page, bundle parts
 * included (a part carries its own disposition), with `only_if_undecided`, so
 * a row another consultant decided since this page loaded refuses the whole
 * request rather than being overwritten.
 */
export function keepUndecidedLabel(n: number): string {
  return n === 1 ? "Keep 1 undecided row" : `Keep ${n} undecided rows`;
}

export function keepUndecidedQuestion(n: number): string {
  return n === 1
    ? "Set 1 undecided row to Keep? Rows that already have a decision are not changed."
    : `Set ${n} undecided rows to Keep? Rows that already have a decision are not changed.`;
}

export function BulkKeepUndecided({
  items,
  editable,
  disabled = false,
  onKeep,
}: {
  items: readonly CapabilityItem[];
  editable: boolean;
  disabled?: boolean;
  /** Sends `ids` as Keep with `only_if_undecided`; rejects when refused. */
  onKeep: (ids: string[]) => Promise<void>;
}): JSX.Element | null {
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<{
    kind: "done" | "error";
    text: string;
  } | null>(null);
  const undecided = items.filter((i) => i.disposition === null);
  const n = undecided.length;
  if (!editable || (n === 0 && result === null)) return null;

  async function confirm(): Promise<void> {
    const ids = undecided.map((i) => i.id);
    setBusy(true);
    setResult(null);
    try {
      await onKeep(ids);
      console.debug(`[BulkKeepUndecided] kept ${ids.length} undecided rows`);
      setResult({
        kind: "done",
        text: `Set ${ids.length} ${ids.length === 1 ? "row" : "rows"} to Keep.`,
      });
      setOpen(false);
    } catch (err) {
      setResult({
        kind: "error",
        text: proxyMessage(
          err,
          "Couldn't apply the disposition. Nothing was changed.",
        ),
      });
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      {n > 0 ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          disabled={disabled || busy}
          className="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-50 disabled:opacity-50"
        >
          {keepUndecidedLabel(n)}
        </button>
      ) : null}
      {result ? (
        <span
          role={result.kind === "error" ? "alert" : "status"}
          className={
            result.kind === "error"
              ? "text-status-danger-fg"
              : "text-ink-secondary"
          }
        >
          {result.text}
        </span>
      ) : null}
      <Modal
        open={open}
        onClose={() => {
          if (!busy) setOpen(false);
        }}
        title={keepUndecidedQuestion(n)}
        size="sm"
        footer={
          <>
            <button
              type="button"
              onClick={() => setOpen(false)}
              disabled={busy}
              className="rounded-md border border-border px-4 py-2 text-sm font-semibold text-ink-primary hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-60"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void confirm()}
              disabled={busy}
              className="rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {keepUndecidedLabel(n)}
            </button>
          </>
        }
      >
        {null}
      </Modal>
    </div>
  );
}
