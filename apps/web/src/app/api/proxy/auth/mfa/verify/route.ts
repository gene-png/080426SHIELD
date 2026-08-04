/**
 * POST /api/proxy/auth/mfa/verify - confirm TOTP enrollment (Sprint 6 T4).
 * Forwards the code to the API, which flips mfa_enrolled and returns one-time
 * recovery codes (shown to the user exactly once). Requires a session.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

export async function POST(request: Request): Promise<NextResponse> {
  const session = await auth();
  const bearer = session?.accessToken;
  if (!bearer) {
    return NextResponse.json(
      { error: { code: 401, message: "Not signed in." } },
      { status: 401 },
    );
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    body = undefined;
  }
  try {
    const result = await apiFetch<unknown>("/auth/mfa/verify", {
      method: "POST",
      body: body as Record<string, unknown> | undefined,
      bearer,
      clientId: "",
    });
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return NextResponse.json(
      { error: { message: "Upstream mfa/verify call failed." } },
      { status: 502 },
    );
  }
}
