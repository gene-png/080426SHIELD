"use client";

/**
 * The admin client switcher's active tenant, read from the cookie-backed
 * `/api/active-client` route.
 *
 * Any admin surface that scopes data to one tenant has to resolve this BEFORE
 * it calls a tenant-scoped endpoint. `require_client` (apps/api/app/dependencies.py)
 * rejects a platform admin with no `X-Client-Id` as a 400, so a surface that
 * fetches first and reports whatever comes back turns "you have not picked a
 * client yet" into a raw upstream status — which is what /admin/deliverables
 * did until 2026-08-07.
 *
 * Lives here rather than under `lib/risk/` because it is not risk-specific;
 * `lib/risk/client.ts` re-exports it so its own callers are unaffected.
 */
export async function getActiveClientId(): Promise<string | null> {
  const res = await fetch("/api/active-client", {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`Could not read the active client (${res.status}).`);
  }
  const body = (await res.json()) as { active: string | null };
  return body.active;
}
