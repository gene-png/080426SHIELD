import { expect, type APIRequestContext, type Page } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD } from "./auth";

/**
 * Runtime resolution of the seeded Atlas tenant's ids, so specs never hardcode
 * UUIDs that only hold for a seeded-once-and-persisted DB (they break the moment
 * the stack is reseeded — the exact defect this helper retires).
 *
 * Two resolution paths:
 *   - Proxy path (`atlasClientId` / `atlasServiceId`): for an admin-authenticated
 *     `page`. Goes through the Next proxy, exactly as the app does.
 *   - API-direct path (`adminApiToken` / `atlasClientIdViaApi` /
 *     `atlasServiceIdsViaApi`): for specs that already drive the FastAPI admin
 *     endpoints with a bearer (e.g. s13-isolation, whose page becomes a
 *     non-admin client user, so the proxy path is unavailable).
 *
 * The suite is serialized (playwright.config.ts: workers=1, fullyParallel=false),
 * so the proxy-path results are memoised in module state for the whole run —
 * one lookup regardless of how many specs ask.
 */

/** Upstream FastAPI base (the API-direct path bypasses the Next proxy). */
export const API_BASE = "http://localhost:8000";

interface ClientRow {
  id: string;
  legal_name: string;
}

interface Engagement {
  service_id: string;
  service_type: string;
}

/** Pick the Atlas tenant from a clients list (never a QA-* throwaway). */
function pickAtlas(clients: ClientRow[]): string {
  const atlas = clients.find((c) => /atlas/i.test(c.legal_name));
  expect(atlas, "Atlas tenant must exist in the seed").toBeTruthy();
  return (atlas as ClientRow).id;
}

// --- Proxy path (admin-authenticated page) ---------------------------------

let clientIdCache: string | undefined;
const serviceIdCache = new Map<string, string>(); // service_type -> service_id

/**
 * The Atlas tenant's client id, from the admin clients list through the Next
 * proxy. Requires an admin-authenticated `page`. Memoised for the run.
 */
export async function atlasClientId(page: Page): Promise<string> {
  if (clientIdCache) return clientIdCache;
  const res = await page.request.get("/api/proxy/admin/clients");
  expect(res.ok(), "GET /api/proxy/admin/clients").toBeTruthy();
  const { clients } = (await res.json()) as { clients: ClientRow[] };
  clientIdCache = pickAtlas(clients);
  return clientIdCache;
}

/**
 * A seeded Atlas service id by `serviceType` (e.g. "nist_csf",
 * "attack_coverage", "zero_trust_dod", "zero_trust_cisa", "tech_debt").
 *
 * Resolves via the client engagements list, which the admin proxy exposes once
 * the active-client cookie is aligned to Atlas — so this sets that cookie first
 * (a no-op for the workspaces that re-align it via EnsureActiveClient anyway).
 * Requires an admin-authenticated `page`. Memoised per service_type for the run.
 */
export async function atlasServiceId(
  page: Page,
  serviceType: string,
): Promise<string> {
  const cached = serviceIdCache.get(serviceType);
  if (cached) return cached;

  const clientId = await atlasClientId(page);
  const switched = await page.request.post("/api/active-client", {
    data: { clientId },
  });
  expect(switched.ok(), "align active client to Atlas").toBeTruthy();

  const res = await page.request.get("/api/proxy/intake/assessments");
  expect(res.ok(), "GET /api/proxy/intake/assessments").toBeTruthy();
  const engagements = (await res.json()) as Engagement[];
  for (const e of engagements) serviceIdCache.set(e.service_type, e.service_id);

  const id = serviceIdCache.get(serviceType);
  expect(
    id,
    `Atlas ${serviceType} service must exist in the seed`,
  ).toBeTruthy();
  return id as string;
}

// --- API-direct path (admin bearer against FastAPI) ------------------------

/** An admin access token from the FastAPI login endpoint. */
export async function adminApiToken(
  request: APIRequestContext,
): Promise<string> {
  const res = await request.post(`${API_BASE}/auth/login`, {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
  });
  expect(res.ok(), "admin API login").toBeTruthy();
  return ((await res.json()) as { access_token: string }).access_token;
}

/** The Atlas client id via the admin API directly (bearer, no proxy). */
export async function atlasClientIdViaApi(
  request: APIRequestContext,
  token: string,
): Promise<string> {
  const res = await request.get(`${API_BASE}/admin/clients`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(res.ok(), "GET /admin/clients (api-direct)").toBeTruthy();
  const { clients } = (await res.json()) as { clients: ClientRow[] };
  return pickAtlas(clients);
}

/**
 * All seeded Atlas service ids keyed by service_type, via the admin API
 * directly. The engagements list is tenant-scoped by the X-Client-Id header.
 */
export async function atlasServiceIdsViaApi(
  request: APIRequestContext,
  token: string,
  clientId: string,
): Promise<Map<string, string>> {
  const res = await request.get(`${API_BASE}/intake/engagements`, {
    headers: { Authorization: `Bearer ${token}`, "X-Client-Id": clientId },
  });
  expect(res.ok(), "GET /intake/engagements (api-direct)").toBeTruthy();
  const engagements = (await res.json()) as Engagement[];
  const byType = new Map<string, string>();
  for (const e of engagements) byType.set(e.service_type, e.service_id);
  return byType;
}
