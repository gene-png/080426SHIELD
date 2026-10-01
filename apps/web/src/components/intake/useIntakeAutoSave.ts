"use client";

import * as React from "react";

import { patchIntake } from "@/lib/intake/client";
import type {
  IntakePatchRequest,
  IntakeStateResponse,
} from "@/lib/intake/types";

import type { SaveState } from "./SaveStatus";
import {
  clientFacingError,
  isUpstreamOutcomeUnknown,
} from "@/lib/describe-save-error";

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

/** The fields a patch writes, keyed so a client field and a top-level
 *  profile field of the same name cannot collide. */
function fieldsOf(patch: IntakePatchRequest): string[] {
  const top = Object.keys(patch).filter((k) => k !== "client");
  const client = Object.keys(patch.client ?? {}).map((k) => `client.${k}`);
  return [...top, ...client];
}

/** An answer the api DID send that refused the value (a 4xx), as opposed to
 *  no answer at all (#550's `upstream_outcome_unknown`, where the save may
 *  have landed). Duck-typed on the proxy error's numeric `status`. */
function isAnsweredRefusal(err: unknown): boolean {
  const status = (err as { status?: unknown } | null)?.status;
  return (
    typeof status === "number" &&
    status >= 400 &&
    status < 500 &&
    !isUpstreamOutcomeUnknown(err)
  );
}

/** Wraps `patchIntake` with save-status state + lightweight error handling.
 *
 * Callers invoke `save(patch)` on field blur. The hook returns the updated
 * intake state on success (so the caller can refresh local form values) or
 * `null` on failure. The SaveStatus indicator reads `saveState` directly.
 *
 * `onRefused(patch)` is called when the api ANSWERED and refused the save
 * (a 4xx), so a caller holding the typed value can let it go: the server
 * does not hold it and never will (review of #757, finding 2).
 */
export function useIntakeAutoSave(
  onUpdate?: (next: IntakeStateResponse) => void,
  onRefused?: (patch: IntakePatchRequest) => void,
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
      try {
        const next = await patchIntake(patch);
        for (const f of own()) errors.current.delete(f);
        onUpdate?.(next);
        return next;
      } catch (err) {
        const message = clientFacingError(err, "Network error.");
        for (const f of own()) {
          // Re-inserted, so the newest error is the one shown.
          errors.current.delete(f);
          errors.current.set(f, message);
        }
        if (isAnsweredRefusal(err)) onRefused?.(patch);
        return null;
      } finally {
        pending.current -= 1;
        setSavesInFlight((n) => n - 1);
        publish();
      }
    },
    [onUpdate, onRefused, publish],
  );

  return { saveState, savesInFlight, save, setSaveState };
}
