import { NextResponse } from "next/server";

import {
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
 * callback ends the session on. The warning runs `update()` only when this
 * says ended, because `update()` on a session the server still considers
 * alive REFRESHES it: a browser clock a few seconds fast would otherwise roll
 * the idle deadline forward every time it arrived (round 5 on #499).
 */
export const dynamic = "force-dynamic";

export async function GET(req: Request): Promise<Response> {
  const token = await readSessionToken(req);
  console.info(`[auth.session-expiry] token ${token ? "present" : "absent"}`);
  return NextResponse.json(
    {
      // The EARLIER of the rolling refresh expiry and the fixed re-auth
      // ceiling -- the same rule the session callback uses. No `error` field:
      // nothing reads one, and a decode-only read would not see a fresh one.
      sessionExpiresAt:
        sessionEndsAt(token?.refreshExpiresAt, token?.reauthAt) ?? null,
      ended: sessionHasEnded(token?.refreshExpiresAt, token?.reauthAt),
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
