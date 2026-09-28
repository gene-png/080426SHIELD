# 2026-09-27: a user of an archived client cannot sign in (#727, D-104)

Branch `track4/archived-client-sign-in`, stacked on
`track1/archive-ends-sessions` (#726) at `33eb0a2`, because #726 was still open
when this branch was cut. Retarget to `main` once #726 merges.

## What was wrong

#726 ended the sessions an archive found, but nothing on any session-issuing path
read `Client.archived_at`. The same user simply signed in again by password, by
finishing an MFA step, or by the OIDC exchange, and `current_client` served the
archived tenant. A new registrant on the archived client's domain joined it and
got a session too.

## What changed

- **Gene's decision (D-104):** a typed `client_archived` refusal at password
  login, MFA verify, the OIDC exchange, refresh, registration (409) and
  `current_client` (client-role users only).
- **One module,** `app/security/archived_client.py`.
- **Web:** the sign-in form shows the archived copy instead of "Invalid email or
  password.", and a refresh refused as `client_archived` ends the session through
  the same sign-out as `refresh_reused`.

## Residuals

- A Kentro admin keeps access to an archived client through `X-Client-Id`. This
  is on purpose (D-104).
- A proxy call refused by `current_client` with `client_archived` is a 403, and
  `SessionExpiryGuard` watches 401s only, so it does not sign the user out. The
  API refuses every call, and the next refresh ends the session. This case is
  only reachable for a client archived before #726, or for a token minted in
  the archive's own second.
