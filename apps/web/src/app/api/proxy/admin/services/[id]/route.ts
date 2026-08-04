/**
 * GET /api/proxy/admin/services/:id - service detail (admin).
 *
 * Used by the workspace shell to resolve which client a service belongs to,
 * so it can set that as the active tenant before its tenant-scoped data
 * calls. Cross-tenant by design (admin-only); does not forward X-Client-Id.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

export async function GET(
  _request: Request,
  props: { params: Promise<{ id: string }> },
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
  try {
    const result = await apiFetch<unknown>(`/admin/services/${params.id}`, {
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
      { error: { message: "Upstream admin/services call failed." } },
      { status: 502 },
    );
  }
}
