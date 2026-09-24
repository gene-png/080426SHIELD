# 2026-09-23: Two small honesty fixes (the ATT&CK catalog's counts; an idle timeout that was never read)

Branch `fix/catalog-counts-idle-timeout`, base `f231b0e`.

## `attack/catalog.py` stated wrong counts

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

`docs/security.md` now says so, including the part a reader could miss.
Compose sets that TTL to 1800 (30 minutes). The config default outside compose
is 86400 (24 hours). The README's settings table and the Keycloak README are
corrected to match. `Settings` ignores unknown variables, so an `.env` that
still sets `SHIELD_IDLE_TIMEOUT_SECONDS` boots unchanged. `SPRINT_3.md` still
names the setting; it is a closed sprint's plan and is not edited.
