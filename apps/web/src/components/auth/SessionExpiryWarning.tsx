"use client";

import { signOut, useSession } from "next-auth/react";
import * as React from "react";

/**
 * Tells the user their session is about to end, before it does.
 *
 * Sessions used to end without warning: the access token expired, a rotation
 * race turned that into a hard sign-out, and whatever was on screen was gone.
 * The race is fixed, but a session still has a real ceiling
 * (`jwt_refresh_ttl_seconds` / the daily forced-reauth limit), and walking into
 * it mid-assessment with no notice is its own defect — the client-facing
 * self-assessment is 37 questions long.
 *
 * Two warnings, at five minutes and one minute. Both are dismissible: this is
 * information, not an interruption, and a consultant who knows they are about
 * to be signed out may simply want to finish a sentence. Dismissing the
 * five-minute notice does NOT suppress the one-minute one — that is the point
 * at which "I'll deal with it" stops being a safe answer.
 *
 * `sessionExpiresAt` is the EARLIER of the refresh token's expiry and the
 * forced re-auth ceiling (`reauth_at`): the moment past which no rotation can
 * save the session, and at which the `jwt` callback ends it. The access token's own expiry is deliberately
 * NOT used — it is renewed silently (every 15 minutes under the compose default)
 * and means nothing to a user.
 */

/** Warning thresholds, longest first. Rendered as "5 minutes" / "1 minute". */
const THRESHOLDS_MS = [5 * 60_000, 60_000] as const;

/** How often to re-check. One second keeps the countdown honest near zero. */
const TICK_MS = 1_000;

function minutesLabel(msRemaining: number): string {
  const minutes = Math.max(1, Math.ceil(msRemaining / 60_000));
  return `${minutes} minute${minutes === 1 ? "" : "s"}`;
}

/** How often to re-read the stored expiry from `/api/session-expiry`. */
const STORED_EXPIRY_POLL_MS = 60_000;

/** How often to re-ask the server once the browser thinks the end has come. */
const DEADLINE_RECHECK_MS = 5_000;

/** What `/api/session-expiry` answered. */
interface StoredExpiry {
  sessionExpiresAt: string | null;
  /** Decided on the SERVER's clock, the one the `jwt` callback ends it on. */
  ended: boolean;
}

/**
 * The expiry stored in the session cookie, read without running any auth
 * callback (#498). The `useSession` cache refetches only on focus, and since
 * #487 persists rotations into the cookie, the refresh expiry rolls forward
 * there while the cache keeps the value from sign-in. Reading
 * `/api/auth/session` instead would refresh and extend the session, so a
 * polling tab would never idle out; `/api/session-expiry` only decodes.
 *
 * `stored` is null until the first successful read, or while every read has
 * failed; the caller then falls back to the cached value, which is the
 * behaviour before this existed. After a success, a failed read keeps the last
 * stored value. `recheck` reads again now.
 */
function useStoredExpiry(enabled: boolean): {
  stored: StoredExpiry | null;
  recheck: () => void;
} {
  const [stored, setStored] = React.useState<StoredExpiry | null>(null);
  const live = React.useRef(true);
  React.useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);

  const recheck = React.useCallback(() => {
    void (async () => {
      try {
        const res = await fetch("/api/session-expiry", { cache: "no-store" });
        if (!res.ok) {
          // The status is logged as a separate value, never built into a
          // sentence (see client-surfaces-never-render-an-internal-string).
          console.warn(
            "[auth.session-expiry] read failed; status:",
            res.status,
          );
          return;
        }
        const body = (await res.json()) as {
          sessionExpiresAt?: string | null;
          ended?: boolean;
        };
        if (live.current) {
          setStored({
            sessionExpiresAt: body.sessionExpiresAt ?? null,
            ended: body.ended === true,
          });
        }
      } catch (err) {
        // Stated, not swallowed: the warning falls back to the cached expiry.
        console.warn(
          "[auth.session-expiry] could not read the stored expiry",
          err,
        );
      }
    })();
  }, []);

  React.useEffect(() => {
    if (!enabled) return;
    recheck();
    const id = setInterval(recheck, STORED_EXPIRY_POLL_MS);
    return () => clearInterval(id);
  }, [enabled, recheck]);

  return { stored, recheck };
}

export function SessionExpiryWarning(): React.JSX.Element | null {
  const { data: session } = useSession();
  const { stored, recheck } = useStoredExpiry(
    Boolean(session?.sessionExpiresAt),
  );
  const source = stored?.sessionExpiresAt ?? session?.sessionExpiresAt;
  const expiresAt = source ? Date.parse(source) : null;

  const [now, setNow] = React.useState(() => Date.now());
  // The largest threshold the user has already dismissed. Starts at Infinity so
  // nothing is suppressed; dismissing the 5-minute notice sets it to 5 minutes,
  // which still leaves the 1-minute notice free to fire.
  const [dismissedAboveMs, setDismissedAboveMs] = React.useState(
    Number.POSITIVE_INFINITY,
  );

  React.useEffect(() => {
    if (expiresAt === null || Number.isNaN(expiresAt)) return;
    const id = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(id);
  }, [expiresAt]);

  // When the session ends, the page has to learn it. `useSession` refetches
  // only on focus, so without this a user who never leaves the page watched
  // the countdown vanish and then typed into 401s with no sign-out and no
  // reason.
  //
  // Only the SERVER's `ended` (from `/api/session-expiry`, decided on the
  // clock the `jwt` callback uses) triggers the sign-out, whatever the
  // browser's clock says: acting on the browser's clock either refreshed a
  // live session (round 5 on #499) or left a dead one under a countdown
  // (round 6). The browser's clock only decides when to re-ask sooner than
  // the minute poll.
  //
  // It signs out DIRECTLY, with the reason the guard would give, rather than
  // asking `update()` to have the guard do it (rounds 4-6): `update()`
  // resolves `undefined` while a fetch is in flight and `null` both for "no
  // session" and for a failed fetch, and next-auth drops a null -- so a tab
  // whose cookie was gone looped on it for good (round 7).
  const reachedDeadline =
    expiresAt !== null && !Number.isNaN(expiresAt) && now >= expiresAt;
  const serverSaysEnded = stored?.ended === true;

  React.useEffect(() => {
    if (!reachedDeadline || serverSaysEnded) return;
    recheck();
    const id = setInterval(recheck, DEADLINE_RECHECK_MS);
    return () => clearInterval(id);
  }, [reachedDeadline, serverSaysEnded, recheck]);

  // Once per page: `signOut` navigates away. A REJECTED one is retried after
  // DEADLINE_RECHECK_MS -- `attempt` re-runs this effect -- so a network blip
  // cannot leave the tab on a dead session for good. `signingOut` is cleared
  // the moment it fails, not when the retry fires, so a retry cancelled by
  // `ended` flipping back cannot leave the page believing it is still signing
  // out. NOT every failure rejects: a failed CSRF fetch inside `signOut`
  // resolves and navigates to next-auth's error page instead (#502).
  const signingOut = React.useRef(false);
  const [attempt, setAttempt] = React.useState(0);
  React.useEffect(() => {
    if (!serverSaysEnded || signingOut.current) return;
    signingOut.current = true;
    console.info("[auth.session-expiry] the server says ended; signing out");
    let retry: ReturnType<typeof setTimeout> | undefined;
    signOut({ callbackUrl: "/sign-in?reason=session_expired" }).catch(
      (err: unknown) => {
        // Stated, not swallowed: tried again shortly.
        console.warn("[auth.session-expiry] sign-out failed; retrying", err);
        signingOut.current = false;
        retry = setTimeout(() => setAttempt((n) => n + 1), DEADLINE_RECHECK_MS);
      },
    );
    return () => {
      if (retry !== undefined) clearTimeout(retry);
    };
  }, [serverSaysEnded, attempt]);

  if (expiresAt === null || Number.isNaN(expiresAt)) return null;
  // The session is over; a countdown would claim time the user does not have.
  if (serverSaysEnded) return null;

  const remaining = expiresAt - now;
  // Past the browser's own deadline but not yet `ended` by the server: say
  // nothing. The sign-out effect above acts when the server says so.
  if (remaining <= 0) return null;

  // The TIGHTEST threshold we are inside and have not dismissed. Searched
  // shortest-first: a plain `.find` over a longest-first list always returns the
  // 5-minute entry, so the notice would never escalate to the 1-minute wording
  // no matter how little time was left.
  const active = [...THRESHOLDS_MS]
    .sort((a, b) => a - b)
    .find((t) => remaining <= t && t < dismissedAboveMs);
  if (active === undefined) return null;

  const urgent = active <= 60_000;

  return (
    <div
      // `alert` rather than `status`: this is time-critical and a screen-reader
      // user must not have to go looking for it.
      role="alert"
      aria-live="assertive"
      data-testid="session-expiry-warning"
      className="fixed inset-x-0 bottom-0 z-50 flex justify-center p-4"
    >
      <div
        className={`flex w-full max-w-xl flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 shadow-lg ${
          urgent
            ? "border-status-danger-fg bg-surface-card"
            : "border-border bg-surface-card"
        }`}
      >
        <div className="min-w-0">
          <p className="text-sm font-semibold text-ink-primary">
            {urgent
              ? "You will be signed out in less than a minute"
              : `You will be signed out in about ${minutesLabel(remaining)}`}
          </p>
          <p className="text-xs text-ink-secondary">
            Save anything you are part-way through. Signing in again returns you
            to this page.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() =>
              void signOut({ callbackUrl: "/sign-in?reason=session_expired" })
            }
            className="rounded-md bg-brand-500 px-3 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
          >
            Sign in again
          </button>
          <button
            type="button"
            onClick={() => setDismissedAboveMs(active)}
            className="rounded-md border border-border px-3 py-2 text-sm font-medium text-ink-secondary hover:text-ink-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
