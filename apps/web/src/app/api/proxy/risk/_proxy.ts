/**
 * Shared proxy helpers for Risk Register routes. Same shape as
 * attack/_proxy.ts. Risk routes are admin-only and name the client in the
 * path (cid), so no X-Client-Id is required upstream.
 */

import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";
import { upstreamOutcomeUnknown } from "@/lib/upstream-outcome-unknown";

export async function proxyJson<T = unknown>(
  upstream: string,
  init: { method: "GET" | "POST" | "PATCH" | "DELETE"; body?: unknown } = {
    method: "GET",
  },
): Promise<NextResponse> {
  const session = await auth();
  const token = session?.accessToken;
  if (!token) {
    return NextResponse.json(
      { error: { code: 401, message: "Not signed in." } },
      { status: 401 },
    );
  }
  try {
    const result = await apiFetch<T>(upstream, {
      method: init.method,
      bearer: token,
      body: init.body as Record<string, unknown> | undefined,
    });
    // NOT `result ?? {}`. That turned an empty return into `{}` at HTTP 200:
    // the client parses it as its response type, every field is `undefined`,
    // and the renderer draws a successful response containing nothing. Filed
    // as #173.
    //
    // But the coalesce was also the ONLY thing handling 204, so removing it
    // without replacing it would trade a swallow for a broken path -- the
    // over-match rule in `CLAUDE.md`: before fixing one, check what it was
    // accidentally catching.
    //
    // `apiFetch` has exactly three exits: it throws `ApiError` when `!res.ok`,
    // returns `undefined` on 204, and otherwise returns parsed JSON. So
    // `undefined` HERE means 204, and 204 is what goes back.
    //
    // MEASURED, AND THE BOUND MATTERS: at 5fbd0ca none of the six proxied
    // routers emitted a 204 (`HTTP_204_NO_CONTENT` count was 0 in attack,
    // csf, zt, risk, tech_debt and ai), no route handler returned null, and an
    // unparseable 200 throws in `res.json()` before reaching here. That made
    // the swallow LATENT rather than live at that commit. It was a measurement
    // about what the ROUTERS emit, not about what `fetch` can receive -- a 204
    // from middleware, the dev server, or anything between was never covered
    // by it, which is why this branch exists rather than an assertion that it
    // is unreachable.
    //
    // NO LONGER LATENT as of #896: `POST /risk/clients/{cid}/services/{sid}/
    // archive` answers 204 on success, so this branch is that route's success
    // path (the duplicate banner's archive, through
    // `risk/clients/[cid]/services/[sid]/archive/route.ts`).
    if (result === undefined) {
      return new NextResponse(null, { status: 204 });
    }
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return upstreamOutcomeUnknown(err, "Upstream Risk Register call");
  }
}
