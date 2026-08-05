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

/**
 * Where the status request has got to.
 *
 * `status === null` is ambiguous on its own — it means BOTH "we haven't asked
 * yet" and "the endpoint is down" — and a consumer that conflates the two
 * treats an in-flight request as a permanent unknown. That is exactly how the
 * Run-AI guard came to produce 1646 fields of canned output with no warning:
 * under load the click beat the fetch. Callers must branch on `phase`, not on
 * `status === null`.
 */
export type AiStatusPhase = "loading" | "loaded" | "error";

export interface UseAiStatus {
  status: AiStatus | null;
  phase: AiStatusPhase;
  /**
   * Resolves once the in-flight status request settles — `null` if it failed.
   * Lets an event handler wait for the answer instead of guessing from a
   * `null` status, which is what the Run-AI guard needs.
   */
  settled: () => Promise<AiStatus | null>;
  refresh: () => void;
}

interface StatusResult {
  nonce: number;
  status: AiStatus | null;
  phase: Exclude<AiStatusPhase, "loading">;
}

/** Load AI status once on mount, with a manual refresh for after key changes. */
export function useAiStatus(): UseAiStatus {
  const [nonce, setNonce] = React.useState(0);
  const [result, setResult] = React.useState<StatusResult | null>(null);
  const inFlight = React.useRef<Promise<AiStatus | null> | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    // Rejection is folded into `null` here so both consumers — the render
    // state below and `settled()` — see the same settled value.
    const request = fetchAiStatus().then(
      (s) => s,
      () => null,
    );
    inFlight.current = request;
    void request.then((s) => {
      if (cancelled) return;
      // Non-blocking: a status outage must not stop an admin working. The
      // distinction from "loading" is the whole point of `phase`.
      setResult({ nonce, status: s, phase: s ? "loaded" : "error" });
    });
    return () => {
      cancelled = true;
    };
  }, [nonce]);

  // A result from a previous nonce is stale: `refresh()` puts us back in
  // "loading" by derivation, so no effect ever has to set state to say so.
  const fresh = result && result.nonce === nonce ? result : null;

  return {
    status: fresh ? fresh.status : null,
    phase: fresh ? fresh.phase : "loading",
    // The fallback covers a click landing before the mount effect ran; one
    // extra request is the right trade against a promise that never settles.
    settled: () => inFlight.current ?? fetchAiStatus().catch(() => null),
    refresh: () => setNonce((n) => n + 1),
  };
}
