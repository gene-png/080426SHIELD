"use client";

import type {
  AdminIntakeQueueResponse,
  FulfillServiceRequestResponse,
} from "./types";

/**
 * Issue 7: pass a `clientId` to scope the queue to ONE organization. Without it
 * the API returns every tenant's requests but sets `client` to whichever tenant
 * was created last — advisory only, and the cause of the queue appearing to
 * "open to the last client submitted".
 */
export async function fetchIntakeQueue(
  clientId?: string,
): Promise<AdminIntakeQueueResponse> {
  const qs = clientId ? `?client_id=${encodeURIComponent(clientId)}` : "";
  const res = await fetch(`/api/proxy/admin/intake-queue${qs}`, {
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
  /** Issue 3: non-null once archived. Only present when include_archived. */
  archived_at: string | null;
  /** Issue 7: service requests still awaiting review, for the org index. */
  open_request_count: number;
  total_request_count: number;
}

/** Issue 3: one user inside a tenant, for the Management user list. */
export interface AdminUserRow {
  id: string;
  email: string;
  display_name: string | null;
  title: string | null;
  role: "admin" | "client";
  is_active: boolean;
  last_login_at: string | null;
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

export async function listClients(
  opts: { includeArchived?: boolean } = {},
): Promise<ClientSummary[]> {
  const qs = opts.includeArchived ? "?include_archived=true" : "";
  const res = await fetch(`/api/proxy/admin/clients${qs}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await _detail(res));
  return ((await res.json()) as { clients: ClientSummary[] }).clients;
}

/** Issue 3: archive a tenant. Data is retained; the row leaves the live list. */
export async function archiveClient(cid: string): Promise<void> {
  const res = await fetch(`/api/proxy/admin/clients/${cid}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await _detail(res));
}

/** Issue 3: the users pinned to a tenant, active and deactivated alike. */
export async function listClientUsers(cid: string): Promise<AdminUserRow[]> {
  const res = await fetch(`/api/proxy/admin/clients/${cid}/users`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await _detail(res));
  return ((await res.json()) as { users: AdminUserRow[] }).users;
}

/** Issue 3: deactivate (or reactivate) a user. Deactivation blocks sign-in. */
export async function setUserActive(
  userId: string,
  isActive: boolean,
): Promise<AdminUserRow> {
  const res = await fetch(`/api/proxy/admin/users/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_active: isActive }),
  });
  if (!res.ok) throw new Error(await _detail(res));
  return (await res.json()) as AdminUserRow;
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
