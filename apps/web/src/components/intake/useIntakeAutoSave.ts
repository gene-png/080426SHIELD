"use client";

import * as React from "react";

import { patchIntake } from "@/lib/intake/client";
import type {
  IntakePatchRequest,
  IntakeStateResponse,
} from "@/lib/intake/types";

import type { SaveState } from "./SaveStatus";

export interface AutoSaveHandle {
  saveState: SaveState;
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

  const save = React.useCallback(
    async (patch: IntakePatchRequest): Promise<IntakeStateResponse | null> => {
      setSaveState({ kind: "saving" });
      try {
        const next = await patchIntake(patch);
        setSaveState({ kind: "saved", at: Date.now() });
        onUpdate?.(next);
        return next;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Network error.";
        setSaveState({ kind: "error", message });
        return null;
      }
    },
    [onUpdate],
  );

  return { saveState, save, setSaveState };
}
