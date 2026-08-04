/**
 * Shared proxy helper for AI routes.
 *
 * Thin pass-through to the FastAPI backend with the session bearer attached
 * server-side and the active-client cookie forwarded as X-Client-Id (via
 * apiFetch). Mirrors apps/web/src/app/api/proxy/csf/_proxy.ts.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

export async function proxyAiJson(
  request: Request,
  upstream: string,
): Promise<NextResponse> {
  const session = await auth();
  const token = session?.accessToken;
  if (!token) {
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
    const result = await apiFetch(upstream, {
      method: "POST",
      bearer: token,
      body: body as Record<string, unknown> | undefined,
    });
    return NextResponse.json(result ?? {});
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return NextResponse.json(
      { error: { message: "Upstream AI call failed." } },
      { status: 502 },
    );
  }
}
