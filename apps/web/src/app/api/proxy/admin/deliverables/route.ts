import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

/**
 * Admin deliverables for the active tenant. `apiFetch` forwards the
 * active-client cookie as X-Client-Id, which is how the upstream route resolves
 * the tenant — so there is no client id in this path.
 */
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
    const result = await apiFetch<unknown>("/admin/deliverables", { bearer });
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return NextResponse.json(
      { error: { message: "Upstream admin call failed." } },
      { status: 502 },
    );
  }
}
