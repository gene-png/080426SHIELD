import { cookies } from "next/headers";

import { ACTIVE_CLIENT_COOKIE, apiFetch } from "@/lib/api";

interface MeResponse {
  role: "admin" | "client";
  client_id: string | null;
}

interface AdminServiceDetail {
  client_id: string;
}

/**
 * Resolve the tenant a service dashboard belongs to (issue 4).
 *
 * Client users are pinned to their own tenant, so `/auth/me` answers it. A
 * platform admin has no pinned tenant and normally carries one in the
 * active-client cookie — but that cookie is only set once they've been inside a
 * workspace. Following the "View dashboard" link from a deliverable card in a
 * fresh session (or pasting the URL) previously produced an unhandled API 400
 * and a Next.js server-exception page.
 *
 * For admins we therefore fall back to asking which tenant owns the service.
 * `/admin/services/{id}` is admin-only and cross-tenant by design, so this
 * cannot widen what a client can see: a client never reaches this branch.
 */
export async function resolveDashboardClientId(
  token: string,
  serviceId?: string,
): Promise<string | undefined> {
  const me = await apiFetch<MeResponse>("/auth/me", {
    bearer: token,
    clientId: "",
  });
  if (me.client_id) return me.client_id;

  const fromCookie = (await cookies()).get(ACTIVE_CLIENT_COOKIE)?.value;
  if (fromCookie) return fromCookie;

  if (me.role === "admin" && serviceId) {
    try {
      const svc = await apiFetch<AdminServiceDetail>(
        `/admin/services/${serviceId}`,
        { bearer: token, clientId: "" },
      );
      return svc.client_id;
    } catch {
      // Fall through to undefined — the caller renders "not available yet",
      // which is the honest answer when we can't establish the tenant.
      return undefined;
    }
  }
  return undefined;
}
