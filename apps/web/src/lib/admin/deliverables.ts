"use client";

import { readFailureReason } from "@/lib/describe-save-error";

/** Wire types for GET /admin/deliverables (apps/api/app/schemas/admin.py). */

/** `withheld`: a released ATT&CK report scored against another catalog (#556).
 *  Released, and NOT visible to the client. */
export type DeliverableStatus =
  "generated" | "released" | "withheld" | "superseded";

export interface AdminDeliverableRow {
  id: string;
  service_id: string;
  service_kind: string;
  service_title: string;
  title: string;
  version: number;
  status: DeliverableStatus;
  /** True ONLY for a released, non-superseded row — what the client can see. */
  client_visible: boolean;
  finalized_at: string | null;
  released_at: string | null;
  pdf_artifact_id: string | null;
  xlsx_artifact_id: string | null;
  docx_artifact_id: string | null;
}

export interface AdminDeliverableListResponse {
  items: AdminDeliverableRow[];
}

/**
 * RR-2 (for #1121), design note §3.2: the deliverables of the client the
 * page's picker chose. The proxy refuses a request that names none.
 */
export async function fetchAdminDeliverables(
  clientId: string,
  signal?: AbortSignal,
): Promise<AdminDeliverableListResponse> {
  const url = `/api/proxy/admin/deliverables?client_id=${encodeURIComponent(clientId)}`;
  const res = await fetch(url, {
    cache: "no-store",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!res.ok) {
    // Read the body ONCE. res.json() followed by res.text() throws "body stream
    // already read" and masks the real status — the defect the 2026-08-04 pass
    // fixed in all six lib/*/client.ts wrappers.
    //
    // RR-2 (for #1121): the body is read as the `{error: {...}}` envelope every
    // api error arrives in (`_handle_http_exception`), through
    // `readFailureReason`, so a server sentence shows and #550's write-only
    // sentence does not. The old `detail` reads matched nothing the api sends.
    const raw = await res.text();
    let payload: unknown = undefined;
    try {
      payload = JSON.parse(raw) as unknown;
    } catch {
      /* non-JSON upstream error: the status-based fallback below */
    }
    throw new Error(
      readFailureReason({ status: res.status, payload }) ??
        `Failed to load deliverables (${res.status}).`,
    );
  }
  return (await res.json()) as AdminDeliverableListResponse;
}
