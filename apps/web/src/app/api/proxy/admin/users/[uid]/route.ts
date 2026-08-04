/**
 * PATCH /api/proxy/admin/users/{uid} - deactivate or reactivate a user (issue 3).
 *
 * Admin-only, cross-tenant by design. Deactivation is the user-removal
 * primitive: sign-in refuses an inactive account, so the user is locked out
 * immediately while every row they authored is retained.
 *
 * Upstream errors are forwarded verbatim so the typed D-016 refusal (e.g.
 * `cannot_deactivate_self`) reaches the Management UI as friendly copy rather
 * than a bare "Request failed".
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

export async function PATCH(
  request: Request,
  props: { params: Promise<{ uid: string }> },
): Promise<NextResponse> {
  const params = await props.params;
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
    const result = await apiFetch<unknown>(`/admin/users/${params.uid}`, {
      method: "PATCH",
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
      { error: { message: "Upstream admin/users call failed." } },
      { status: 502 },
    );
  }
}
