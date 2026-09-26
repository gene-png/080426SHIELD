# 2026-09-26: archiving a client ends its users' sessions (#652, D-103)

Branch `track1/archive-ends-sessions`, stacked on `track1/access-token-cutoff`
(#670) at `b95a8a03`, because it needs that PR's `credentials_changed_at`
column. It lands after #670.

## What was wrong

Nothing on the request path read a client's `archived_at`, so a user of an
archived tenant kept a working access token until its TTL, and a refresh token
that went on minting new ones.

## What changed

- **Gene's decision (D-103):** archiving a client ends every session its users
  hold, access and refresh alike, the same way a password reset does.
- **One helper,** `app/security/sessions.py::end_user_sessions(user, at=...)`.
  It clears the three refresh-rotation fields and stamps
  `credentials_changed_at` to `at`'s whole second. The caller passes its own
  clock reading, so the reset's existing tests still pin its cutoff through
  `app.routes.auth.utcnow`.
- **Three callers:** the password reset, deactivation, and client archive (every
  user whose `client_id` is the archived client).
- **Deactivation now stamps the cutoff too.** A reactivated user's
  pre-deactivation access tokens no longer work again.

## Residuals

- Signing in again after the archive is not refused. The login path does not
  read `Client.archived_at` (a grep of `routes/auth.py`, `dependencies.py` and
  `security/` returns nothing). This is #652's other half, not decided here.
- A token minted in the archive's own second is accepted, the same residual as
  the reset (#658's whole-second rule).
