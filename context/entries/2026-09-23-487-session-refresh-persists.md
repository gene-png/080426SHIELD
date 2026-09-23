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
runs only in the main suite, at the default TTL; the #487 step runs just the TTL spec. `sessionChanged` and the cookie stripping have unit
tests; making `sessionChanged` always true fails the three that expect `false`.

## Also from review

- **The daily re-auth ceiling.** A rotation rolls the refresh expiry forward,
  so counting down to it alone would miss the forced re-auth deadline, which
  does not move. The API now states `reauth_at` (login `auth_time` + ceiling)
  on every token pair, the session's end is the EARLIER of the two, and the
  `jwt` callback ends the session AT the ceiling (`REAUTH_REQUIRED_ERROR`,
  no backend call). Otherwise the API would notice only at the next refresh,
  up to one access-token lifetime later, after the warning had disappeared. Capping
  the refresh token's own `exp` at the ceiling was rejected: an expired token
  never reaches the refresh endpoint's `auth_time` check, so an API client
  would get a generic error instead of the typed `reauth_required` refusal
  (`test_refresh_past_forced_reauth_returns_typed_401`). The web client now
  ends a lapsed session itself before calling the backend, so for the web
  alone that cost no longer applies; for any other API client it still does.
- **The session ends at its end, whichever deadline that is.** The `jwt`
  callback's end check uses the same earlier-of rule as the warning, so a
  lapsed refresh expiry also ends the session without a backend call. Past
  its deadline the warning re-asks `/api/session-expiry` every 5 s. It calls
  `update()` only when that route says `ended`, and does so whatever the
  browser's clock says, re-asking every 5 s until the guard signs the user
  out. A cookie that is gone reads as `ended`. That answer comes from
  the web server's clock, which the `jwt` callback also uses. Calling
  `update()` on the browser's clock alone refreshed an idle session whenever
  the browser ran ahead of the server, so that tab never timed out.
- **The OIDC path** seeds `reauthAt` from the exchange too, and a refresh
  response that omits `reauth_at` keeps the ceiling the token already had.
  Each wiring point is pinned by a named test in `options.test.ts` or
  `route.test.ts` that goes red when it is removed.
- **Like with like.** The raw token keeps its access token after a refresh
  error, but the session hides it, so an errored session read as "changed" on
  every request. Both sides are now normalised the same way.
- **The cookie name** follows next-auth's `x-forwarded-proto` fallback when no
  auth URL is set. A decode miss with a live session logs an error.

## Residual

The grace window is 60 s. If the rotating request runs longer than that (a live
Run-AI can), another request sent meanwhile still carries the old refresh
token and is rejected after 60 s. What can still race a sign-out is the set of
requests in flight around a rotation, not every request.

Clock skew, filed as #501: the end is decided on the web server's clock. With
several web replicas whose clocks disagree, the route and `update()` can land
on different instances. And a web clock BEHIND the API's leaves a window, as
wide as the skew, where a refresh fails as a generic error the guard ignores.
