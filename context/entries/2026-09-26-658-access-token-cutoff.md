# 2026-09-26: an access token issued before a password reset is refused (#658)

Branch `track1/token-cutoff`, cut from `origin/main` at `d649566` (which
includes #633). Leaves #658 open for the owner.

## What was wrong

#633 ended every refresh family at a password reset (#636's refresh half). An
ACCESS token issued before the reset stayed valid until its own TTL: 900 s under
compose and `.env.example`, 3600 s as the code default.

## What changed

- **`users.credentials_changed_at`**, migration **0055**, nullable, no backfill
  (NULL means no cutoff; backfilling "now" would sign everyone out at deploy).
- **`reset_password` sets it to the reset's whole second.** That is the only
  credential change today. Swept by the symptom (`password_hash` writes, any
  spelling): sign-up creates a user rather than changing one, and login's
  rehash rewrites the hash of the SAME password, so neither sets it. A test pins
  the rehash case. Deactivation is out of scope: `current_user`'s `is_active`
  check already refuses on every request.
- **`current_user` refuses a token whose `iat` < cutoff**, with a typed 401
  `credentials_changed`, reading the row it already loads, so there is no extra
  query. `TokenPayload` now carries `iat`, which `verify_token` already required.
- **The owner's rule, 2026-09-25**: whole seconds, accept iff `iat >= cutoff`.
  A login in the reset's own second is accepted. So is a token minted EARLIER
  in that second, which is the rule's stated residual, pinned by a test rather
  than left to be found. With more than one API instance, clock skew between
  them can refuse a new session for up to the skew. Nothing here measures that.

## Migration order

0055, chaining from 0054 (#620), which is on `main`. It was first numbered
0056 behind #640's 0055; it now lands before #640, so under the owner's rule
(number order, renumbered at landing) it was renumbered 0055 on 2026-09-26 and
#640 takes 0056.
