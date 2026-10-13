import { NextResponse } from "next/server";

import { auth } from "@/lib/auth/options";

import { proxyJson } from "../../../../_proxy";

/**
 * RR-1 (for #1122), design note §3.1: the admin's selection travels in the
 * body, `{"include": {"csf": bool, "zero_trust": ...}}`, and is forwarded as
 * parsed. It used to forward `{method: "POST"}` alone, dropping any body.
 *
 * Not `proxyJsonFromRequest`: that turns an unparseable body into "no body",
 * which here is the absent-body default, so one selection would be silently
 * replaced by another. An unparseable body is refused, typed, before any
 * upstream call. An EMPTY body is a request that sent none (an API caller,
 * never the page, which always sends its selection): forwarded as none.
 */
const SELECTION_UNREADABLE_MESSAGE =
  "The services to include could not be read. Reload the page and choose them again.";

export async function POST(
  request: Request,
  props: { params: Promise<{ cid: string }> },
) {
  const params = await props.params;
  // #1148 review, finding 7: who is asking comes before what they sent, so a
  // signed-out caller is told so, never that its body was unreadable.
  // `proxyJson` checks again; this one runs before the body is read.
  const session = await auth();
  if (!session?.accessToken) {
    return NextResponse.json(
      { error: { code: 401, message: "Not signed in." } },
      { status: 401 },
    );
  }
  const raw = await request.text();
  let body: unknown = undefined;
  if (raw.trim() !== "") {
    try {
      body = JSON.parse(raw) as unknown;
    } catch {
      console.error(
        `proxy.risk_selection_unreadable cid=${params.cid} length=${raw.length}`,
      );
      return NextResponse.json(
        {
          error: {
            code: 400,
            reason: "risk_selection_unreadable",
            message: SELECTION_UNREADABLE_MESSAGE,
          },
        },
        { status: 400 },
      );
    }
  }
  return proxyJson(`/risk/clients/${params.cid}/register/generate`, {
    method: "POST",
    body,
  });
}
