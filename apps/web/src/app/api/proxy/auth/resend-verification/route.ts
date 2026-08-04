/**
 * Server-side proxy for /auth/resend-verification (Sprint 6 T5, D-028).
 * Enumeration-safe: the upstream returns the same message regardless of whether
 * the account exists.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";

interface ProxyBody {
  email?: string;
}

export async function POST(request: Request): Promise<NextResponse> {
  let body: ProxyBody;
  try {
    body = (await request.json()) as ProxyBody;
  } catch {
    return NextResponse.json(
      { error: { message: "Invalid JSON body." } },
      { status: 400 },
    );
  }
  try {
    const result = await apiFetch<unknown>("/auth/resend-verification", {
      method: "POST",
      body: body as unknown as Record<string, unknown>,
    });
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return NextResponse.json(
      { error: { message: "Upstream resend-verification call failed." } },
      { status: 502 },
    );
  }
}
