# 2026-09-23 — #487 and #498: a one-page user stays signed in, sign-out stays signed out, and the warning tells the truth

Branch `fix/487-refresh-persists`, base `f231b0e`. Both `client-reaching`:
#487 `tier-1`, #498 `tier-2`. Bundled, because the #487 fix alone makes the
#498 false warning reachable.

## What was wrong

`lib/auth/options.ts`'s `jwt` callback rotates the refresh token when the
access token is within 30 s of expiry. A zero-argument `await auth()` runs that
callback and then **discards the session response's `Set-Cookie`**
(next-auth 5.0.0-beta.32, `lib/index.js` `initAuth`). `apps/web` calls
`auth()` that way in its proxy route handlers and server components, and had no
`middleware.ts`. So the backend rotated while the browser kept the old refresh
token. After the 60 s grace window every refresh was `refresh_reused`, and the
user was signed out: at 15.8 minutes with the compose default 900 s TTL (#487).

## What changed

- **`apps/web/src/middleware.ts`** runs next-auth's middleware wrapper, the
  form that keeps the refreshed cookie, ahead of every page and proxy route
  (Node runtime; it never redirects).
- **Rotation-only.** next-auth re-issues the session cookie on every call, so
  the first version wrote it on every response. A response already in flight
  when the user signed out in another tab put a live session back, and
  `POST /auth/logout` revokes nothing (#392). The cookie is now written only
  when `sessionChanged`: a new access token, or a new error. That rule is in
  `lib/auth/session-cookie.ts`.
- **#498.** `SessionExpiryWarning` counted down to the `useSession` cache,
  which keeps the sign-in expiry while the cookie's rolls forward. It now reads
  the stored expiry from `/api/session-expiry`, which only decodes the cookie
  and is outside the middleware. Polling `/api/auth/session` instead would
  refresh the session, and an idle tab would never time out.

## Proof

| check | fix present | fix removed |
| --- | --- | --- |
| proxy-only session, 60 s TTL (`session/session-survives-refresh.spec.ts`) | passes, 4.3 min | 401 from 1.7 min, `reauth_required` |
| sign out while a response is held in flight (`session/signout-survives-an-inflight-response.spec.ts`) | passes | fails with **every-response writes**: "the in-flight response put a session cookie back after sign-out" |
| warning with a stale cached expiry (`SessionExpiryWarning.test.tsx`) | no warning | warns |

The TTL spec runs in a new E2E job step against api and web recreated with
`JWT_ACCESS_TTL_SECONDS=60`, and it fails if the TTL is not short. The race spec
runs in the main suite. `sessionChanged` and the cookie stripping have unit
tests; making `sessionChanged` always true fails two of them.

## Residual

The grace window is 60 s. If the rotating request runs longer than that (a live
Run-AI can), another request sent meanwhile still carries the old refresh
token and is rejected after 60 s. A rotation that coincides with a sign-out can
still race; that window is now one rotation per access-token lifetime, not
every request.
