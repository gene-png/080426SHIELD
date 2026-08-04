"use client";

import type {
  AdminIntakeQueueResponse,
  FulfillServiceRequestResponse,
} from "./types";

export async function fetchIntakeQueue(): Promise<AdminIntakeQueueResponse> {
  const res = await fetch("/api/proxy/admin/intake-queue", {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to load intake queue (${res.status}).`);
  }
  return (await res.json()) as AdminIntakeQueueResponse;
}

export async function fulfillServiceRequest(
  requestId: string,
): Promise<FulfillServiceRequestResponse> {
  const res = await fetch(
    `/api/proxy/admin/service-requests/${requestId}/fulfill`,
    { method: "POST" },
  );
  if (!res.ok) {
    let detail = `Failed to publish (${res.status}).`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* keep default */
    }
    throw new Error(detail);
  }
  return (await res.json()) as FulfillServiceRequestResponse;
}

// --- Client + domain management (Work Order B2) -----------------------------

export interface ClientSummary {
  id: string;
  legal_name: string;
  dba_name: string | null;
  industry: string | null;
  size_band: string | null;
  intake_completed_at: string | null;
  created_at: string;
}

export interface DomainRow {
  id: string;
  client_id: string;
  domain: string;
  created_at: string;
}

async function _detail(res: Response): Promise<string> {
  try {
    // The API surfaces errors through the D-016 envelope
    // ({error: {message, reason?}}); older/plain routes use {detail}. Prefer
    // the typed message so friendly copy (e.g. the reserved-TLD rejection)
    // reaches the Management UI instead of a bare "Request failed".
    const body = (await res.json()) as {
      detail?: string;
      error?: { message?: string };
    };
    if (body?.error?.message) return body.error.message;
    if (body?.detail) return body.detail;
  } catch {
    /* keep default */
  }
  return `Request failed (${res.status}).`;
}

export async function listClients(): Promise<ClientSummary[]> {
  const res = await fetch("/api/proxy/admin/clients", { cache: "no-store" });
  if (!res.ok) throw new Error(await _detail(res));
  return ((await res.json()) as { clients: ClientSummary[] }).clients;
}

export async function createClient(body: {
  legal_name: string;
  industry?: string;
}): Promise<ClientSummary> {
  const res = await fetch("/api/proxy/admin/clients", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await _detail(res));
  return (await res.json()) as ClientSummary;
}

export async function listDomains(cid: string): Promise<DomainRow[]> {
  const res = await fetch(`/api/proxy/admin/clients/${cid}/domains`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await _detail(res));
  return ((await res.json()) as { domains: DomainRow[] }).domains;
}

export async function addDomain(
  cid: string,
  domain: string,
): Promise<DomainRow> {
  const res = await fetch(`/api/proxy/admin/clients/${cid}/domains`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ domain }),
  });
  if (!res.ok) throw new Error(await _detail(res));
  return (await res.json()) as DomainRow;
}

export async function removeDomain(cid: string, did: string): Promise<void> {
  const res = await fetch(`/api/proxy/admin/clients/${cid}/domains/${did}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await _detail(res));
}
