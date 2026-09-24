import { NextResponse } from "next/server";

import { REAUTH_REQUIRED_ERROR } from "@/lib/auth/errors";
import {
  hasSessionCookie,
  readSessionToken,
  sessionEndsAt,
  sessionHasEnded,
} from "@/lib/auth/session-cookie";

/**
 * The stored session expiry, read WITHOUT running any auth callback (#498).
 *
 * `SessionExpiryWarning` counted down to `sessionExpiresAt` from the client
 * `useSession` cache, which refetches only on focus. Once #487 persisted token
 * rotations into the cookie, the refresh expiry rolls forward there while the
 * cache kept the value from sign-in -- so a user working on one page was warned
 * of a sign-out that would not happen, beside a button that would cause one.
 *
 * Refetching `/api/auth/session` instead would run the `jwt` callback, which
 * refreshes near expiry and rolls the refresh expiry forward: a polling tab
 * would never time out, and the refresh TTL (30 minutes under the compose
 * default, `JWT_REFRESH_TTL_SECONDS`) is what idles a session out. So
 * this route only DECODES the cookie, and it is excluded from the middleware
 * matcher for the same reason. Polling it is not activity.
 *
 * `ended` is decided HERE, on the web server's clock -- the clock the `jwt`
 * callback ends the session on -- and the warning signs out only when this
 * says ended. The browser's clock is never the judge: acting on it either
 * refreshed a live session (round 5 on #499) or left a dead one under a
 * countdown (round 6).
 */
export const dynamic = "force-dynamic";

export async function GET(req: Request): Promise<Response> {
  const token = await readSessionToken(req);
  if (token === null && hasSessionCookie(req)) {
    // A cookie that will not decode is a secret or cookie-name mismatch, not
    // an ended session -- answering `ended` would sign out a session that may
    // be live. Refused loudly instead; the warning treats a failed read as no
    // answer and does nothing (round 7 on #499).
    console.error(
      "[auth.session-expiry] a session cookie is present but did not decode -- cookie name or secret mismatch",
    );
    return NextResponse.json(
      {
        reason: "session_cookie_unreadable",
        message: "The session cookie could not be read.",
      },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
  console.info(`[auth.session-expiry] token ${token ? "present" : "absent"}`);
  return NextResponse.json(
    {
      // The EARLIER of the rolling refresh expiry and the fixed re-auth
      // ceiling -- the same rule the session callback uses.
      sessionExpiresAt:
        sessionEndsAt(token?.refreshExpiresAt, token?.reauthAt) ?? null,
      // Ended when: there is no cookie at all (an undecodable one was refused
      // above) -- a cookie that expired or was cleared without a sign-out
      // broadcast; a sign-out in another tab broadcasts, and this tab's
      // session then drops before it ever asks (#503). When its end has passed. Or
      // when the backend REFUSED a refresh: the middleware writes that
      // terminal error into the cookie, every proxy call is a 401 from then
      // on, and the refresh expiry it carries is still in the future (round 9
      // on #499). Not the generic RefreshAccessTokenError, which the next
      // callback retries.
      ended:
        token === null ||
        token.error === REAUTH_REQUIRED_ERROR ||
        sessionHasEnded(token.refreshExpiresAt, token.reauthAt),
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
