import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";
import { clientIdRequired, pickedClientId } from "@/lib/proxy-client-id";
import { upstreamOutcomeUnknown } from "@/lib/upstream-outcome-unknown";

/**
 * Admin deliverables for the client the page's picker chose, sent as
 * `?client_id=` and forwarded as X-Client-Id (RR-2, for #1121). The cookie is
 * never read: an absent or empty id is refused before any upstream call.
 */
export async function GET(request: Request): Promise<NextResponse> {
  const clientId = pickedClientId(request);
  if (clientId === null) return clientIdRequired("/admin/deliverables");
  const session = await auth();
  const bearer = session?.accessToken;
  if (!bearer) {
    return NextResponse.json(
      { error: { code: 401, message: "Not signed in." } },
      { status: 401 },
    );
  }
  try {
    const result = await apiFetch<unknown>("/admin/deliverables", {
      bearer,
      clientId,
    });
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return upstreamOutcomeUnknown(err, "Upstream admin call");
  }
}
