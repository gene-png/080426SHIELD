/**
 * GET /api/proxy/health/ready - proxy the API readiness matrix (admin).
 * `/ready` on the API is public and always returns 200 (with a ready flag),
 * but we gate the operator view behind an admin session so the dependency
 * detail isn't exposed to anonymous callers.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

export async function GET(): Promise<NextResponse> {
  const session = await auth();
  if (!session || session.role !== "admin") {
    return NextResponse.json(
      { error: { code: 403, message: "Admin only." } },
      { status: 403 },
    );
  }
  try {
    const result = await apiFetch<unknown>("/ready", { clientId: "" });
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return NextResponse.json(
      { error: { message: "Upstream readiness call failed." } },
      { status: 502 },
    );
  }
}
