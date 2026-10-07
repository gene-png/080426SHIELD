"use client";

import type { RiskGate, RiskRegister } from "./types";

export class RiskProxyError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: unknown,
  ) {
    super(`Risk proxy ${status}`);
  }
}

async function jsonRequest<T>(
  url: string,
  init: { method?: "GET" | "POST" | "PATCH"; body?: unknown } = {},
): Promise<T> {
  const res = await fetch(url, {
    method: init.method ?? "GET",
    cache: "no-store",
    headers:
      init.body === undefined
        ? { Accept: "application/json" }
        : { Accept: "application/json", "Content-Type": "application/json" },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
  if (!res.ok) {
    // Read the body ONCE, then try to parse it. Calling res.json() and then
    // res.text() on failure throws "body stream already read", which masked a
    // real 404 behind a confusing error while this path was unwired (issue 4).
    const raw = await res.text();
    let payload: unknown;
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = raw;
    }
    throw new RiskProxyError(res.status, payload);
  }
  return (await res.json()) as T;
}

/**
 * #896 review B2: archive one service of a duplicate group through the
 * Risk-scoped route, which re-checks on the server that it is STILL one of a
 * group and refuses with a typed 409 otherwise. 204 on success, so this does
 * not go through `jsonRequest`, which parses a body.
 *
 * Rejects with `RiskProxyError(status, payload)`; `payload` is null when the
 * body was not JSON, so the screen's fallback applies rather than a raw page.
 */
export async function archiveDuplicateService(
  cid: string,
  serviceId: string,
): Promise<void> {
  const res = await fetch(
    `/api/proxy/risk/clients/${cid}/services/${serviceId}/archive`,
    { method: "POST", cache: "no-store" },
  );
  if (res.ok) return;
  // Read the body ONCE, then parse it (see `jsonRequest`).
  const raw = await res.text();
  let payload: unknown = null;
  try {
    payload = JSON.parse(raw);
  } catch {
    // Not JSON: no sentence of the API's to show. Thrown below, not swallowed.
    payload = null;
  }
  throw new RiskProxyError(res.status, payload);
}

/**
 * Re-exported from the neutral module: the active tenant is not a risk concern,
 * and /admin/deliverables needs the same lookup. `describeRiskError` already
 * falls back to `err.message` for a non-RiskProxyError, so callers here are
 * unaffected by the plain Error it throws.
 */
export { getActiveClientId } from "@/lib/active-client";
import { orgDisplayName } from "@/lib/org-name";

export async function getClientName(cid: string): Promise<string> {
  try {
    const clients = await jsonRequest<
      { id: string; legal_name: string | null }[]
    >("/api/proxy/admin/clients");
    // THREE absences, and they are NOT one fallback -- the earlier version of
    // this comment claimed parity with the server side and that claim is now
    // false. `|| "Client"` was satisfied by `"   "`, so a blank name rendered
    // as a blank heading, and it invented a SECOND label for "unnamed" ("Client")
    // while every other web reader says "(pending intake)".
    //
    //   * no such client        -> "Client": we could not identify the tenant
    //   * the fetch failed      -> "Client" (the catch below): same, we do not know
    //   * the client is UNNAMED -> orgDisplayName, the one label the rest of
    //                              the web uses for exactly this state
    //
    // The first two are "we cannot say who this is"; the third is "we know who
    // it is and nobody has named them". Collapsing the third into the other two
    // is what put a different word on the same state.
    const found = clients.find((c) => c.id === cid);
    return found ? orgDisplayName(found.legal_name) : "Client";
  } catch {
    return "Client";
  }
}

export async function fetchRiskGate(cid: string): Promise<RiskGate> {
  return jsonRequest<RiskGate>(`/api/proxy/risk/clients/${cid}/gate`);
}

export async function fetchRiskRegisterLatest(
  cid: string,
): Promise<RiskRegister | null> {
  try {
    return await jsonRequest<RiskRegister>(
      `/api/proxy/risk/clients/${cid}/register/latest`,
    );
  } catch (err) {
    if (err instanceof RiskProxyError && err.status === 404) return null;
    throw err;
  }
}

export async function generateRiskRegister(cid: string): Promise<RiskRegister> {
  return jsonRequest<RiskRegister>(
    `/api/proxy/risk/clients/${cid}/register/generate`,
    { method: "POST" },
  );
}

export async function exportRiskRegister(cid: string): Promise<RiskRegister> {
  return jsonRequest<RiskRegister>(
    `/api/proxy/risk/clients/${cid}/register/export`,
    { method: "POST" },
  );
}

/**
 * #737. Publish the current register to the client. Export no longer does:
 * this is the one action that puts a register on the client's dashboard.
 */
export async function publishRiskRegister(cid: string): Promise<RiskRegister> {
  return jsonRequest<RiskRegister>(
    `/api/proxy/risk/clients/${cid}/register/publish`,
    { method: "POST" },
  );
}

/**
 * #844. Set or clear one entry's likelihood and/or impact. A key left out of
 * `change` is unchanged; a key sent as `null` clears that half. Returns the
 * whole register, so every counter and banner re-derives from stored state.
 */
export async function editRiskEntryRating(
  cid: string,
  entryId: string,
  change: { likelihood?: string | null; impact?: string | null },
): Promise<RiskRegister> {
  return jsonRequest<RiskRegister>(
    `/api/proxy/risk/clients/${cid}/register/entries/${entryId}`,
    { method: "PATCH", body: change },
  );
}

export function describeRiskError(err: unknown): string {
  if (err instanceof RiskProxyError) {
    const payload = err.payload as
      { error?: { message?: string }; detail?: string } | undefined;
    return (
      payload?.error?.message ??
      payload?.detail ??
      `Request failed (${err.status}).`
    );
  }
  return err instanceof Error ? err.message : "Request failed.";
}
