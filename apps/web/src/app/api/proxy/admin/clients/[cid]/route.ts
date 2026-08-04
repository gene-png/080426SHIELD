/**
 * DELETE /api/proxy/admin/clients/{cid} - archive a client tenant (issue 3).
 *
 * Admin-only, cross-tenant by design (no X-Client-Id forwarded). Archiving is
 * a soft removal upstream: the tenant drops out of the live client list and the
 * intake-queue org index, but every row it owns is retained.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

export async function DELETE(
  _request: Request,
  props: { params: Promise<{ cid: string }> },
): Promise<NextResponse> {
  const params = await props.params;
  const session = await auth();
  const token = session?.accessToken;
  if (!token) {
    return NextResponse.json(
      { error: { code: 401, message: "Not signed in." } },
      { status: 401 },
    );
  }
  try {
    await apiFetch<unknown>(`/admin/clients/${params.cid}`, {
      method: "DELETE",
      bearer: token,
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
      { error: { message: "Upstream admin/clients archive call failed." } },
      { status: 502 },
    );
  }
}
