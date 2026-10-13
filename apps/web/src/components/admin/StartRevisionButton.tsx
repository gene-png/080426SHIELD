"use client";
import * as React from "react";

import { Modal } from "@shield/design-system";

import { REVISION_COPY } from "@/lib/revisions/copy";
import { fill } from "@/lib/revisions/fill";

import type { JSX } from "react";

export interface StartRevisionButtonProps {
  /**
   * The record's status. The control renders ONLY for "approved" or
   * "released", the states the API allows a revision from (#1120, Option A):
   * an approved record is never edited in place, it is revised.
   */
  status: string;
  /** The version a revision would copy (V2's and V2a's {v}). */
  version: number;
  /**
   * Starts the revision with the typed reason. Throws on refusal; the thrown
   * error's message (the API's approved copy) is shown in the dialog.
   */
  onStart: (reason: string) => Promise<void>;
  /** Disables the trigger while a sibling workspace action is in flight. */
  disabled?: boolean;
}

/**
 * #1120 "Start a revision": the trigger (V1) and its dialog (V2, V2a, V2b,
 * V2c). The reason is required, as the API requires it; a refusal leaves the
 * dialog open and says why, in the API's words.
 */
export function StartRevisionButton({
  status,
  version,
  onStart,
  disabled = false,
}: StartRevisionButtonProps): JSX.Element | null {
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const reasonId = React.useId();
  const hintId = React.useId();

  if (status !== "approved" && status !== "released") return null;

  const trimmed = reason.trim();

  async function handleConfirm(): Promise<void> {
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      await onStart(trimmed);
      setOpen(false);
      setReason("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={disabled}
        className="rounded-md border border-border px-4 py-2 text-sm font-semibold text-ink-primary hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-60"
      >
        {REVISION_COPY.V1}
      </button>
      <Modal
        open={open}
        onClose={() => {
          if (!busy) setOpen(false);
        }}
        title={fill(REVISION_COPY.V2, { v: version })}
        size="sm"
        footer={
          <>
            <button
              type="button"
              onClick={() => setOpen(false)}
              disabled={busy}
              className="rounded-md border border-border px-4 py-2 text-sm font-semibold text-ink-primary hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-60"
            >
              {REVISION_COPY.V2c_CANCEL}
            </button>
            <button
              type="button"
              onClick={() => void handleConfirm()}
              disabled={busy || !trimmed}
              className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {REVISION_COPY.V2c_CONFIRM}
            </button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <p className="text-sm text-ink-secondary">
            {fill(REVISION_COPY.V2a, { v: version, "v+1": version + 1 })}
          </p>
          <label
            htmlFor={reasonId}
            className="text-sm font-semibold text-ink-primary"
          >
            {REVISION_COPY.V2b_LABEL}
          </label>
          <textarea
            id={reasonId}
            aria-describedby={hintId}
            required
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={busy}
            rows={3}
            className="rounded-md border border-border px-3 py-2 text-sm"
          />
          <p id={hintId} className="text-xs text-ink-tertiary">
            {REVISION_COPY.V2b_HINT}
          </p>
          {error ? (
            <p role="alert" className="text-sm text-status-danger-fg">
              {error}
            </p>
          ) : null}
        </div>
      </Modal>
    </>
  );
}
