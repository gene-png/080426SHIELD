import { auth } from "@/lib/auth/options";

/**
 * Persist a token refresh before any page or proxy route reads the session.
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
 * The middleware-wrapper form of `auth` is the one that KEEPS those headers
 * (`handleAuth` appends the session response's cookies to the response it
 * returns). Running it here means the rotation reaches the browser before the
 * route handler runs. The handler's own `auth()` then reads the request's
 * pre-rotation cookie and refreshes again with the just-rotated token, which
 * the backend's grace window serves with the current identity (`keep_jti`), so
 * the handler still gets a working access token and the browser keeps the
 * persisted one.
 *
 * No `authorized` callback is configured, so this never redirects; access
 * control stays where it was, in the pages and proxies.
 */
export default auth(() => undefined);

export const config = {
  // `lib/auth/options.ts` is Node code (the OIDC exchange, `apiFetch`); the
  // Node middleware runtime is stable in Next 15.5.
  runtime: "nodejs",
  // Everything except next-auth's own routes, which already persist cookies,
  // and static assets, which carry no session.
  matcher: ["/((?!api/auth|_next/static|_next/image|favicon.ico).*)"],
};
