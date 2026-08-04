/**
 * GET /api/proxy/admin/llm-calls - read the AI egress log (admin).
 * Forwards filter + cursor query params through to the backend. Not
 * tenant-scoped (cross-tenant admin surface), so X-Client-Id is suppressed.
 * Read-only over an append-only store.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

export async function GET(request: Request): Promise<NextResponse> {
  const session = await auth();
  const bearer = session?.accessToken;
  if (!bearer) {
    return NextResponse.json(
      { error: { code: 401, message: "Not signed in." } },
      { status: 401 },
    );
  }
  const search = new URL(request.url).search;
  try {
    const result = await apiFetch<unknown>(`/admin/llm-calls${search}`, {
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
      { error: { message: "Upstream llm-calls call failed." } },
      { status: 502 },
    );
  }
}
