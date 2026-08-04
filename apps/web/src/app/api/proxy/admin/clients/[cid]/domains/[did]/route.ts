/**
 * DELETE /api/proxy/admin/clients/{cid}/domains/{did} - remove an approved domain.
 * Admin-only; cross-tenant by design.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

export async function DELETE(
  _request: Request,
  props: { params: Promise<{ cid: string; did: string }> },
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
    await apiFetch<unknown>(
      `/admin/clients/${params.cid}/domains/${params.did}`,
      { method: "DELETE", bearer: token, clientId: "" },
    );
    return new NextResponse(null, { status: 204 });
  } catch (err) {
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
}
