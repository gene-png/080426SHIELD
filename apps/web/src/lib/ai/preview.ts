"use client";

/**
 * Redaction-preview client (Sprint 5 T6).
 *
 * Fetches what a service's next Run-AI would send to the model AFTER redaction.
 * The backend builds this from the SAME payload builder run-ai uses, and it
 * neither egresses nor writes an llm_calls row — this is a look-before-you-send
 * gate, nothing more.
 */

export interface AiPreview {
  purpose: string;
  redaction_mode: string;
  payload: Record<string, unknown>;
  removed_counts: Record<string, number>;
}

export class AiPreviewError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: unknown,
  ) {
    super(`AI preview ${status}`);
  }
}

export async function fetchAiPreview(serviceId: string): Promise<AiPreview> {
  const res = await fetch("/api/proxy/ai/preview", {
    method: "POST",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ service_id: serviceId }),
  });
  if (!res.ok) {
    let payload: unknown;
    try {
      payload = await res.json();
    } catch {
      payload = await res.text();
    }
    throw new AiPreviewError(res.status, payload);
  }
  return (await res.json()) as AiPreview;
}

/**
 * Total number of redacted SPANS across all categories.
 *
 * Summing every value is correct only because `redacted_counts` carries one
 * unit: every value is a count of removals (see `app/ai/redact.py`). A key
 * measuring anything else -- characters deleted, bytes, a duration -- would make
 * this aggregate silently wrong on the pre-egress preview. If one is ever
 * needed, it goes in its own column, not in this dict.
 */
export function totalRemoved(counts: Record<string, number>): number {
  return Object.values(counts).reduce((sum, n) => sum + n, 0);
}
