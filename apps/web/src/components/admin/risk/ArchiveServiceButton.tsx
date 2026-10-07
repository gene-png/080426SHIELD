"use client";
import * as React from "react";

import { Modal } from "@shield/design-system";

import { clientFacingError, serverReasonCode } from "@/lib/describe-save-error";
import { UPSTREAM_OUTCOME_UNKNOWN } from "@/lib/upstream-outcome";
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

/**
 * Review round 2, F1 (advisor, #736 6047873969): after the server's refusal
 * or an outcome-unknown 504, the screen says what its own reload did -- and
 * only the screen can, because only it knows whether the reload worked.
 */
const REFRESHED = "The list has been refreshed.";
const NOT_REFRESHED =
  "The list could not be refreshed. Reload the page before trying again.";

/** The failures the ruling appends a line about the list to. */
const SAYS_WHAT_THE_LIST_DID = new Set([
  "service_not_in_duplicate_group",
  UPSTREAM_OUTCOME_UNKNOWN,
]);

function failureText(
  message: string,
  code: string | null,
  reloaded: boolean,
): string {
  if (code === null || !SAYS_WHAT_THE_LIST_DID.has(code)) return message;
  return `${message} ${reloaded ? REFRESHED : NOT_REFRESHED}`;
}

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
  /**
   * Reloads the gate. Called after EVERY attempt, success or failure (B2).
   * Resolves to whether the gate was actually re-read (review round 2, F1).
   */
  onSettled: () => Promise<boolean>;
}

/** A failed attempt, and whether the reload after it re-read the gate. */
interface Failure {
  serviceId: string;
  /** The whole alert: the API's sentence and, where ruled, the list line. */
  text: string;
}

export function ArchiveServiceDialog({
  clientId,
  service,
  onClose,
  onSettled,
}: ArchiveServiceDialogProps): JSX.Element {
  const [busy, setBusy] = React.useState(false);
  const [failure, setFailure] = React.useState<Failure | null>(null);
  // DERIVED, not reset: a failure belongs to the service it was raised for,
  // so opening the dialog for another one shows none.
  const shown =
    failure !== null &&
    service !== null &&
    failure.serviceId === service.service_id
      ? failure
      : null;

  // Every way the dialog closes comes through here (round 3): Cancel, Esc, a
  // backdrop click, and the parent's own close after a success. A failure
  // belongs to one attempt, so closing ends it (R3-2); the parent is always
  // told, so its target and what is on screen cannot disagree (R3-1).
  function dismiss(): void {
    setFailure(null);
    onClose();
  }

  async function handleConfirm(target: RiskDuplicateService): Promise<void> {
    setBusy(true);
    setFailure(null);
    let message: string | null = null;
    let code: string | null = null;
    try {
      await archiveDuplicateService(clientId, target.service_id);
      console.info("[risk] service archived", { serviceId: target.service_id });
    } catch (err) {
      // The API's own sentence where it sent one (an outcome-unknown 504 says
      // the archive may have landed, which the fallback would deny), else the
      // approved fallback.
      console.error("[risk] archive service failed", {
        serviceId: target.service_id,
        err,
      });
      message = clientFacingError(err, FALLBACK);
      code = serverReasonCode(err);
    }
    // B2: on ANY outcome, re-read the gate, so the banner shows what the
    // server now holds -- which is also the "check" a 504 asks for. F1: the
    // failure is recorded only AFTER the reload, with whether it re-read the
    // gate, so nothing can claim a refresh that did not happen.
    let reloaded = false;
    try {
      reloaded = await onSettled();
    } finally {
      setBusy(false);
    }
    if (message === null) {
      onClose();
      return;
    }
    console.info("[risk] gate reload after a failed archive", { reloaded });
    setFailure({
      serviceId: target.service_id,
      text: failureText(message, code, reloaded),
    });
  }

  return (
    <Modal
      open={service !== null}
      onClose={dismiss}
      // R3-1: an archive in flight must not be dismissed out from under
      // itself. Not by a busy check here, which ran AFTER the native dialog
      // had already closed: the Modal keeps itself open instead.
      dismissible={!busy}
      title={service ? `Archive ${service.title}?` : ""}
      // B1: the same line as under the button, directly under the title.
      description={service ? startedLine(service) : undefined}
      size="sm"
      footer={
        <>
          <button
            type="button"
            onClick={dismiss}
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
      {shown !== null ? (
        <p
          role="alert"
          className="mt-3 text-sm font-medium text-status-danger-fg"
        >
          {shown.text}
        </p>
      ) : null}
    </Modal>
  );
}
