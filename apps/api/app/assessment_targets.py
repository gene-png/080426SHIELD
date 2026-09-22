"""The lowest level a client may TARGET, for each self-assessment ladder.

## One product rule, two ladders

Level 1 is where an organization starts, not something it sets out to reach,
so neither target picker offers it. That is a single product decision; it is
expressed twice only because ZT counts in CISA/DoD *stages* and CSF counts in
*tiers*. They are declared side by side, under one docstring, so that the next
person to change one is looking at the other.

## This is a COPY of `apps/web/src/lib/assessment-targets.ts`

Duplicated across the LANGUAGE boundary rather than derived, because there is
no build step shared by this app and the web bundle -- the same conclusion
`SCHEMA_REASON_PREFIX` reached one module over, for the same reason.

**What closes the window, stated exactly rather than implied.** Each side's own
suite spells the number and names the other file in its failure message:
`tests/unit/test_intake_target_floor.py` here, and
`lib/intake/target-options-are-derived.test.ts` there. So a unilateral change
goes RED on the side that made it, pointing at the side that did not.

That is all it does. It does **not** prove the two agree, and nothing available
can: the api container mounts `./apps/api` alone and the web container mounts
`apps/web`, `packages`, `package.json`, `pnpm-workspace.yaml` and the lockfile
-- neither can read the other's file, so a parity check would pass in CI and
fail on every developer's machine. An author who edits the number here, updates
the assertion here, and stops has not been stopped. A shared parity gate needs
a mount that does not exist today; tracked in **#422**.

## Why the ranges are NOT declared here

A floor is one end. The other end is the ladder's length, and the ladder is
framework-specific: `csf/maturity.py::TIER_DEFINITIONS` has four entries and
`zt/maturity.py::level_count` returns 4 for CISA and 3 for DoD. Restating
either here would be a third spelling of a number those modules already own.
`routes/intake.py::_validate_targets` is where the two ends meet, because it
is the only place that can see `service_type`.

## Why the floor is NOT a `Field(ge=2)` bound

It was, on four fields, and that is #406. A declarative bound is refused by
FastAPI's own handler as `"Request validation failed."` under a `schema_*`
reason with no client copy behind it -- `CLAUDE.md` records the shape, and
`describe-save-error.ts::serverReason` withholds every `schema_*` code by
design, so the client's intake wizard rendered a bare generic fallback naming
neither the field nor the range. Moving the check into `_validate_targets`
buys a typed `{reason, message}` refusal (the D-016 pattern) on the surface
where a client first chooses a target.
"""

from __future__ import annotations

#: ZT (CISA ZTMM 2.0 and DoD ZTRA). Stage 1 is a starting point, not a goal.
MIN_TARGET_STAGE = 2

#: NIST CSF 2.0. Tier 1 ("Partial") is a starting point, not a goal.
MIN_TARGET_TIER = 2
