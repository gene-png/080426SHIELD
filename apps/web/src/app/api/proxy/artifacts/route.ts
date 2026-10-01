/**
 * Multipart proxy for /artifacts. The Next.js route reads the inbound
 * FormData, attaches the session's access token, and forwards to the
 * FastAPI upload endpoint. The browser never sees the API host name or
 * the access token.
 */

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { ACTIVE_CLIENT_COOKIE } from "@/lib/api";
import { auth } from "@/lib/auth/options";
import { upstreamOutcomeUnknown } from "@/lib/upstream-outcome-unknown";

const BASE_URL = process.env.API_BASE_URL ?? "http://api:8000";

async function bearerOrUnauthorized(): Promise<string | NextResponse> {
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

/**
 * Bearer + tenant headers for the upstream call. This route hand-rolls the
 * proxy (multipart can't go through `lib/api.ts`), so we forward the active
 * client cookie as X-Client-Id ourselves - otherwise admin uploads
 * hit the backend's `current_client` guard and 400. Don't set Content-Type:
 * `fetch` derives the multipart boundary from the FormData body.
 */
async function upstreamHeaders(
  bearer: string,
): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${bearer}`,
  };
  const activeClient = (await cookies()).get(ACTIVE_CLIENT_COOKIE)?.value;
  if (activeClient) {
    headers["X-Client-Id"] = activeClient;
  }
  return headers;
}

export async function POST(request: Request): Promise<NextResponse> {
  const bearer = await bearerOrUnauthorized();
  if (bearer instanceof NextResponse) return bearer;

  // Forward the FormData payload as-is so multipart boundaries and the
  // raw file bytes are preserved.
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json(
      { error: { code: 400, message: "Multipart body required." } },
      { status: 400 },
    );
  }

  // #550: the fetch sat outside any `try`, so a timeout or reset was an
  // unhandled throw. Reading the body is inside too: a reset mid-body is the
  // same "we did not see the answer". The `try` that used to wrap the
  // `NextResponse` constructor caught nothing that can throw there.
  let upstream: Response;
  let body: string;
  try {
    upstream = await fetch(`${BASE_URL}/artifacts`, {
      method: "POST",
      headers: await upstreamHeaders(bearer),
      body: form,
    });
    body = await upstream.text();
  } catch (err) {
    return upstreamOutcomeUnknown(err, "artifacts upload");
  }
  return new NextResponse(body, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("Content-Type") ?? "application/json",
    },
  });
}

export async function GET(): Promise<NextResponse> {
  const bearer = await bearerOrUnauthorized();
  if (bearer instanceof NextResponse) return bearer;
  let upstream: Response;
  let body: string;
  try {
    upstream = await fetch(`${BASE_URL}/artifacts`, {
      headers: await upstreamHeaders(bearer),
      cache: "no-store",
    });
    body = await upstream.text();
  } catch (err) {
    return upstreamOutcomeUnknown(err, "artifacts list");
  }
  return new NextResponse(body, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("Content-Type") ?? "application/json",
    },
  });
}
