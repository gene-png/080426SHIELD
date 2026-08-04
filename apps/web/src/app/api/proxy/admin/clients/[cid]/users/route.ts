/**
 * GET /api/proxy/admin/clients/{cid}/users - list a tenant's users (issue 3).
 *
 * Admin-only, cross-tenant by design. Includes deactivated users so the
 * Management UI can label and reactivate them.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

export async function GET(
  _request: Request,
  props: { params: Promise<{ cid: string }> },
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
    const result = await apiFetch<unknown>(
      `/admin/clients/${params.cid}/users`,
      { bearer, clientId: "" },
    );
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return NextResponse.json(
      { error: { message: "Upstream admin/clients users call failed." } },
      { status: 502 },
    );
  }
}
