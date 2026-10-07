"use client";
import * as React from "react";

import { Modal } from "@shield/design-system";

import { archiveService } from "@/lib/admin/client";
import { clientFacingError } from "@/lib/describe-save-error";

import type { JSX } from "react";

/**
 * #896: archive one service from the Risk Register's duplicate banner, the
 * remedy for its two-of-a-kind refusal. A danger-styled trigger and a confirm
 * dialog in the `DiscardDraftButton` pattern; nothing is archived until the
 * explicit confirm.
 *
 * Every string here was approved by the advisor (#736 6042801745, on the plan
 * in 6042306149), the dialog body with its last sentence changed to
 * "Archiving cannot be undone.": there is no unarchive route, through the API
 * either. Change none of them without the advisor.
 */

/** Shown when the API sent no sentence fit for a person. */
const FALLBACK = "The service could not be archived. Nothing was changed.";

function dialogBody(title: string): string {
  return (
    `The Risk Register will stop drawing on ${title}: the next version you ` +
    "generate leaves out its findings, and publishing no longer waits for it. " +
    "Nothing else changes: its assessments, its deliverables and the " +
    "client's view of it stay as they are. Archiving cannot be undone."
  );
}

export interface ArchiveServiceButtonProps {
  serviceId: string;
  title: string;
  /** Called once the archive has succeeded; the dashboard reloads its gate. */
  onArchived: () => void | Promise<void>;
  /** Disables the trigger while another dashboard action is in flight. */
  disabled?: boolean;
}

export function ArchiveServiceButton({
  serviceId,
  title,
  onArchived,
  disabled = false,
}: ArchiveServiceButtonProps): JSX.Element {
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function handleConfirm(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await archiveService(serviceId);
    } catch (err) {
      // The API's own sentence where it sent one (an outcome-unknown 504 says
      // the archive may have landed, which the fallback would deny), else the
      // approved fallback. The dialog stays open so the reader sees it.
      console.error("[risk] archive service failed", { serviceId, err });
      setError(clientFacingError(err, FALLBACK));
      setBusy(false);
      return;
    }
    console.info("[risk] service archived", { serviceId });
    setBusy(false);
    setOpen(false);
    await onArchived();
  }

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setError(null);
          setOpen(true);
        }}
        disabled={disabled}
        className="rounded-md border border-status-danger-border px-3 py-1.5 text-sm font-semibold text-status-danger-fg hover:bg-status-danger-bg disabled:cursor-not-allowed disabled:opacity-60"
      >
        Archive {title}
      </button>
      <Modal
        open={open}
        onClose={() => {
          // An archive in flight must not be dismissed out from under itself.
          if (!busy) setOpen(false);
        }}
        title={`Archive ${title}?`}
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
              onClick={() => void handleConfirm()}
              disabled={busy}
              className="rounded-md bg-status-danger-fg px-4 py-2 text-sm font-semibold text-ink-on-accent hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? "Archiving…" : "Yes, archive"}
            </button>
          </>
        }
      >
        <p className="text-sm text-ink-secondary">{dialogBody(title)}</p>
        {error !== null ? (
          <p
            role="alert"
            className="mt-3 text-sm font-medium text-status-danger-fg"
          >
            {error}
          </p>
        ) : null}
      </Modal>
    </>
  );
}
