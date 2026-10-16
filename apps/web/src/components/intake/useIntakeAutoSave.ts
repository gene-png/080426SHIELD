"use client";

import * as React from "react";

import { patchIntake } from "@/lib/intake/client";
import type {
  IntakePatchRequest,
  IntakeStateResponse,
} from "@/lib/intake/types";

import type { SaveState } from "./SaveStatus";
import { clientFacingError } from "@/lib/describe-save-error";
import { UPSTREAM_OUTCOME_UNKNOWN_MESSAGE } from "@/lib/upstream-outcome";

export interface AutoSaveHandle {
  saveState: SaveState;
  /**
   * #252: how many saves have been sent and not yet answered. A count, not a
   * flag: with two saves out, the first answer must not read as "nothing in
   * flight" while the second is still pending.
   */
  savesInFlight: number;
  save: (patch: IntakePatchRequest) => Promise<IntakeStateResponse | null>;
  setSaveState: React.Dispatch<React.SetStateAction<SaveState>>;
}

/** Approved verbatim on #736 (6115773247, ruling B). */
const REFUSED_NOT_SAVED = "This value was not accepted, so it was not saved.";
/** Approved verbatim on #736 (6116519635): a 5xx came back with no usable
 *  server message. */
const SERVER_NOT_SAVED =
  "The server could not save this value. Try again in a moment.";
/** S-1115-1, approved verbatim on #736 (6207611148): an answer that did not
 *  judge the value (a 401, 403, 429...), so the typed value is kept. */
const NOT_SAVED_KEPT =
  "This value was not saved. It is still in the form, so you can save it again.";
/** S-1115-2, a PLACEHOLDER until approved: the same answer, for a field the
 *  caller does NOT keep, where "still in the form" would be false (review of
 *  8b4f28a1: Step 3 re-reads its fields from the server when it reopens). */
const NOT_SAVED_RETYPE = "This value was not saved. Set it again to save it.";

/** The fields a patch writes, keyed so a client field and a top-level
 *  profile field of the same name cannot collide. */
function fieldsOf(patch: IntakePatchRequest): string[] {
  const top = Object.keys(patch).filter((k) => k !== "client");
  const client = Object.keys(patch.client ?? {}).map((k) => `client.${k}`);
  return [...top, ...client];
}

/** The answer's HTTP status, duck-typed on the proxy error's numeric
 *  `status`; null for a thrown network error, which carries none. */
function statusOf(err: unknown): number | null {
  const status = (err as { status?: unknown } | null)?.status;
  return typeof status === "number" ? status : null;
}

/** #1115 (advisor 6207611148): the statuses that JUDGED the value, a 400, a
 *  409 (the intake will never take it) or a 422. Only these let the typed
 *  value go. A 401, 403 or 429, typed or not, says nothing about the value,
 *  so the client keeps what they typed and can save it again. */
const JUDGED_THE_VALUE = new Set([400, 409, 422]);

function isValueRefusal(err: unknown): boolean {
  const status = statusOf(err);
  return status !== null && JUDGED_THE_VALUE.has(status);
}

/** The api's own envelope (`{error: {...}}`), as `exceptions.py` sends every
 *  error, including its 500. A 5xx without it came from something in front of
 *  the api, so the save may have landed (ruling (a)). */
function hasApiEnvelope(err: unknown): boolean {
  const payload = (err as { payload?: unknown } | null)?.payload;
  const inner = (payload as { error?: unknown } | null)?.error;
  return typeof inner === "object" && inner !== null;
}

/** The sentence when the error carries no usable server message. `kept`
 *  says whether the caller holds the typed value for this save. */
function fallbackFor(err: unknown, kept: boolean): string {
  const status = statusOf(err);
  if (status === null) return "Network error.";
  // #1093 item 2, review of e85890b3: a 2xx we cannot attribute to the api.
  // Our proxy answers every 2xx with JSON, and an unreadable api 2xx already
  // arrives as the typed 504, so this came from something in front of the app
  // (a captive portal, a proxy's block page, a sign-in interstitial) and the
  // PATCH may never have arrived. Not "a write that landed with an unreadable
  // answer", the issue's first framing, which does not survive that trace.
  // Unknown, never "Saved" and never "Network error.".
  if (status >= 200 && status < 300) return UPSTREAM_OUTCOME_UNKNOWN_MESSAGE;
  if (isValueRefusal(err)) return REFUSED_NOT_SAVED;
  if (status >= 500 && status < 600) {
    return hasApiEnvelope(err)
      ? SERVER_NOT_SAVED
      : UPSTREAM_OUTCOME_UNKNOWN_MESSAGE;
  }
  return kept ? NOT_SAVED_KEPT : NOT_SAVED_RETYPE;
}

/** Wraps `patchIntake` with save-status state + lightweight error handling.
 *
 * Callers invoke `save(patch)` on field blur. The hook returns the updated
 * intake state on success (so the caller can refresh local form values) or
 * `null` on failure. The SaveStatus indicator reads `saveState` directly.
 *
 * `onRefused(patch)` is called when the api ANSWERED and judged the value (a
 * 400, 409 or 422, #1115), so a caller holding the typed value can let it go:
 * the server does not hold it and never will (review of #757, finding 2).
 * Any other answer keeps it.
 *
 * `keeps(patch)` says whether the caller holds every value in `patch` on
 * screen after a failed save, which decides whether the client may be told it
 * is "still in the form". Its default, true, suits a caller with no fields of
 * its own (the hook's tests); the wizard passes its real answer.
 *
 * `clientId` (#1262, the `/intake` residual) is the client every save is
 * scoped to: the wizard passes the client it loaded, so a save never follows
 * the shared active-client cookie to another tenant.
 */
export function useIntakeAutoSave(
  onUpdate?: (next: IntakeStateResponse) => void,
  onRefused?: (patch: IntakePatchRequest) => void,
  keeps: (patch: IntakePatchRequest) => boolean = () => true,
  clientId?: string,
): AutoSaveHandle {
  const [saveState, setSaveState] = React.useState<SaveState>({ kind: "idle" });
  const [savesInFlight, setSavesInFlight] = React.useState(0);
  // The same count, readable synchronously when an answer lands, so a save
  // that finishes while another is still out does not say "Saved".
  const pending = React.useRef(0);
  // Review of #757, finding 4. A failed field's error stays until THAT field
  // saves successfully, or a newer save of it fails with its own error. A
  // later answer for ANOTHER field used to overwrite it with "Saving…" or
  // "Saved", which is what made a refused value silent. `latest` is each
  // field's newest save, so an older answer cannot clear or set a newer
  // save's state.
  const sequence = React.useRef(0);
  const latest = React.useRef(new Map<string, number>());
  const errors = React.useRef(new Map<string, string>());

  const publish = React.useCallback(() => {
    const messages = [...errors.current.values()];
    if (messages.length > 0) {
      setSaveState({ kind: "error", message: messages[messages.length - 1] });
    } else if (pending.current > 0) {
      setSaveState({ kind: "saving" });
    } else {
      setSaveState({ kind: "saved", at: Date.now() });
    }
  }, []);

  const save = React.useCallback(
    async (patch: IntakePatchRequest): Promise<IntakeStateResponse | null> => {
      const id = ++sequence.current;
      const fields = fieldsOf(patch);
      for (const f of fields) latest.current.set(f, id);
      const own = () => fields.filter((f) => latest.current.get(f) === id);
      pending.current += 1;
      setSavesInFlight((n) => n + 1);
      publish();
      let next: IntakeStateResponse;
      try {
        next = await patchIntake(patch, clientId);
        for (const f of own()) errors.current.delete(f);
      } catch (err) {
        // IN-1 (#1049): "Network error." only when no answer came back. An
        // answer with no usable server message gets copy for its class, by
        // the table #1115 approved (6207611148): see `fallbackFor`.
        const message = clientFacingError(err, fallbackFor(err, keeps(patch)));
        for (const f of own()) {
          // Re-inserted, so the newest error is the one shown.
          errors.current.delete(f);
          errors.current.set(f, message);
        }
        if (isValueRefusal(err)) onRefused?.(patch);
        return null;
      } finally {
        pending.current -= 1;
        setSavesInFlight((n) => n - 1);
        publish();
      }
      // OUTSIDE the try (#1093 item 2): a throw here is the caller's bug, not
      // a failed save, so it is logged and re-thrown as itself rather than
      // reported to the client as "Network error.". The wizard calls
      // `void autoSave.save(...)`, so the re-throw surfaces as an unhandled
      // rejection in the console: loud, on purpose. Its `onUpdate` is a
      // `setState`, which does not throw today.
      try {
        onUpdate?.(next);
      } catch (err) {
        console.error("[intake] onUpdate threw after a save landed", err);
        throw err;
      }
      return next;
    },
    [onUpdate, onRefused, keeps, clientId, publish],
  );

  return { saveState, savesInFlight, save, setSaveState };
}
