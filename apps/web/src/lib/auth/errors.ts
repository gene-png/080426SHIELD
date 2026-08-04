/**
 * Client-safe auth error constants. Kept separate from `options.ts` (which
 * imports server-only `next/headers` via the api client) so client components
 * like SessionExpiryGuard can import the signal without dragging server code
 * into the browser bundle.
 */

/**
 * Stamped on the NextAuth session token when the daily forced-reauth ceiling
 * is hit or the refresh token was rotated out (backend reason
 * `reauth_required` / `refresh_reused`). The UI treats it as "sign in again"
 * with friendly copy, distinct from a generic refresh failure.
 */
export const REAUTH_REQUIRED_ERROR = "reauth_required";

/**
 * Stamped on the NextAuth session token when a Keycloak (OIDC) sign-in reached
 * the app but the backend `POST /auth/oidc/exchange` refused the identity
 * (no local account, unverified email, subject mismatch, JWKS outage, …).
 * The typed backend reason is logged server-side in the jwt callback; the
 * client only sees this opaque signal so SessionExpiryGuard can sign the user
 * out to `/sign-in?reason=oidc_exchange_failed` with a loud banner rather than
 * leaving a half-authenticated session that 401s on every proxy call.
 * (Sprint 9 T6, D-032.)
 */
export const OIDC_EXCHANGE_ERROR = "OIDC_EXCHANGE_ERROR";
