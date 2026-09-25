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
under any isolation level. A row lock (`with_for_update`) was not used:
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

## Limits

- The race is forced on SQLite through a hook. No Postgres-backed concurrent
  test was added. The swap's correctness does not depend on the isolation
  level, which is why it was chosen over a lock.
- The hook anchors on `utcnow()` being called between the user load and the
  rotation (the ceiling check). The tests assert the hook fired, so if that
  call moves they fail rather than pass vacuously.
