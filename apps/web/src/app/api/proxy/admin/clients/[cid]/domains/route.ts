/**
 * GET  /api/proxy/admin/clients/{cid}/domains - list a client's approved domains.
 * POST /api/proxy/admin/clients/{cid}/domains - approve a domain for a client.
 * Admin-only; cross-tenant by design (no X-Client-Id forwarded).
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

function mapError(err: unknown): NextResponse {
  if (err instanceof ApiError) {
    return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
      status: err.status,
    });
  }
  return NextResponse.json(
    { error: { message: "Upstream admin/domains call failed." } },
    { status: 502 },
  );
}

export async function GET(
  _request: Request,
  props: { params: Promise<{ cid: string }> },
): Promise<NextResponse> {
  const params = await props.params;
  const token = await bearer();
  if (!token) return unauthorized();
  try {
    const result = await apiFetch<unknown>(
      `/admin/clients/${params.cid}/domains`,
      { bearer: token, clientId: "" },
    );
    return NextResponse.json(result);
  } catch (err) {
    return mapError(err);
  }
}

export async function POST(
  request: Request,
  props: { params: Promise<{ cid: string }> },
): Promise<NextResponse> {
  const params = await props.params;
  const token = await bearer();
  if (!token) return unauthorized();
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    body = undefined;
  }
  try {
    const result = await apiFetch<unknown>(
      `/admin/clients/${params.cid}/domains`,
      {
        method: "POST",
        body: body as Record<string, unknown> | undefined,
        bearer: token,
        clientId: "",
      },
    );
    return NextResponse.json(result, { status: 201 });
  } catch (err) {
    return mapError(err);
  }
}
