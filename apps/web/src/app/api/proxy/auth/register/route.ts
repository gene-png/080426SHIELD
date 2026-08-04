/**
 * Server-side proxy for /auth/register on the FastAPI backend.
 *
 * Keeps the API host name off the wire to the browser and runs the body
 * through the typed `apiFetch` helper so any error shape changes only
 * need to be fixed in one place.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";

interface ProxyBody {
  email?: string;
  password?: string;
  display_name?: string;
  title?: string | null;
  phone?: string | null;
  timezone?: string;
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
    const result = await apiFetch<unknown>("/auth/register", {
      method: "POST",
      body: body as unknown as Record<string, unknown>,
    });
    return NextResponse.json(result, { status: 201 });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return NextResponse.json(
      { error: { message: "Upstream registration failed." } },
      { status: 502 },
    );
  }
}
