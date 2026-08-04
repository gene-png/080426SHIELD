/**
 * Shared proxy helpers for tech-debt routes.
 *
 * Each tech-debt route is a thin pass-through to the FastAPI backend with
 * the session bearer attached. This module pulls the boilerplate into one
 * place so adding a new route is a one-liner.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

export async function getBearer(): Promise<string | NextResponse> {
  const session = await auth();
  const token = session?.accessToken;
  if (!token) {
    return NextResponse.json(
      { error: { code: 401, message: "Not signed in." } },
      { status: 401 },
    );
  }
  return token;
}

export async function proxyJson<T = unknown>(
  upstream: string,
  init: { method: "GET" | "POST" | "PATCH" | "DELETE"; body?: unknown } = {
    method: "GET",
  },
): Promise<NextResponse> {
  const bearer = await getBearer();
  if (bearer instanceof NextResponse) return bearer;
  try {
    const result = await apiFetch<T>(upstream, {
      method: init.method,
      bearer,
      body: init.body as Record<string, unknown> | undefined,
    });
    return NextResponse.json(result ?? {});
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return NextResponse.json(
      { error: { message: "Upstream tech-debt call failed." } },
      { status: 502 },
    );
  }
}

export async function proxyJsonFromRequest(
  request: Request,
  upstream: string,
  method: "POST" | "PATCH",
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    body = undefined;
  }
  return proxyJson(upstream, { method, body });
}
