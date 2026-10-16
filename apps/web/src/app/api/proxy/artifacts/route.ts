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
import { clientIdRequired } from "@/lib/proxy-client-id";
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
 * #1262: the tenant an UPLOAD is filed under. A client the request names
 * (`?client_id=`, an admin workspace's own tenant) wins over the shared
 * cookie, which another tab may have rewritten. An EMPTY value is refused, as
 * the download proxy does. With no parameter, the cookie as before: the
 * client wizard names none. It cannot widen access: the api pins a
 * client-role user to its own client whatever X-Client-Id says
 * (`current_client`).
 */
async function uploadClient(
  request: Request,
): Promise<string | undefined | NextResponse> {
  const named = new URL(request.url).searchParams;
  if (named.has("client_id")) {
    const id = named.get("client_id");
    return id ? id : clientIdRequired("/artifacts");
  }
  return (await cookies()).get(ACTIVE_CLIENT_COOKIE)?.value;
}

/**
 * Bearer + tenant headers for the upstream call. This route hand-rolls the
 * proxy (multipart can't go through `lib/api.ts`), so it forwards the tenant
 * as X-Client-Id itself - otherwise admin calls hit the backend's
 * `current_client` guard and 400. Don't set Content-Type: `fetch` derives
 * the multipart boundary from the FormData body.
 */
async function upstreamHeaders(
  bearer: string,
  activeClient?: string,
): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${bearer}`,
  };
  if (activeClient) {
    headers["X-Client-Id"] = activeClient;
  }
  return headers;
}

export async function POST(request: Request): Promise<NextResponse> {
  const bearer = await bearerOrUnauthorized();
  if (bearer instanceof NextResponse) return bearer;
  const client = await uploadClient(request);
  if (client instanceof NextResponse) return client;

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
      headers: await upstreamHeaders(bearer, client),
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
      headers: await upstreamHeaders(
        bearer,
        (await cookies()).get(ACTIVE_CLIENT_COOKIE)?.value,
      ),
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
