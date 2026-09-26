"use client";

import { signOut, useSession } from "next-auth/react";
import * as React from "react";

import { OIDC_EXCHANGE_ERROR, REAUTH_REQUIRED_ERROR } from "@/lib/auth/errors";

const SESSION_EXPIRED_URL = "/sign-in?reason=session_expired";

/** The API's typed 401 for an access token issued before a password reset (#658). */
const CREDENTIALS_CHANGED = "credentials_changed";

/** Marks the fetch this guard installed, so a second mount does not wrap it again. */
const WATCHED = Symbol.for("shield.sessionExpiryGuard.fetchWatch");

type WatchedFetch = typeof window.fetch & { [WATCHED]?: true };

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function isSameOriginProxy(input: RequestInfo | URL): boolean {
  try {
    const url = new URL(requestUrl(input), window.location.origin);
    return (
      url.origin === window.location.origin &&
      url.pathname.startsWith("/api/proxy/")
    );
  } catch {
    return false;
  }
}

/** The envelope's `error.reason`, or undefined for any body that does not carry one. */
async function reasonOf(response: Response): Promise<string | undefined> {
  try {
    const body: unknown = await response.json();
    const reason = (body as { error?: { reason?: unknown } } | null)?.error
      ?.reason;
    return typeof reason === "string" ? reason : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Watches the session for two terminal signals and, when either fires, clears
 * the dead session and routes to sign-in with a friendly reason banner instead
 * of letting every proxy call 401 silently:
 *
 *  - `REAUTH_REQUIRED_ERROR` — the session is over: the backend refused a
 *    refresh (forced-reauth ceiling, rotated-out token), or the jwt callback
 *    found the session's end already passed (ceiling or idle-lapsed refresh
 *    expiry) → `?reason=session_expired`. See `lib/auth/errors.ts`.
 *  - `OIDC_EXCHANGE_ERROR` — a Keycloak sign-in reached the app but the backend
 *    refused the exchange (no local account, unverified email, sub mismatch, …)
 *    set in the jwt callback → `?reason=oidc_exchange_failed`. Without this a
 *    rejected SSO user would sit on a token-less session that fails opaquely.
 *
 * And one per-REQUEST signal (#658/#670): after a password reset the API
 * refuses the old access token on every call with a typed 401, reason
 * `credentials_changed`, while the session itself still looks alive until the
 * token's TTL. That 401 reaches the browser through the proxies unchanged, and
 * about twenty files call `fetch("/api/proxy/...")` directly besides the six
 * service clients, so there is no shared client wrapper to catch it in. The
 * guard therefore watches `fetch` ONCE, globally: it reads a CLONE of a
 * same-origin `/api/proxy/` 401, returns the original untouched, and on that
 * reason signs out through the same session_expired path, once however many
 * panels 401 together. Anything else passes through; a body that does not
 * parse is ignored.
 *
 * One guard is mounted, in `AuthSessionProvider`. A second mount does not wrap
 * `fetch` again; if the FIRST then unmounted while a second stayed, nothing
 * would be watching -- not a state this app reaches.
 *
 * A generic refresh failure keeps the existing per-proxy 401 behavior. Fresh
 * credential sign-ins never carry an error, so the e2e suite never trips this.
 */
export function SessionExpiryGuard(): null {
  const { data: session } = useSession();
  const firedRef = React.useRef(false);

  const signOutOnce = React.useCallback((callbackUrl: string) => {
    if (firedRef.current) {
      return;
    }
    firedRef.current = true;
    void signOut({ callbackUrl });
  }, []);

  React.useEffect(() => {
    if (session?.error === REAUTH_REQUIRED_ERROR) {
      signOutOnce(SESSION_EXPIRED_URL);
    } else if (session?.error === OIDC_EXCHANGE_ERROR) {
      signOutOnce("/sign-in?reason=oidc_exchange_failed");
    }
  }, [session?.error, signOutOnce]);

  React.useEffect(() => {
    const original = window.fetch as WatchedFetch;
    if (original[WATCHED]) {
      return;
    }
    const watched: WatchedFetch = async (input, init) => {
      const response = await original(input, init);
      if (response.status === 401 && isSameOriginProxy(input)) {
        void reasonOf(response.clone()).then((reason) => {
          if (reason === CREDENTIALS_CHANGED) {
            signOutOnce(SESSION_EXPIRED_URL);
          }
        });
      }
      return response;
    };
    watched[WATCHED] = true;
    window.fetch = watched;
    return () => {
      if (window.fetch === watched) {
        window.fetch = original;
      }
    };
  }, [signOutOnce]);

  return null;
}
