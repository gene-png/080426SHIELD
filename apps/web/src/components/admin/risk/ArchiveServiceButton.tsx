"use client";
import * as React from "react";

import { Modal } from "@shield/design-system";

import { clientFacingError } from "@/lib/describe-save-error";
import { archiveDuplicateService } from "@/lib/risk/client";
import { startedLine } from "@/lib/risk/started";
import type { RiskDuplicateService } from "@/lib/risk/types";

import type { JSX } from "react";

/**
 * #896: archive one service from the Risk Register's duplicate banner, the
 * remedy for its two-of-a-kind refusal. A danger-styled button per service
 * and ONE confirm dialog in the `DiscardDraftButton` pattern; nothing is
 * archived until the explicit confirm.
 *
 * Review B2 (advisor, #736 6046491381): the dialog archives through the
 * Risk-scoped route, which re-checks on the server, and reloads the gate on
 * ANY outcome so the buttons reflect the server. The dialog is hosted by the
 * dashboard, not by a button, because that reload can remove the very button
 * that opened it -- and a failure message inside an unmounted dialog is a
 * message nobody reads.
 *
 * Every string here was approved by the advisor (#736 6042801745), the dialog
 * body with its last sentence "Archiving cannot be undone.": there is no
 * unarchive route, through the API either. The line under each button and
 * under the dialog's title is `startedLine` (review B1, 6046898402). Change
 * none of them without the advisor.
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
  service: RiskDuplicateService;
  /** Opens the dashboard's dialog for this service. */
  onOpen: (service: RiskDuplicateService) => void;
  /** Disables the trigger while another dashboard action is in flight. */
  disabled?: boolean;
}

export function ArchiveServiceButton({
  service,
  onOpen,
  disabled = false,
}: ArchiveServiceButtonProps): JSX.Element {
  // B1: two services can share a title, so the line beneath says which this
  // is. Outside the button, so its accessible NAME stays "Archive {title}";
  // linked as its description, so a screen reader hears the line too.
  const lineId = React.useId();
  return (
    <div className="flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={() => onOpen(service)}
        disabled={disabled}
        aria-describedby={lineId}
        className="rounded-md border border-status-danger-border px-3 py-1.5 text-sm font-semibold text-status-danger-fg hover:bg-status-danger-bg disabled:cursor-not-allowed disabled:opacity-60"
      >
        Archive {service.title}
      </button>
      <span id={lineId} className="text-xs text-ink-secondary">
        {startedLine(service)}
      </span>
    </div>
  );
}

export interface ArchiveServiceDialogProps {
  clientId: string;
  /** The service being confirmed; null while the dialog is closed. */
  service: RiskDuplicateService | null;
  onClose: () => void;
  /** Reloads the gate. Called after EVERY attempt, success or failure (B2). */
  onSettled: () => Promise<void>;
}

export function ArchiveServiceDialog({
  clientId,
  service,
  onClose,
  onSettled,
}: ArchiveServiceDialogProps): JSX.Element {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<{
    serviceId: string;
    message: string;
  } | null>(null);
  // DERIVED, not reset: an error belongs to the service it was raised for, so
  // opening the dialog for another one shows none.
  const shownError =
    error !== null && service !== null && error.serviceId === service.service_id
      ? error.message
      : null;

  async function handleConfirm(target: RiskDuplicateService): Promise<void> {
    setBusy(true);
    setError(null);
    let failed = false;
    try {
      await archiveDuplicateService(clientId, target.service_id);
      console.info("[risk] service archived", { serviceId: target.service_id });
    } catch (err) {
      // The API's own sentence where it sent one (the 409 says the list was
      // refreshed; an outcome-unknown 504 says the archive may have landed,
      // which the fallback would deny), else the approved fallback.
      failed = true;
      console.error("[risk] archive service failed", {
        serviceId: target.service_id,
        err,
      });
      setError({
        serviceId: target.service_id,
        message: clientFacingError(err, FALLBACK),
      });
    }
    // B2: on ANY outcome, re-read the gate, so the banner shows what the
    // server now holds -- which is also the "check" a 504 asks for.
    try {
      await onSettled();
    } finally {
      setBusy(false);
    }
    if (!failed) onClose();
  }

  return (
    <Modal
      open={service !== null}
      onClose={() => {
        // An archive in flight must not be dismissed out from under itself.
        if (!busy) onClose();
      }}
      title={service ? `Archive ${service.title}?` : ""}
      // B1: the same line as under the button, directly under the title.
      description={service ? startedLine(service) : undefined}
      size="sm"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-md border border-border px-4 py-2 text-sm font-semibold text-ink-primary hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => {
              if (service) void handleConfirm(service);
            }}
            disabled={busy}
            className="rounded-md bg-status-danger-fg px-4 py-2 text-sm font-semibold text-ink-on-accent hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? "Archiving…" : "Yes, archive"}
          </button>
        </>
      }
    >
      {service ? (
        <p className="text-sm text-ink-secondary">
          {dialogBody(service.title)}
        </p>
      ) : null}
      {shownError !== null ? (
        <p
          role="alert"
          className="mt-3 text-sm font-medium text-status-danger-fg"
        >
          {shownError}
        </p>
      ) : null}
    </Modal>
  );
}
