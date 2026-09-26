# 2026-09-25: a refresh rotation is a compare-and-swap (#505)

Branch `track1/refresh-rotation-cas`, cut from `34f0e33` and rebased onto
current `main` before opening.

## Why

`routes/auth.py::refresh()` loaded the user, checked that the presented
refresh jti was the active one, and then wrote the rotation. Nothing made the
check and the write atomic. Two refreshes presenting the same active jti at the
same moment could both pass the check and both rotate. Under Postgres READ
COMMITTED, the second write overwrote the first, and the winner's new jti was
then neither active nor previous. Its next refresh read as `refresh_reused`,
and the session ended as if a token had been stolen. Since #499 an open page
signs out within a minute of that.

It was not caught because the unit suite runs on SQLite, which serialises
writes, and the existing concurrency test sends its requests one after
another.

## What changed

The rotation is a single `UPDATE ... WHERE id = ? AND active_refresh_jti =
<presented>`, and the route requires `rowcount == 1`. Only one caller can match,
under Postgres READ COMMITTED (the configured default) and on SQLite. Under
REPEATABLE READ or SERIALIZABLE the loser would instead get a
`SerializationFailure`, an untyped 500 (#637). An earlier version of this entry
said "under any isolation level", which was too strong (review of `ef7762a`).
A row lock (`with_for_update`) was not used:
SQLite ignores `FOR UPDATE`, so the unit suite could not pin it. The swap it
can.

**What the losing request gets** was decided deliberately and is stated at the
site. The loser writes nothing, re-reads the winner's state, and goes through
the SAME decision as any non-active jti (`_grace_or_reuse`, factored out
unchanged):
- **With the grace window (the default):** the winner has just set `previous`
  to the loser's jti, so the loser is served the winner's identity with a 200.
  A benign two-tab race is not read as a stolen token.
- **With the grace at 0 (strict single-use):** the loser gets a typed 401
  `refresh_reused`. Under that setting a non-active jti is a replay, whoever
  wrote the active one.

Neither path is a 500. Today's non-active path revokes nothing, so neither
does this.

## Verified

- Two tests in `test_auth_reauth.py` force the race deterministically. The
  route's first `utcnow()` after loading the user is the ceiling check, which
  runs before rotation. A one-shot hook there commits a concurrent winner's
  rotation through a separate session, and records that it fired and what it
  saw, so the test cannot pass without the interleaving:
  - with the grace window, the loser gets 200 carrying the winner's jti, and
    the stored (active, previous) is still (winner, presented);
  - with the grace at 0, the loser gets a typed 401 `refresh_reused`, and the
    stored state is unchanged.
- Both were written first and were RED on the unfixed code. The loser
  overwrote the winner's jti; with grace 0 it got a 200.
- Red-on-revert, 3 of 3, both tests red each time, each revert checked to have
  landed:
  - `main`'s `refresh()`;
  - the swap's `active_refresh_jti == presented` condition dropped;
  - a lost swap ignored.

## Round 1 (review of `ef7762a`): a reset left the grace path open (#636)

The swap held. The review found a PRE-EXISTING hole in the same function,
filed as #636 (tier-1, the coordinator's call, owner-confirmed). A password
reset and an admin deactivation cleared only `active_refresh_jti`. The grace
path honours `previous_refresh_jti` inside the window, and with active None it
issued through `_issue_pair(keep_jti=None)`, which is a full rotation. So the
previous token minted a new session after the control meant to end them all.

This PR fixes the REFRESH half only, as scoped by the coordinator, with no
migration:
- **(a)** Every site that clears `active_refresh_jti` also clears
  `previous_refresh_jti` and `refresh_rotated_at`: the password reset
  (`routes/auth.py`) and deactivation (`routes/admin.py`). The sites were found
  by grepping the symptom, `active_refresh_jti = None`, which gave two.
- **(b)** `_grace_or_reuse` refuses with a typed 401 `refresh_reused` when no
  session is active, so the grace path never rotates.

The ACCESS-token half is not here. It needs a stored per-user cutoff checked
against `iat`, which is a migration, and it stays on #636.

(a) and (b) are redundant at the refresh endpoint. While active is None, (b)
refuses; active only becomes non-None again through a login, whose rotation
overwrites `previous`. So each is pinned on its own:
- (a) by driving the reset and deactivation endpoints and asserting the three
  stored fields are cleared;
- (b) at the refresh endpoint, on a stored state with active None and a live
  previous inside the window;
- plus an end-to-end test: reset, then present the previous token.

All four were RED on the unfixed code. The end-to-end case got a 200 and a
fresh token pair after the reset.

Red-on-revert, each case turning exactly its intended tests red:
- the reset site reverted turns only the reset field test red;
- the deactivation site reverted turns only the deactivation test red;
- (b) reverted turns only the grace refusal test red;
- (a) and (b) both reverted turns the end-to-end test red too.

Known twins, not fixed here: MFA recovery codes and the email and reset
tokens are read-check-write, #505's shape (#638, tier-2).

## Limits

- The race is forced on SQLite through a hook. No Postgres-backed concurrent
  test was added. The swap holds under READ COMMITTED, the configured
  default; the higher isolation levels are #637.
- The hook anchors on `utcnow()` being called between the user load and the
  rotation (the ceiling check). The tests assert the hook fired, so if that
  call moves they fail rather than pass vacuously.
