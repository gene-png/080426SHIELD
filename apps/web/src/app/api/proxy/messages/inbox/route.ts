/**
 * GET /api/proxy/messages/inbox — per-service thread summaries + unread counts
 * for the client named by `?client_id=` (RR-2, for #1121: the admin Messages
 * page's picker; the cookie is never read). Client users are pinned to their
 * own tenant server-side, so the explicit id cannot widen their scope.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";
import { clientIdRequired, pickedClientId } from "@/lib/proxy-client-id";
import { upstreamOutcomeUnknown } from "@/lib/upstream-outcome-unknown";

export async function GET(request: Request): Promise<NextResponse> {
  const clientId = pickedClientId(request);
  if (clientId === null) return clientIdRequired("/messages/inbox");
  const session = await auth();
  const token = session?.accessToken;
  if (!token) {
    return NextResponse.json(
      { error: { code: 401, message: "Not signed in." } },
      { status: 401 },
    );
  }
  try {
    const result = await apiFetch<unknown>("/messages/inbox", {
      bearer: token,
      clientId,
    });
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return upstreamOutcomeUnknown(err, "Upstream inbox call");
  }
}
