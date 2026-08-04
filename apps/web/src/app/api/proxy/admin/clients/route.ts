/**
 * GET /api/proxy/admin/clients - list all client tenants (admin).
 * POST /api/proxy/admin/clients - create a new client tenant (admin).
 *
 * These power the client-switcher dropdown in the top nav. The list view
 * intentionally does NOT forward X-Client-Id (cross-tenant by design).
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

export async function GET(): Promise<NextResponse> {
  const session = await auth();
  const bearer = session?.accessToken;
  if (!bearer) {
    return NextResponse.json(
      { error: { code: 401, message: "Not signed in." } },
      { status: 401 },
    );
  }
  try {
    const result = await apiFetch<unknown>("/admin/clients", {
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
      { error: { message: "Upstream admin/clients call failed." } },
      { status: 502 },
    );
  }
}

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
    const result = await apiFetch<unknown>("/admin/clients", {
      method: "POST",
      body: body as Record<string, unknown> | undefined,
      bearer,
      clientId: "",
    });
    return NextResponse.json(result, { status: 201 });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return NextResponse.json(
      { error: { message: "Upstream admin/clients call failed." } },
      { status: 502 },
    );
  }
}
