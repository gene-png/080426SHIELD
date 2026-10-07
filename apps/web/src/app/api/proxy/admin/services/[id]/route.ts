/**
 * GET /api/proxy/admin/services/:id - service detail (admin).
 * DELETE /api/proxy/admin/services/:id - archive a service (admin, #896).
 *
 * Used by the workspace shell to resolve which client a service belongs to,
 * so it can set that as the active tenant before its tenant-scoped data
 * calls. Cross-tenant by design (admin-only); does not forward X-Client-Id.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";
import { upstreamOutcomeUnknown } from "@/lib/upstream-outcome-unknown";

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
    return upstreamOutcomeUnknown(err, "Upstream admin/services call");
  }
}

/**
 * DELETE /api/proxy/admin/services/:id - archive a service (admin, #896).
 *
 * The Risk Register's duplicate banner calls this, so a consultant can clear
 * its two-of-a-kind refusal from the screen. Upstream only sets the service's
 * status to archived and writes an audit row; nothing is deleted, and there is
 * no unarchive route. Cross-tenant by design, like GET above.
 */
export async function DELETE(
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
    await apiFetch<unknown>(`/admin/services/${params.id}`, {
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
    return upstreamOutcomeUnknown(err, "Upstream admin/services archive call");
  }
}
