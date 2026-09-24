import type { NextFetchEvent, NextRequest } from "next/server";

import { auth } from "@/lib/auth/options";
import {
  readSessionToken,
  sessionChanged,
  sessionCookieName,
  stripSessionCookies,
  type SessionAfter,
} from "@/lib/auth/session-cookie";

/**
 * Persist a token refresh -- and ONLY a token refresh -- before any page or
 * proxy route reads the session.
 *
 * #487. The `jwt` callback in `lib/auth/options.ts` rotates the refresh token
 * whenever the access token is within `REFRESH_SKEW_MS` of expiry. A
 * zero-argument `await auth()` -- every proxy route handler and every server
 * component -- runs that callback and then DISCARDS the session response's
 * `Set-Cookie` headers (next-auth 5.0.0-beta.32, `lib/index.js` `initAuth`).
 * So the backend rotated while the browser kept the old refresh token; the
 * 60-second grace window hid it briefly, and then every refresh was rejected as
 * `refresh_reused` and the user was signed out. Reproduced 2026-09-23: a user
 * making only proxy calls on one page lost the session at 15.8 minutes, with
 * the compose default `JWT_ACCESS_TTL_SECONDS=900`.
 *
 * The middleware-wrapper form of `auth` KEEPS those headers (`handleAuth`
 * appends the session response's cookies to the response it returns), so a
 * rotation is persisted on THIS request's response. It reaches the browser when
 * that response does, not before the handler runs. The handler's own `auth()`
 * reads the request's pre-rotation cookie and refreshes again with the
 * just-rotated token, which the backend's grace window serves with the current
 * identity (`keep_jti`).
 *
 * ROTATION-ONLY. next-auth re-issues the session cookie on every call, so the
 * first version of this file wrote it on EVERY matched response -- and a
 * response already in flight when the user signed out in another tab put a live
 * session back. `POST /auth/logout` revokes nothing (#392), so that was a
 * sign-out that did not sign you out. The cookie is now written only when
 * `sessionChanged`: a new access token, or a new error the browser must learn.
 * What can still race a sign-out is the set of requests in flight around a
 * rotation -- the rotating one, and any sent meanwhile with the pre-rotation
 * cookie, which refresh through the grace window and also write -- rather than
 * every request.
 *
 * RESIDUAL: the grace window is 60 s (`jwt_refresh_grace_seconds`). If the
 * rotating request runs longer than that -- a live Run-AI can -- another
 * request sent meanwhile still carries the old refresh token, and after 60 s it
 * is rejected as reused.
 *
 * No `authorized` callback is configured, so this never redirects; access
 * control stays where it was, in the pages and proxies.
 */
export default async function middleware(
  req: NextRequest,
  event: NextFetchEvent,
) {
  const before = await readSessionToken(req);
  let after: SessionAfter | null = null;
  const run = auth((authed) => {
    after = authed.auth
      ? { accessToken: authed.auth.accessToken, error: authed.auth.error }
      : null;
    return undefined;
  });
  const response = (await run(req, event as never)) as Response;
  if (before === null && after !== null) {
    // A session after the callback means a session cookie came in, so a null
    // decode means this file is reading the wrong cookie name or secret. Every
    // response would then count as "changed" and the rotation-only rule would
    // silently revert to writing on every request. Said out loud.
    console.error(
      "[auth.middleware] session present but the incoming cookie did not decode -- cookie name or secret mismatch; writing the cookie on every response",
    );
  }
  if (!sessionChanged(before, after)) {
    stripSessionCookies(response.headers, sessionCookieName(req));
  }
  return response;
}

export const config = {
  // `lib/auth/options.ts` is Node code (the OIDC exchange, `apiFetch`); the
  // Node middleware runtime is stable in Next 15.5.
  runtime: "nodejs",
  // Everything except next-auth's own routes, which already persist cookies;
  // `/api/session-expiry`, whose polling must never count as activity (it
  // would refresh, and an idle tab would never time out); and static assets.
  matcher: [
    "/((?!api/auth|api/session-expiry|_next/static|_next/image|favicon.ico).*)",
  ],
};
