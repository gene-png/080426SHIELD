/**
 * T6, the client-scoped navigation frame (#736 issuecomment-6204357376, plan
 * issuecomment-6204457912): routes, their tables, and the server-side checks
 * every frame page runs before it renders.
 *
 * SERVER ONLY (it calls `apiFetch`). The client a page serves comes from its
 * URL and is passed to the API EXPLICITLY on every tenant read, so the
 * active-client cookie never decides what the frame shows. The URL is not
 * authorization: each page re-checks the client (admin-only read) and that the
 * service it names belongs to that client, and refuses with `notFound()`.
 */
import { notFound } from "next/navigation";

import {
  KIND_ORDER,
  sectionHref,
  type ClientFrame,
  type FrameService,
} from "@/components/service-shell/frameRoutes";
import type { FrameKind } from "@/components/service-shell/shellCopy";
import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";
import { orgDisplayName } from "@/lib/org-name";

/** 403 / 404 / 422 from a read naming a client or service: not found. */
function isRefusal(err: unknown): boolean {
  return err instanceof ApiError && [403, 404, 422].includes(err.status);
}

/**
 * The bearer of an ADMIN session, or `notFound()` before any API call. The
 * admin layout already shows non-admins its own page; this keeps a frame page
 * from fetching anything on their behalf regardless.
 */
export async function requireAdminBearer(): Promise<string> {
  const session = await auth();
  if (!session?.accessToken || session.role !== "admin") {
    console.warn("[client_frame] refused: not an admin session");
    notFound();
  }
  return session.accessToken;
}

/** `ClientSwitcher`'s and RR-2's label: `dba (legal)` or the legal name. */
function clientLabel(row: {
  legal_name: string | null;
  dba_name: string | null;
}): string {
  return row.dba_name
    ? `${row.dba_name} (${orgDisplayName(row.legal_name)})`
    : orgDisplayName(row.legal_name);
}

function parseServices(body: unknown): FrameService[] {
  if (!Array.isArray(body))
    throw new Error("client_frame: /intake/engagements did not return a list");
  return body.flatMap((row: Record<string, unknown>) => {
    const kind = row?.service_type;
    if (
      typeof row?.service_id !== "string" ||
      typeof row.status !== "string" ||
      typeof row.created_at !== "string" ||
      typeof kind !== "string"
    )
      throw new Error("client_frame: an engagement row is malformed");
    // `consultation` has no workspace, so no place in the frame. Any OTHER
    // kind the frame does not know is refused loudly, never dropped: a new
    // service kind must not vanish from the rail without a sign.
    if (kind === "consultation") return [];
    if (!KIND_ORDER.includes(kind as FrameKind))
      throw new Error(`client_frame: unknown service kind "${kind}"`);
    return [
      {
        service_id: row.service_id,
        service_type: kind as FrameKind,
        status: row.status,
        created_at: row.created_at,
      },
    ];
  });
}

/**
 * Every frame page's first call: an admin session, the URL's client (admin-only
 * read, refused as not found), and that client's services read with ITS id.
 */
export async function loadClientFrame(clientId: string): Promise<ClientFrame> {
  const bearer = await requireAdminBearer();
  let row: { legal_name: string | null; dba_name: string | null };
  try {
    row = await apiFetch(`/admin/clients/${encodeURIComponent(clientId)}`, {
      bearer,
      clientId: "",
    });
  } catch (err) {
    if (isRefusal(err)) {
      console.warn("[client_frame] refused: client not found", clientId);
      notFound();
    }
    throw err;
  }
  const services = parseServices(
    await apiFetch<unknown>("/intake/engagements", { bearer, clientId }),
  );
  console.info(
    "[client_frame] loaded",
    clientId,
    `${services.length} services`,
  );
  return {
    bearer,
    client: { id: clientId, label: clientLabel(row) },
    services,
  };
}

/**
 * The old `/admin/services/{id}/{segment}` URL's new home, from the
 * admin-only, cross-tenant service read. Not found for an unknown id.
 */
export async function newUrlForOldService(serviceId: string): Promise<string> {
  const bearer = await requireAdminBearer();
  let svc: { kind: string; client_id: string };
  try {
    svc = await apiFetch(`/admin/services/${encodeURIComponent(serviceId)}`, {
      bearer,
      clientId: "",
    });
  } catch (err) {
    if (isRefusal(err)) {
      console.warn("[client_frame] old URL: service not found", serviceId);
      notFound();
    }
    throw err;
  }
  if (!KIND_ORDER.includes(svc.kind as FrameKind))
    throw new Error(`client_frame: service ${serviceId} has kind ${svc.kind}`);
  return sectionHref(
    svc.client_id,
    svc.kind as FrameKind,
    "overview",
    serviceId,
  );
}
