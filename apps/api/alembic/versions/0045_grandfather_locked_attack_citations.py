"""Grandfather LOCKED ATT&CK assessments' citations to `[]` (D-056)

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-21 00:00:00

Closes a hole in migration 0044's affordability argument, found by measuring the
dev database rather than by reading the code.

0044 made `unconfirmed_citations IS NULL` score as PENDING -- deliberately
fail-closed, on the reasoning that "what it costs is one Run-AI on each of the
existing drafts, which is exactly the work that was never done for them."

**APPROVED assessments are not drafts, and nothing can reach them.** All three
write paths refuse a locked parent: `run_ai` re-reads the assessment status
before committing and raises `assessment_not_editable`, `patch_coverage` raises
"This assessment is locked", and `confirm_coverage_citations` does the same. So
an approved assessment written before the resolver existed was pinned at 0%
coverage, permanently, with no action available anywhere in the product.

0044's affordability check verified that **zero RELEASED** assessments existed.
It never asked about APPROVED. On the dev database at the time of writing there
were 14, holding **8,862** NULL-citation coverage rows -- 29 of 48 assessments
dropped from ~62% to 0%.

## The decision (D-056), taken narrowly

Grandfather the rows under assessments that are LOCKED against every write path
-- `approved` and `released` -- and only where the column is still NULL.

* **Only `IS NULL`.** A locked row that already carries an outstanding flag KEEPS
  it. Blanket `SET unconfirmed_citations = '[]'` would erase exactly the review
  queue #101 exists to persist, which is a bigger defect than the one being
  fixed.
* **Not `draft`.** A draft is reachable by Run-AI, and re-resolving it is the
  work 0044 said was owed. Grandfathering drafts would spend the fail-closed
  guarantee to save a click.
* **Not `discarded`.** Equally unreachable, and the least obvious of the four:
  it is a soft-deleted assessment nobody will read, so writing "these citations
  are confirmed" onto it asserts something no human checked, for no benefit. If
  one is ever restored it should be re-run, not trusted.
* **`released` is included although the count is zero.** The criterion is "the
  parent is locked against every write path", not "the parent happens to be
  approved". Keying on the property rather than on today's row count means the
  migration is right by construction instead of right by coincidence.

## The casing trap this migration shipped once and had to fix

The first version matched `status IN ('approved', 'released')` and grandfathered
**zero** rows against 8,862 that needed it, while reporting success.
`AttackAssessment.status` is a `SAEnum(..., native_enum=False)`, and SQLAlchemy's
`Enum` persists the member's **NAME** -- the column holds `'APPROVED'`, not the
`'approved'` that `AttackAssessmentStatus.APPROVED.value` returns.

Two things caught it and both were deliberate: the row count in the log line
(the alternative is that "touched nothing" and "had nothing to do" look
identical), and applying it to the dev database rather than trusting a green
test. The test itself could NOT have caught it -- its fixture inserted
`'approved'` by hand, so it agreed with the migration by construction, which is
CLAUDE.md's standing rule about a test that supplies its own precondition from
the thing under test. The fixture now seeds through the ORM, so the stored
representation comes from the same code production uses.

## What this is NOT

It is **not** a decision that approval counts as citation confirmation in
general. That is a real and separate design question -- should
`approve_assessment` stamp its rows' citations from now on? -- and it gets its
own D-number if the answer turns out to be yes. This migration is a one-time
backfill of rows that predate the rule, nothing more. Deliberately kept apart so
that "we grandfathered old data" never quietly becomes "sign-off is evidence".

## Downgrade

A no-op, and loudly so. Nothing in the stored value distinguishes a row this
migration set to `[]` from one a clean Run-AI set to `[]`, so reverting would
have to guess, and guessing wrong means either resurrecting a stuck assessment
or wiping a genuine resolution. 0044's own downgrade drops the column outright,
which is the honest way back.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | None = None
depends_on: str | None = None

#: Parent statuses that refuse every write path, in the casing the column is
#: MATCHED on (see `upgrade`). Compared case-insensitively on purpose.
#:
#: The first version of this migration ran clean and grandfathered **zero** rows
#: against 8,862 that needed it. `AttackAssessment.status` is a
#: `SAEnum(..., native_enum=False)`, and SQLAlchemy's `Enum` persists the
#: member's **NAME**, not its `.value` -- so the column holds `'APPROVED'` while
#: `AttackAssessmentStatus.APPROVED.value` is `'approved'`. Matching on the
#: value silently selected nothing.
#:
#: It was caught only by the row count in the log line below, which is the whole
#: argument for printing it: a backfill that touched nothing and a backfill that
#: correctly had nothing to do are indistinguishable afterwards.
_LOCKED = ("APPROVED", "RELEASED")


def upgrade() -> None:
    # Core rather than raw SQL so the JSON value is bound through the column's
    # own type: a literal '[]' needs a cast on Postgres and none on SQLite, and
    # hand-writing that difference is how a migration passes on SQLite and
    # fails in prod.
    coverage = sa.table(
        "attack_coverage",
        sa.column("unconfirmed_citations", sa.JSON()),
        sa.column("assessment_id"),
    )
    assessments = sa.table("attack_assessments", sa.column("id"), sa.column("status"))

    # `upper()` rather than trusting either casing. The stored representation is
    # SQLAlchemy's, not ours, and a migration is pinned to history while the
    # model is free to change -- importing `AttackAssessmentStatus` here would
    # couple this file to a model that may not exist in this shape in a year.
    # Both SQLite and Postgres have `upper()`.
    locked = sa.select(assessments.c.id).where(sa.func.upper(assessments.c.status).in_(_LOCKED))
    result = op.get_bind().execute(
        coverage.update()
        .where(coverage.c.unconfirmed_citations.is_(None))
        .where(coverage.c.assessment_id.in_(locked))
        .values(unconfirmed_citations=[])
    )
    # Success paths log too. A backfill that silently touched zero rows and one
    # that correctly had nothing to do look identical afterwards, and the number
    # is the only evidence of which happened.
    print(f"[0045] grandfathered {result.rowcount} coverage rows under locked assessments")


def downgrade() -> None:
    print(
        "[0045] downgrade is a deliberate no-op: a backfilled '[]' is "
        "indistinguishable from one a clean Run-AI wrote, so reverting would "
        "either resurrect a stuck assessment or wipe a genuine resolution. "
        "0044's downgrade drops the column, which is the honest way back."
    )
