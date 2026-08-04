/**
 * POST   /api/proxy/admin/llm-key - store the provider API key (issue 2).
 * DELETE /api/proxy/admin/llm-key - remove it, taking AI back offline.
 *
 * Admin-only, cross-tenant by design. The key travels only on the way IN — no
 * response from either method contains it, and it is never logged here.
 *
 * Upstream errors are forwarded verbatim so the typed D-016 refusal
 * (`llm_key_rejected` with the provider's own reason) reaches the UI as
 * actionable copy rather than a bare "Request failed".
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
    const result = await apiFetch<unknown>("/admin/llm-key", {
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
      { error: { message: "Upstream admin/llm-key call failed." } },
      { status: 502 },
    );
  }
}

export async function DELETE(): Promise<NextResponse> {
  const session = await auth();
  const bearer = session?.accessToken;
  if (!bearer) {
    return NextResponse.json(
      { error: { code: 401, message: "Not signed in." } },
      { status: 401 },
    );
  }
  try {
    await apiFetch<unknown>("/admin/llm-key", {
      method: "DELETE",
      bearer,
      clientId: "",
    });
    return new NextResponse(null, { status: 204 });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return NextResponse.json(
      { error: { message: "Upstream admin/llm-key call failed." } },
      { status: 502 },
    );
  }
}
