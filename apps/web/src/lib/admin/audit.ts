"use client";

/**
 * Client-side fetch helpers for the admin audit viewer (Sprint 5 T7).
 *
 * Two read-only, cursor-paginated stores: audit_entries (Activity) and
 * llm_calls (AI calls). Both go through the Next proxy so the Bearer token
 * never reaches the browser. Read-only by construction — there are no
 * create/update/delete helpers for an append-only store.
 */

export interface AuditEntryRow {
  id: string;
  at: string;
  actor_user_id: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  details: Record<string, unknown> | null;
  correlation_id: string | null;
}

export interface AuditEntriesResponse {
  entries: AuditEntryRow[];
  next_cursor: string | null;
}

export interface LlmCallRow {
  id: string;
  service_id: string | null;
  client_id: string | null;
  purpose: string;
  prompt_version: string;
  provider: string;
  model: string;
  mode: string;
  input_tokens: number | null;
  output_tokens: number | null;
  duration_ms: number | null;
  status: string;
  error_message: string | null;
  redacted_counts: Record<string, number> | null;
  requested_by: string;
  requested_at: string;
  completed_at: string | null;
  correlation_id: string | null;
}

export interface LlmCallsResponse {
  calls: LlmCallRow[];
  next_cursor: string | null;
}

export interface AuditEntryFilters {
  action?: string;
  target_type?: string;
  actor_user_id?: string;
  correlation_id?: string;
  at_from?: string;
  at_to?: string;
  cursor?: string;
  limit?: number;
}

export interface LlmCallFilters {
  client_id?: string;
  purpose?: string;
  provider?: string;
  status?: string;
  correlation_id?: string;
  at_from?: string;
  at_to?: string;
  cursor?: string;
  limit?: number;
}

export class AuditProxyError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: unknown,
  ) {
    super(`Audit proxy ${status}`);
  }
}

function toQuery<T extends object>(filters: T): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  }
  const q = params.toString();
  return q ? `?${q}` : "";
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    let payload: unknown;
    try {
      payload = await res.json();
    } catch {
      payload = await res.text();
    }
    throw new AuditProxyError(res.status, payload);
  }
  return (await res.json()) as T;
}

export async function fetchAuditEntries(
  filters: AuditEntryFilters = {},
): Promise<AuditEntriesResponse> {
  return getJson<AuditEntriesResponse>(
    `/api/proxy/admin/audit-entries${toQuery(filters)}`,
  );
}

export async function fetchLlmCalls(
  filters: LlmCallFilters = {},
): Promise<LlmCallsResponse> {
  return getJson<LlmCallsResponse>(
    `/api/proxy/admin/llm-calls${toQuery(filters)}`,
  );
}

export function describeAuditError(err: unknown): string {
  if (err instanceof AuditProxyError) {
    const payload = err.payload as
      | { error?: { message?: string }; detail?: { message?: string } | string }
      | undefined;
    const detail = payload?.detail;
    return (
      payload?.error?.message ??
      (typeof detail === "string" ? detail : detail?.message) ??
      `Request failed (${err.status}).`
    );
  }
  return err instanceof Error ? err.message : "Request failed.";
}
