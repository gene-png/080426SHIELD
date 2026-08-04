/**
 * Set/clear the active client id cookie used by the client switcher.
 *
 * Multi-tenant: admin users pick which client they are viewing.
 * The cookie is read by `lib/api.ts` and forwarded to the FastAPI backend
 * as `X-Client-Id`. Client-role users don't use this; their tenant is
 * pinned server-side.
 */

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { ACTIVE_CLIENT_COOKIE } from "@/lib/api";

const UUID_RE =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

export async function GET(): Promise<NextResponse> {
  const value = (await cookies()).get(ACTIVE_CLIENT_COOKIE)?.value ?? null;
  return NextResponse.json({ active: value });
}

export async function POST(request: Request): Promise<NextResponse> {
  let body: { clientId?: string | null };
  try {
    body = (await request.json()) as { clientId?: string | null };
  } catch {
    return NextResponse.json({ error: "Body must be JSON." }, { status: 400 });
  }

  const jar = await cookies();
  if (body.clientId == null || body.clientId === "") {
    jar.delete(ACTIVE_CLIENT_COOKIE);
    return NextResponse.json({ active: null });
  }
  if (typeof body.clientId !== "string" || !UUID_RE.test(body.clientId)) {
    return NextResponse.json(
      { error: "clientId must be a UUID." },
      { status: 422 },
    );
  }
  jar.set(ACTIVE_CLIENT_COOKIE, body.clientId, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
  });
  return NextResponse.json({ active: body.clientId });
}
