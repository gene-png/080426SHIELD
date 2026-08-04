/**
 * Server-side proxy for /intake on the FastAPI backend.
 *
 * Reads the access token from the NextAuth session and attaches it as a
 * Bearer header on every upstream call. The browser never sees the API
 * host name or the token.
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
    const result = await apiFetch<unknown>("/intake", { bearer });
    return NextResponse.json(result);
  } catch (err) {
    return mapError(err);
  }
}

export async function PATCH(request: Request): Promise<NextResponse> {
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
    const result = await apiFetch<unknown>("/intake", {
      method: "PATCH",
      bearer,
      body,
    });
    return NextResponse.json(result);
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
    { error: { message: "Upstream intake call failed." } },
    { status: 502 },
  );
}
