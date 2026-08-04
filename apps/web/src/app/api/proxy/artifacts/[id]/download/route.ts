/**
 * Binary passthrough for the artifact download endpoint. The browser
 * never sees the API host or the bearer; this route attaches the
 * session token and streams the body + content-disposition back.
 */

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { ACTIVE_CLIENT_COOKIE } from "@/lib/api";
import { auth } from "@/lib/auth/options";

const BASE_URL = process.env.API_BASE_URL ?? "http://api:8000";

export async function GET(
  _request: Request,
  props: { params: Promise<{ id: string }> },
): Promise<Response> {
  const params = await props.params;
  const session = await auth();
  const token = session?.accessToken;
  if (!token) {
    return NextResponse.json(
      { error: { code: 401, message: "Not signed in." } },
      { status: 401 },
    );
  }
  // Hand-rolled binary proxy, so forward the active-client cookie as
  // X-Client-Id ourselves (the backend download guard is tenant-scoped).
  const reqHeaders: Record<string, string> = {
    Authorization: `Bearer ${token}`,
  };
  const activeClient = (await cookies()).get(ACTIVE_CLIENT_COOKIE)?.value;
  if (activeClient) {
    reqHeaders["X-Client-Id"] = activeClient;
  }
  const upstream = await fetch(`${BASE_URL}/artifacts/${params.id}/download`, {
    headers: reqHeaders,
    cache: "no-store",
  });
  if (!upstream.ok) {
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("Content-Type") ?? "application/json",
      },
    });
  }
  const headers = new Headers();
  const ct = upstream.headers.get("Content-Type");
  if (ct) headers.set("Content-Type", ct);
  const cd = upstream.headers.get("Content-Disposition");
  if (cd) headers.set("Content-Disposition", cd);
  return new Response(upstream.body, { status: 200, headers });
}
