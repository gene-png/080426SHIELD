/**
 * POST /api/proxy/auth/mfa/enroll - begin TOTP MFA enrollment (Sprint 6 T4).
 * Returns the otpauth provisioning URI + secret for the signed-in user so the
 * account page can render enrollment details. Requires an authenticated session.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

export async function POST(): Promise<NextResponse> {
  const session = await auth();
  const bearer = session?.accessToken;
  if (!bearer) {
    return NextResponse.json(
      { error: { code: 401, message: "Not signed in." } },
      { status: 401 },
    );
  }
  try {
    const result = await apiFetch<unknown>("/auth/mfa/enroll", {
      method: "POST",
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
      { error: { message: "Upstream mfa/enroll call failed." } },
      { status: 502 },
    );
  }
}
