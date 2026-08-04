/**
 * GET/POST /api/proxy/services/{id}/messages — per-assessment message thread.
 *
 * Tenant-scoped upstream: client users are pinned to their tenant server-side;
 * admins resolve via the active-client cookie that apiFetch forwards.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

async function bearer(): Promise<string | null> {
  const session = await auth();
  return session?.accessToken ?? null;
}

function unauthorized(): NextResponse {
  return NextResponse.json(
    { error: { code: 401, message: "Not signed in." } },
    { status: 401 },
  );
}

function fail(err: unknown): NextResponse {
  if (err instanceof ApiError) {
    return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
      status: err.status,
    });
  }
  return NextResponse.json(
    { error: { message: "Upstream messages call failed." } },
    { status: 502 },
  );
}

export async function GET(
  _request: Request,
  props: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const params = await props.params;
  const token = await bearer();
  if (!token) return unauthorized();
  try {
    const result = await apiFetch<unknown>(`/services/${params.id}/messages`, {
      bearer: token,
    });
    return NextResponse.json(result);
  } catch (err) {
    return fail(err);
  }
}

export async function POST(
  request: Request,
  props: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const params = await props.params;
  const token = await bearer();
  if (!token) return unauthorized();
  let body: Record<string, unknown> | undefined;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    body = undefined;
  }
  try {
    const result = await apiFetch<unknown>(`/services/${params.id}/messages`, {
      method: "POST",
      bearer: token,
      body,
    });
    return NextResponse.json(result);
  } catch (err) {
    return fail(err);
  }
}
