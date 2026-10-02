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

That is all it does. It does **not** prove the two agree. An author who edits
the number here, updates the assertion here, and stops has not been stopped.

**A REAL PARITY GATE IS BUILDABLE AND THIS PARAGRAPH USED TO SAY IT WAS NOT.**
The claim was that neither container can read the other's tree, so a parity
check "would pass in CI and fail on every developer's machine". False, and the
counter-example is one line further down the file it appealed to:
`docker-compose.yml` mounts `./packages/zt-data:/packages/zt-data:ro` on the
api service, commented "read-only, for the questionnaire contract test" -- a
read-only single-path mount added so a contract test can read a tree outside
the app, working identically in CI and locally. That is exactly the mechanism
the old sentence said did not exist.

So the deferral rests on SCOPE, not impossibility: the mount is a
`docker-compose.yml` edit, which merge-rule condition 5 sends to a human, and
it did not belong in the change that created the second constant. Tracked in
**#422**, whose body carries the mount as the cheapest of its options.

Recorded rather than quietly replaced, because the false version is the more
instructive one: it was a per-file check ("what does the api service mount for
the app?") published as a system-wide negative ("nothing can read across"),
which is the certificate-over-the-wrong-proposition shape one file over from
where this module's own docstring records the last instance of it.

## Why the ranges are NOT declared here

A floor is one end. The other end is the ladder's length, and the ladder is
framework-specific: `csf/maturity.py::TIER_DEFINITIONS` has four entries and
`zt/maturity.py::level_count` returns 4 for CISA and 3 for DoD. Restating
either here would be a third spelling of a number those modules already own.
`routes/intake.py::_validate_targets` is where the two ends meet ON THE INTAKE
ROUTES, because a pydantic field constraint cannot see `service_type`. It is
not the only comparison in the system -- see the next section.

## EVERY WRITER OF THE ENGAGEMENT TARGET ENFORCES THIS, SINCE #85

`ServiceRequest.csf_target_tier` and `.zt_target_stage` have three writers, and
all three refuse a target below the floor with a typed `{reason, message}`:

    routes/intake.py  `_validate_targets`
    routes/csf.py     `submit_self_assessment` (`_refuse_submitted_target_tier`)
    routes/zt.py      `submit_self_assessment`

Until #85 the two submit routes accepted 1: CSF had no range check at all
behind a schema `ge=1, le=4`, and ZT guarded `1 <= stage` as a written
decision. That decision is REVERSED by #85, a product call assumed by the
Phase 2 plan and flagged for the owner: a client may not choose a target of 1
after intake, the same as at intake. All three call `floor_refusal` below for
the sentence, so the client reads one rule in one wording at every door.

**A 1 ALREADY STORED is not a client's target either.** Both resolvers
(`csf/gap.py::resolve_target_tier`, `zt/scoring.py::resolve_target_stage`)
report it as `BELOW_FLOOR` and fall back to the engine default rather than
calling it the client's choice. That covers a deliverable target frozen as 1
too, because the freeze stores the raw choice and the dashboard re-resolves it
on read.

**NOT covered, deliberately (#85's Q4):** a consultant's per-capability
`zt_answers.target_stage`, which still accepts 1 on PATCH, on the AI apply
path and in `effective_target_stages`; and the gap-analysis what-if query
parameter, which is not persisted.

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

#: The resolver source for a stored target that is a real level but below the
#: floor (#85). Its own state: not "client" (it is not a target), and not
#: "client_out_of_range" (the ladder HAS a level 1, so "not a tier CSF has"
#: would be false). The web dashboards and workspaces render it as "a starting
#: point, not a target" (`apps/web/src/lib/assessment-targets.ts`).
BELOW_FLOOR = "client_below_floor"


def floor_refusal(rung: str, value: int, floor: int) -> str:
    """The sentence every target door refuses a below-floor value with.

    `rung` is "Tier" or "Stage". One builder, CALLED by intake and by both
    self-assessment submit routes, so the rule cannot be worded three ways.
    The control it names is real: every client target picker offers `floor`
    and up.
    """
    return (
        f"{rung} {value} is where an organization starts, not a target to "
        f"aim at. Choose {rung} {floor} or higher."
    )
