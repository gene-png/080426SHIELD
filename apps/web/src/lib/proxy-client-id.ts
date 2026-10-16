import { NextResponse } from "next/server";

/**
 * RR-2 (for #1121), design note §3.2. The twin admin pages (Risk Register,
 * Deliverables, Messages) scope their data by the client chosen in their own
 * picker, sent as `?client_id=`. The active-client cookie is shared by every
 * tab, so a proxy that fell back to it could answer for another tenant.
 *
 * `null` means the request named no client, or an EMPTY one. Both are
 * refused: `apiFetch` maps `clientId: ""` to no header but `undefined` to the
 * cookie, so `searchParams.get("client_id") ?? undefined` would silently
 * reinstate the cookie. Nothing is passed through.
 */
export function pickedClientId(request: Request): string | null {
  const id = new URL(request.url).searchParams.get("client_id");
  return id ? id : null;
}

/**
 * The refusal. Deliberately NO `message`: the pages only fetch with an id, so
 * this answer means a page bug, and a sentence rendered under "Deliverables for
 * {client}" would contradict the header with nothing the reader can do about
 * it. With no message, each fetcher shows its existing fallback, and the bug is
 * loud in the log instead.
 */
export function clientIdRequired(route: string): NextResponse {
  console.error(`proxy.client_id_missing route=${route}`);
  return NextResponse.json(
    { error: { code: 400, reason: "client_id_required" } },
    { status: 400 },
  );
}

/**
 * #1262, the `/intake` residual. A client the request NAMES (`?client_id=`)
 * wins over the shared active-client cookie, which another tab may have
 * rewritten since the page loaded. An EMPTY value is refused, as above. With
 * no parameter, `undefined`: `apiFetch` then reads the cookie, as before. It
 * cannot widen access: the api pins a client-role user to its own client
 * whatever X-Client-Id says (`current_client`).
 */
export function namedClientId(
  request: Request,
  route: string,
): string | undefined | NextResponse {
  const params = new URL(request.url).searchParams;
  if (!params.has("client_id")) return undefined;
  const id = params.get("client_id");
  return id ? id : clientIdRequired(route);
}
