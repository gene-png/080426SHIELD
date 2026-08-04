"use client";
import { signIn } from "next-auth/react";
import * as React from "react";

import type { JSX } from "react";

/**
 * Starts the Keycloak (OIDC) sign-in flow (Sprint 9 T6). Rendered by the sign-in
 * page ONLY when `SHIELD_AUTH_OIDC_ENABLED` is on; with the flag off the page
 * never mounts this and the "keycloak" provider does not exist, so the click
 * would have no provider to reach anyway.
 *
 * `signIn("keycloak", ...)` kicks off the standard Auth.js redirect to the
 * Keycloak login page (browser-facing localhost issuer); on return the jwt
 * callback exchanges the Keycloak token for a SHIELD pair. `callbackUrl` lands
 * the user on the app home after a successful round trip.
 */
export function KeycloakSignInButton(): JSX.Element {
  const [pending, setPending] = React.useState(false);
  return (
    <button
      type="button"
      disabled={pending}
      onClick={() => {
        setPending(true);
        void signIn("keycloak", { callbackUrl: "/" });
      }}
      className="rounded-md border border-border bg-surface-card px-4 py-2.5 text-sm font-semibold text-ink-primary hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-60"
    >
      {pending ? "Redirecting…" : "Sign in with Keycloak"}
    </button>
  );
}
