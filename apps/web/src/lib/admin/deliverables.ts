"use client";

/** Wire types for GET /admin/deliverables (apps/api/app/schemas/admin.py). */

export type DeliverableStatus = "generated" | "released" | "superseded";

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

export async function fetchAdminDeliverables(
  signal?: AbortSignal,
): Promise<AdminDeliverableListResponse> {
  const res = await fetch("/api/proxy/admin/deliverables", {
    cache: "no-store",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!res.ok) {
    // Read the body ONCE. res.json() followed by res.text() throws "body stream
    // already read" and masks the real status — the defect the 2026-08-04 pass
    // fixed in all six lib/*/client.ts wrappers.
    const raw = await res.text();
    let detail = `Failed to load deliverables (${res.status}).`;
    try {
      const body = JSON.parse(raw) as {
        detail?: { message?: string } | string;
      };
      if (typeof body?.detail === "string") detail = body.detail;
      else if (body?.detail?.message) detail = body.detail.message;
    } catch {
      /* non-JSON upstream error: keep the status-based message */
    }
    throw new Error(detail);
  }
  return (await res.json()) as AdminDeliverableListResponse;
}
