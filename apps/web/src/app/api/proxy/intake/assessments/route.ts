/**
 * Server-side proxy for the client's assessments list. The UI path is
 * /api/proxy/intake/assessments; the upstream FastAPI route is still
 * /intake/engagements (A2 renamed the UI only, not the backend).
 *
 * Mirrors the sibling /intake proxy: reads the access token from the
 * NextAuth session and attaches it as a Bearer header on every upstream
 * call so the browser never sees the API host or the token.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

async function bearerOrUnauthorized(): Promise<string | NextResponse> {
  const session = await auth();
  const token = session?.accessToken;
  if (!token) {
    return NextResponse.json(
      { error: { code: 401, message: "Not signed in." } },
      { status: 401 },
    );
  }
  return token;
}

export async function GET(): Promise<NextResponse> {
  const bearer = await bearerOrUnauthorized();
  if (bearer instanceof NextResponse) return bearer;
  try {
    const result = await apiFetch<unknown>("/intake/engagements", { bearer });
    return NextResponse.json(result);
  } catch (err) {
    return mapError(err);
  }
}

export async function POST(request: Request): Promise<NextResponse> {
  const bearer = await bearerOrUnauthorized();
  if (bearer instanceof NextResponse) return bearer;
  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json(
      { error: { code: 400, message: "Invalid JSON body." } },
      { status: 400 },
    );
  }
  try {
    const result = await apiFetch<unknown>("/intake/engagements", {
      method: "POST",
      bearer,
      body,
    });
    return NextResponse.json(result, { status: 201 });
  } catch (err) {
    return mapError(err);
  }
}

function mapError(err: unknown): NextResponse {
  if (err instanceof ApiError) {
    return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
      status: err.status,
    });
  }
  return NextResponse.json(
    { error: { message: "Upstream assessments call failed." } },
    { status: 502 },
  );
}
