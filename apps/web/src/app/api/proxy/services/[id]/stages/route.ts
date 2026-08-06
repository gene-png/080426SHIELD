/**
 * GET /api/proxy/services/{id}/stages — derived six-stage progress.
 *
 * Read-only and presentational: the upstream derives the stages from status
 * plus evidence already in the database, and writes nothing.
 *
 * Tenant-scoped upstream: client users are pinned to their tenant server-side;
 * admins resolve via the active-client cookie that apiFetch forwards.
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
  const token = session?.accessToken ?? null;
  if (!token) {
    return NextResponse.json(
      { error: { code: 401, message: "Not signed in." } },
      { status: 401 },
    );
  }
  try {
    const result = await apiFetch<unknown>(`/services/${params.id}/stages`, {
      bearer: token,
    });
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return NextResponse.json(
      { error: { message: "Upstream stages call failed." } },
      { status: 502 },
    );
  }
}
