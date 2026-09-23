# 2026-09-23 — #487: a user working on one page is no longer signed out when the access token expires

Branch `fix/487-refresh-persists`, base `f231b0e`. `tier-1`, `client-reaching`.

## What was wrong

`lib/auth/options.ts`'s `jwt` callback rotates the refresh token when the
access token is within 30 s of expiry. A zero-argument `await auth()` runs that
callback and then **discards the session response's `Set-Cookie`**
(next-auth 5.0.0-beta.32, `lib/index.js` `initAuth`). `apps/web` calls
`auth()` that way in its proxy route handlers and server components, and had no
`middleware.ts`. So the backend rotated while the browser kept the old refresh
token. The 60 s grace window hid it briefly, then every refresh was
`refresh_reused` and `SessionExpiryGuard` signed the user out.

With the compose default `JWT_ACCESS_TTL_SECONDS=900`, a user making only proxy
calls lost the session at 15.8 minutes (reproduced on the dev stack, #487).

## What changed

`apps/web/src/middleware.ts` runs next-auth's middleware wrapper
(`export default auth(() => undefined)`, Node runtime). That form keeps the
session response's cookies, so a rotation reaches the browser before the route
handler runs. The handler's own `auth()` still refreshes once from the
pre-rotation cookie, and the backend's grace window serves it the current
identity. No `authorized` callback exists, so the middleware never redirects.

## Proof

With a 60 s access TTL on the dev stack, the same proxy-only run:

| | with the middleware | without it |
| --- | --- | --- |
| proxy calls, 20 s apart | 12 of 12 → 200 over 4.2 min | 401 from 1.7 min |
| final session | no error | `reauth_required` |
| session cookie | changes as rotations persist | never changes |

`e2e/session/session-survives-refresh.spec.ts` pins it. CI's E2E job gains a
step that recreates api and web with `JWT_ACCESS_TTL_SECONDS=60` after the main
suite and runs that spec with `E2E_SESSION_TTL=1`. The spec **fails if the TTL
is not short** ("access TTL is 900 s…", observed), so it cannot pass vacuously.
It went red, with the same 200-then-401 pattern, when run against a web
container that had not picked up the middleware.
