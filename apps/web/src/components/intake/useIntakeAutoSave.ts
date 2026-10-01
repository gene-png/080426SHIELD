"use client";

import * as React from "react";

import { patchIntake } from "@/lib/intake/client";
import type {
  IntakePatchRequest,
  IntakeStateResponse,
} from "@/lib/intake/types";

import type { SaveState } from "./SaveStatus";
import { clientFacingError } from "@/lib/describe-save-error";

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

/** Wraps `patchIntake` with save-status state + lightweight error handling.
 *
 * Callers invoke `save(patch)` on field blur. The hook returns the updated
 * intake state on success (so the caller can refresh local form values) or
 * `null` on failure. The SaveStatus indicator reads `saveState` directly.
 */
export function useIntakeAutoSave(
  onUpdate?: (next: IntakeStateResponse) => void,
): AutoSaveHandle {
  const [saveState, setSaveState] = React.useState<SaveState>({ kind: "idle" });
  const [savesInFlight, setSavesInFlight] = React.useState(0);
  // The same count, readable synchronously when an answer lands, so a save
  // that finishes while another is still out does not say "Saved".
  const pending = React.useRef(0);

  const save = React.useCallback(
    async (patch: IntakePatchRequest): Promise<IntakeStateResponse | null> => {
      pending.current += 1;
      setSavesInFlight((n) => n + 1);
      setSaveState({ kind: "saving" });
      try {
        const next = await patchIntake(patch);
        setSaveState(
          pending.current > 1
            ? { kind: "saving" }
            : { kind: "saved", at: Date.now() },
        );
        onUpdate?.(next);
        return next;
      } catch (err) {
        const message = clientFacingError(err, "Network error.");
        setSaveState({ kind: "error", message });
        return null;
      } finally {
        pending.current -= 1;
        setSavesInFlight((n) => n - 1);
      }
    },
    [onUpdate],
  );

  return { saveState, savesInFlight, save, setSaveState };
}
