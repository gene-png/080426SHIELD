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
 * `sessionExpiresAt` is the refresh token's expiry: the moment past which no
 * rotation can save the session. The access token's own expiry is deliberately
 * NOT used — it is renewed silently every hour and means nothing to a user.
 */

/** Warning thresholds, longest first. Rendered as "5 minutes" / "1 minute". */
const THRESHOLDS_MS = [5 * 60_000, 60_000] as const;

/** How often to re-check. One second keeps the countdown honest near zero. */
const TICK_MS = 1_000;

function minutesLabel(msRemaining: number): string {
  const minutes = Math.max(1, Math.ceil(msRemaining / 60_000));
  return `${minutes} minute${minutes === 1 ? "" : "s"}`;
}

export function SessionExpiryWarning(): React.JSX.Element | null {
  const { data: session } = useSession();
  const expiresAt = session?.sessionExpiresAt
    ? Date.parse(session.sessionExpiresAt)
    : null;

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

  if (expiresAt === null || Number.isNaN(expiresAt)) return null;

  const remaining = expiresAt - now;
  if (remaining <= 0) return null; // SessionExpiryGuard owns the actual sign-out.

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
