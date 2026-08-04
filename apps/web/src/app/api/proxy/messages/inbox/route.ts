/**
 * GET /api/proxy/messages/inbox — per-service thread summaries + unread counts
 * for the active client (admins via the active-client cookie; client users are
 * pinned to their own tenant server-side).
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

export async function GET(): Promise<NextResponse> {
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
    });
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return NextResponse.json(
      { error: { message: "Upstream inbox call failed." } },
      { status: 502 },
    );
  }
}
