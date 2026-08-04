"use client";
import * as React from "react";

import { fetchAiStatus, type AiStatus } from "@/lib/admin/client";

/**
 * Issue 2: shared AI-readiness state for the admin surfaces.
 *
 * Two behaviours this exists to guarantee:
 *
 * 1. **The warning follows the config, not the page.** The banner used to live
 *    on a single workspace, so an admin could sign in and run AI from four
 *    other workspaces without ever being told output would be canned.
 *
 * 2. **Acknowledging offline mode does not outlive the key it applied to.**
 *    The "Continue offline" acknowledgement is stored under a key derived from
 *    the current configuration (`aiStatusKey`). Removing the API key changes
 *    `ready`/`key_source`, which changes that storage key, so the very next
 *    Run AI in the same session warns again — exactly what was asked for.
 */

/** Identity of the current AI configuration; changes whenever the key does. */
export function aiStatusKey(s: AiStatus): string {
  return `shield.ai-offline-ack:${s.mode}:${s.provider}:${s.key_source}:${s.ready}`;
}

export function hasAcknowledgedOffline(s: AiStatus): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.sessionStorage.getItem(aiStatusKey(s)) === "1";
  } catch {
    // Storage can throw in hardened browser configs. Treat it as "not
    // acknowledged" so the admin is warned rather than silently skipped.
    return false;
  }
}

export function acknowledgeOffline(s: AiStatus): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(aiStatusKey(s), "1");
  } catch {
    /* non-blocking: worst case the admin is warned again */
  }
}

export interface UseAiStatus {
  status: AiStatus | null;
  refresh: () => void;
}

/** Load AI status once on mount, with a manual refresh for after key changes. */
export function useAiStatus(): UseAiStatus {
  const [status, setStatus] = React.useState<AiStatus | null>(null);
  const [nonce, setNonce] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    fetchAiStatus()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        // Non-blocking: a status outage must not stop an admin working.
        if (!cancelled) setStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [nonce]);

  return { status, refresh: () => setNonce((n) => n + 1) };
}
