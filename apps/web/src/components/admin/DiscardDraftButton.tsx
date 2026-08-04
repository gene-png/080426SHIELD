"use client";
import * as React from "react";

import { Modal } from "@shield/design-system";

import type { JSX } from "react";

export interface DiscardDraftButtonProps {
  /**
   * Current draft status. The affordance renders ONLY for `"draft"` — a
   * discarded, submitted, approved, or released record has no draft to throw
   * away, mirroring the backend's draft-only discard contract (D-031).
   */
  status: string;
  /**
   * One-line, service-specific summary of what discarding destroys, computed
   * by the workspace from the already-fetched grid (e.g. "12 answers,
   * including client-entered data, will be discarded.").
   */
  destructionSummary: string;
  /** Invoked when the user confirms. May be async; the modal stays open until it settles. */
  onConfirm: () => void | Promise<void>;
  /** Disables the trigger while a sibling workspace action is in flight. */
  disabled?: boolean;
  /** Trigger label. Defaults to "Discard draft". */
  label?: string;
}

/**
 * The app's first destructive-confirm dialog: a danger-styled trigger that
 * opens the design-system Modal, states exactly what will be destroyed, and
 * only calls `onConfirm` on an explicit confirm click. Cancel / ESC / backdrop
 * dismiss without side effects.
 */
export function DiscardDraftButton({
  status,
  destructionSummary,
  onConfirm,
  disabled = false,
  label = "Discard draft",
}: DiscardDraftButtonProps): JSX.Element | null {
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  if (status !== "draft") return null;

  async function handleConfirm(): Promise<void> {
    setBusy(true);
    try {
      await onConfirm();
      setOpen(false);
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
        className="rounded-md border border-status-danger-border px-4 py-2 text-sm font-semibold text-status-danger-fg hover:bg-status-danger-bg disabled:cursor-not-allowed disabled:opacity-60"
      >
        {label}
      </button>
      <Modal
        open={open}
        onClose={() => {
          // A confirm-in-flight must not be dismissed out from under itself.
          if (!busy) setOpen(false);
        }}
        title="Discard this draft?"
        description="This cannot be undone."
        size="sm"
        footer={
          <>
            <button
              type="button"
              onClick={() => setOpen(false)}
              disabled={busy}
              className="rounded-md border border-border-default px-4 py-2 text-sm font-semibold text-ink-primary hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-60"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleConfirm()}
              disabled={busy}
              className="rounded-md bg-status-danger-fg px-4 py-2 text-sm font-semibold text-ink-on-accent hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? "Discarding…" : "Yes, discard"}
            </button>
          </>
        }
      >
        <p className="text-sm text-ink-secondary">{destructionSummary}</p>
      </Modal>
    </>
  );
}
