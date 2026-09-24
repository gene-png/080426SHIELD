# 2026-09-23: Two small honesty fixes (the ATT&CK catalog's counts; an idle timeout that was never read), and a 12-hour re-auth ceiling

Branch `fix/catalog-counts-idle-timeout`, base `f231b0e`.

## `attack/catalog.py` stated wrong counts (#183)

The module header said 196 parent techniques, 411 sub-techniques and 607 in
total, for an "ATT&CK Enterprise v15 baseline". Measured on 2026-09-23, the
tables hold 14 tactics and 633 techniques: 193 parents and 440
sub-techniques. The raw table has 636 rows, because three parents appear under
more than one tactic and are merged. The header no longer writes the counts.
It gives the snippet that measures them, and records that the old figures were
wrong. `attack/__init__.py` repeated two of them and now points at the header.

The "v15 baseline" label is gone too. Nothing in the repo records which ATT&CK
release the tables encode, so the label was a claim nothing could check.
Recording the catalog's version is separate held work.

The other "607"s in the tree are the record of a real run that wrote 607 `gap`
rows. That is history, and it is left alone.

## `shield_idle_timeout_seconds` was read by nothing

On a FedRAMP track, a setting called "idle timeout" reads to an assessor as an
implemented control. It was defined in `config.py`, compose and `.env.example`,
and no code read it. **Deleted rather than wired**, because the idle control
already exists: a refresh token rolls forward on each rotation and lapses
when the session is idle. A session idle for longer than
`jwt_refresh_ttl_seconds` since its last rotation cannot be renewed. A second
knob for the same control would be two values that can disagree.

`docs/security.md` now says so, including the parts a reader could miss.
The bound is counted from the last token rotation, not the last activity, so
under compose (access 900, refresh 1800) an idle session gets 15-30 minutes.
At the config defaults (access 3600, refresh 86400) a rotation always pushes
the refresh expiry past the ceiling (24 h when this section was written, 12 h
since D-085, below), so the ceiling fires first: **outside compose there is
no idle bound below the ceiling.** Round 2
of review corrected an earlier "23-24 hours" here, a bound that never takes
effect. And on `main`, a session whose refresh has lapsed is not
signed out: the page stays up and its calls fail. PR #499 adds that. Round 1
of review caught the first version of this calling the control "Implemented".
Whether SHIELD needs a real idle control outside compose is the owner's
decision, filed as #516. The decision to delete rather than wire, and what
it supersedes in D-020, is D-085. `routes/auth.py`'s docstring, which stated
the spec's figures as shipped, now says what ships.

The same subject was stated in `SECURITY.md`'s posture table (which round 3
of review found after the entry said the sweep was done), in the README's
risk-acceptance log ("a 30-minute
refresh-token TTL that functions as the idle timeout") and in
`docs/architecture.md`. All three are corrected, D-020's idle bullet points
at D-085, and so is the access-TTL row beside
the idle row, which said the config does not hold 900 when compose does. The README's settings table and the Keycloak README are
corrected to match. `Settings` ignores unknown variables, so an `.env` that
still sets `SHIELD_IDLE_TIMEOUT_SECONDS` boots unchanged. `SPRINT_3.md` still
names the setting; it is a closed sprint's plan and is not edited.

## The forced re-auth ceiling drops from 24 h to 12 h (the owner's call on #516)

Instead of any of the idle-control options, the owner lowered the session
setting that was already wired: `shield_forced_reauth_seconds`, from 86400 to
43200, in config, compose and `.env.example`. That is one value, with no new
code and no new UX. It covers a working day with overrun and halves the
overnight window. The refusal message no longer says "daily".

**It bounds session AGE, not idle time.** It is counted from the original
sign-in, and no activity extends it. A laptop left open for twenty minutes is
not locked by it, and D-085 says so rather than letting the number imply more.

The real idle control stays #516, with a trigger rather than a date: before
the first client engagement carrying an assessment requirement, or once the
session code (#499, #498, landed 2026-09-24) has been quiet for a month. The
reason for waiting is rework. That middleware still documents a live
residual around the 60-second grace window, and a second timing rule on top of
it would invite a rewrite.

Pinned by `test_auth_reauth.py`: the default is 12 h, taken from the decision
rather than the constant, and the refusal names no period.

**An existing dev `.env` keeps the old value.** Developers copy
`.env.example`, which said 86400 until this change, and both compose and
`Settings` prefer `.env`. So a machine set up earlier still runs a 24-hour
ceiling until its `.env` is edited. CI runs with no `.env`, so it gets 43200.
