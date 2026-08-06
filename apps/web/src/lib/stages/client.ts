"use client";

import * as React from "react";

/**
 * Derived six-stage progress for a service. Read-only presentation of state the
 * API already holds — this never writes and never changes a status.
 */

export type StageState = "complete" | "current" | "pending";

export interface Stage {
  key: string;
  state: StageState;
}

export interface ServiceStages {
  service_id: string;
  kind: string;
  version: number | null;
  stages: Stage[];
}

export class StagesProxyError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: unknown,
  ) {
    super(`Stages proxy ${status}`);
  }
}

export async function fetchServiceStages(
  serviceId: string,
  signal?: AbortSignal,
): Promise<ServiceStages> {
  const res = await fetch(`/api/proxy/services/${serviceId}/stages`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!res.ok) {
    // Read the body ONCE. res.json() then res.text() throws "body stream
    // already read" and masks the real status (the 2026-08-04 fix pass).
    const raw = await res.text();
    let payload: unknown;
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = raw;
    }
    throw new StagesProxyError(res.status, payload);
  }
  return (await res.json()) as ServiceStages;
}

/**
 * Load a service's stages.
 *
 * Returns an explicit phase rather than a bare null. A hook that returns null
 * for BOTH "still loading" and "request failed" makes its callers conflate the
 * two, and anything gating on that null fails open the moment the box is slow —
 * the exact defect the Run-AI guard had.
 *
 * `reloadKey` re-fetches when the caller's own state moves (an approval, a
 * Run-AI, a generated deliverable), since the derivation reads that same state.
 */
export function useServiceStages(
  serviceId: string | null | undefined,
  reloadKey: unknown = 0,
): {
  phase: "loading" | "ready" | "error";
  stages: ServiceStages | null;
} {
  // One key per request. Stamping the result with the key it was fetched for
  // lets "loading" be DERIVED — a stored result whose key no longer matches
  // belongs to a superseded request — instead of written by a synchronous
  // setState inside the effect, which react-hooks/set-state-in-effect rejects
  // and which is a StrictMode double-render hazard anyway.
  const key = serviceId ? `${serviceId}|${String(reloadKey)}` : null;
  const [result, setResult] = React.useState<{
    key: string;
    phase: "ready" | "error";
    stages: ServiceStages | null;
  } | null>(null);

  React.useEffect(() => {
    if (!key || !serviceId) return;
    const controller = new AbortController();
    let live = true;
    fetchServiceStages(serviceId, controller.signal)
      .then((stages) => {
        if (live) setResult({ key, phase: "ready", stages });
      })
      .catch((err: unknown) => {
        if (!live) return;
        // An aborted request was superseded, not failed — reporting it as an
        // error would flash a failure every time the caller re-keyed.
        if (err instanceof DOMException && err.name === "AbortError") return;
        setResult({ key, phase: "error", stages: null });
      });
    return () => {
      live = false;
      controller.abort();
    };
  }, [key, serviceId]);

  // No service to describe: ready with nothing, not an error and not a wait.
  if (!serviceId) return { phase: "ready", stages: null };
  if (!result || result.key !== key) return { phase: "loading", stages: null };
  return { phase: result.phase, stages: result.stages };
}
