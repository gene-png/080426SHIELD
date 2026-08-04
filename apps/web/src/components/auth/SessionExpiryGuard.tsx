"use client";

import { signOut, useSession } from "next-auth/react";
import * as React from "react";

import { OIDC_EXCHANGE_ERROR, REAUTH_REQUIRED_ERROR } from "@/lib/auth/errors";

/**
 * Watches the session for two terminal signals and, when either fires, clears
 * the dead session and routes to sign-in with a friendly reason banner instead
 * of letting every proxy call 401 silently:
 *
 *  - `REAUTH_REQUIRED_ERROR` — the daily forced-reauth ceiling / rotated-token
 *    signal set in the NextAuth refresh callback → `?reason=session_expired`.
 *  - `OIDC_EXCHANGE_ERROR` — a Keycloak sign-in reached the app but the backend
 *    refused the exchange (no local account, unverified email, sub mismatch, …)
 *    set in the jwt callback → `?reason=oidc_exchange_failed`. Without this a
 *    rejected SSO user would sit on a token-less session that fails opaquely.
 *
 * A generic refresh failure keeps the existing per-proxy 401 behavior. Fresh
 * credential sign-ins never carry an error, so the e2e suite never trips this.
 */
export function SessionExpiryGuard(): null {
  const { data: session } = useSession();
  const firedRef = React.useRef(false);

  React.useEffect(() => {
    if (firedRef.current) {
      return;
    }
    if (session?.error === REAUTH_REQUIRED_ERROR) {
      firedRef.current = true;
      void signOut({ callbackUrl: "/sign-in?reason=session_expired" });
    } else if (session?.error === OIDC_EXCHANGE_ERROR) {
      firedRef.current = true;
      void signOut({ callbackUrl: "/sign-in?reason=oidc_exchange_failed" });
    }
  }, [session?.error]);

  return null;
}
