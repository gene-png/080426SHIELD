# 2026-09-22 — #209: the engagement target a deliverable was rendered against is frozen

The last open `tier-1`. Branch `fix/209-frozen-target`, base `43bfa99`.
Decision record: **D-083** (D-082 is reserved by open PR #461).

## What was wrong

Four client-facing surfaces resolved the engagement target LIVE on every
request, while the released document held the number it was rendered with.
Change the intake target after release and the two disagree: the PDF says
"37 gaps at target S4" and the dashboard beside it says something else, computed
from the same approved answers. Both internally consistent, and one is a number
the client never contracted for.

## Shape of the fix

`Deliverable.frozen_target` + `frozen_target_source` (migration 0051), stamped
at FINALIZE by the CSF and ZT finalize routes. The column holds the client's
CHOSEN value, so each read path runs the same resolver it ran before — the
number and its caption stay one derivation rather than two stored values kept in
agreement by hand.

`frozen_target_source` is a freeze-provenance discriminator, not a copy of the
resolver's source vocabulary. Every read path branches on it being NULL, never on
the value being NULL, because a client who chose nothing freezes as
`(None, "finalize")` and a pre-0051 row has no freeze at all — same bytes,
opposite meanings.

Four read sites, one function (`_frozen_or_live_target`). Three further sites
read live on purpose and are named in that function's docstring, because a site
that SHOULD read live is indistinguishable from one that was missed.

## Routed to Gene rather than self-merged

Trips merge-rule condition 4 (migration) and condition 6 (changes what a client
dashboard shows). Also trips condition 5 on `app/models/**`,
`app/routes/clients.py`, `apps/api/tests/**`, `apps/api/scripts/check_*.py` and
the web test globs.

## What was measured, and the three things running found that reading did not

| check | result |
| --- | --- |
| six mutants, each asserted to land, each needing a NAMED test red | 6 of 6 killed |
| four REPAIRED existing tests, mutated against their own claims | see below |
| `pytest test_frozen_engagement_target.py` | 13 passed |
| `pytest test_migration_0051_backfill.py` | 8 passed |
| `pytest test_zt_dashboard.py test_csf_dashboard.py test_disclosure_consumers.py` | 51 passed |
| `ruff check --no-cache app/ alembic/` | exit 0 |
| `black --check app/ alembic/` | exit 0 |
| `verify-in-worktree.sh tsc` | 0 errors |
| `verify-in-worktree.sh vitest` | 762 passed, 63/63 files, 0 never collected |
| `eslint .` (real invocation, not the harness) | exit 0, 3 pre-existing warnings |

**1. The migration's own docstring was wrong, and a test found it.** It said
`client_out_of_range` ends unfrozen. The audit arm declines it, but the
`updated_at` arm reads the raw column and recovers the value verbatim — which is
correct and strictly better, because the resolver is deterministic. Corrected in
place.

**2. Four existing tests were asserting the defect.** They attached the intake
target AFTER finalize and asserted the dashboard reported it; the CSF one
asserted that doing so moves the gap count from 0 to 106. Setup moved to the
product's real ordering (intake before finalize), claims unchanged, then each
mutated against its own claim and required to go red.

**3. `check_disclosure_consumers.py` could not see any of the three new
disclosure fields.** It reported 25 of 25 exit 0 — the same count as before the
change, which is what gave it away. Its predicate is prefix-anchored (#373) and
`target_frozen_at` / `<kind>_targets_computed_live` match none of the eight
prefixes. Adding `"frozen"` and `"computed_live"` to `DISCLOSURE_SUBSTRINGS`
gives 29 of 29, still exit 0; deleting `renderedAgainstNote`'s call site gives
exit 1 naming `ZtDashboardResponse.target_frozen_at`.

## Two things found on the way, neither part of this branch

**#469 and #470 conflict with each other.** Both `MERGEABLE`, both `CLEAN`, both
fully green. `git merge` exits 1 on `apps/api/tests/unit/test_gate_crash_exit_code.py`
— both append their new gate to the same registry list. `audit-gate.yml` itself
merges cleanly. Resolution is "keep both tuples"; they must be sequenced.

**`scripts/verify-in-worktree.sh eslint` cannot pass on any tree.** `HARNESS_EXIT=2`
with `The unix formatter is no longer part of core ESLint`, under a printed
sentence claiming it ran the CI command. Already filed twice, as #450 and #383,
which are duplicates of each other; today's measurement is commented on #450.
