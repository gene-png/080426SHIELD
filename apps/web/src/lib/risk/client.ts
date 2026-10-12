"use client";

import type { RiskGate, RiskInclude, RiskRegister } from "./types";

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
 * Rejects with `RiskProxyError(status, payload)`. `payload` is null when the
 * body was not JSON, and it can be a STRING when the Risk proxy re-sent a
 * gateway's unparseable body (`lib/api.ts` keeps it raw). The archive dialog
 * reads anything that is not a JSON object as no answer at all, and reports
 * the outcome as unconfirmed (#896 R3-3 and round 4, F1) -- never as the
 * fallback "Nothing was changed.", which would assert an unknown outcome.
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
    // Not JSON: no answer from the API, so the screen reports the outcome as
    // unconfirmed. Thrown below, not swallowed.
    payload = null;
  }
  throw new RiskProxyError(res.status, payload);
}

// RR-2 (for #1121): `getActiveClientId` and `getClientName` were here. The
// Risk Register now takes its client, and the client's name, from the page's
// own picker (`lib/admin/client-choice.ts`), which reads the list as the
// `{clients: [...]}` the route returns. `getClientName` read it as a bare
// array, so its silent catch always answered "Client".

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

/**
 * RR-1 (for #1122), design note §3.1: ALWAYS sends the admin's selection.
 * The page never relies on the absent-body default, which refuses a client
 * with both Zero Trust frameworks rather than guess.
 */
export async function generateRiskRegister(
  cid: string,
  include: RiskInclude,
): Promise<RiskRegister> {
  return jsonRequest<RiskRegister>(
    `/api/proxy/risk/clients/${cid}/register/generate`,
    { method: "POST", body: { include } },
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
