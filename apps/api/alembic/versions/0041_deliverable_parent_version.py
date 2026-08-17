"""deliverable -> parent version link, so release knows which row it released

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-17 00:00:00

W4 (`docs/plans/2026-08-08-cross-service-integrity.md` §8) assigns `RELEASED` to
the parent assessment/capability-list inside the release path, because today no
API route assigns it at all — the only writer in the repo is `seed_demo.py`, so
a service released through the product keeps a parent that still reads APPROVED.
The visible symptom is the progress bar showing `release` as the current
incomplete stage on a service whose report is already with the client
(`services/stages.py` derives `released` from the PARENT status, not from
`deliverables.released_at`).

Doing that needs an answer to "which parent row?", and the schema could not give
one. `deliverables` has no foreign key to any parent — only `service_id` — and
deliverable versions and assessment versions are INDEPENDENT counters. So the
candidates ("latest non-discarded", "latest APPROVED", "the one it was built
from") diverge in a sequence that really happens:

    approve v1 -> finalize deliverable -> cut v2 -> approve v2 -> release

There, "latest APPROVED" flips v2 — a row the released report was never built
from. This repo has hit the version trap twice before (migration 0032's notes,
and the Tech-Debt stage-evidence anchor), so the link is recorded rather than
inferred.

`parent_version` is stamped at FINALIZE time, which is the moment the
deliverable's content is frozen against a specific parent version, and it is the
gate that already requires the parent to be APPROVED. Release then flips exactly
that row.

NULL means "finalized before this migration" and is expected on every existing
row — additive/optional so older rows parse unchanged (the C0 pattern). Release
leaves those parents alone and says so in the log rather than guessing; guessing
is what this column exists to stop.

Deliberately NOT a foreign key: the four parents live in four different tables
(`csf_assessments`, `zt_assessments`, `attack_assessments`, `capability_lists`),
so there is no single referent. `(service_id, parent_version)` identifies the row
uniquely because each parent table already carries a unique constraint on
`(service_id, version)`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041"
down_revision: str | Sequence[str] | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("deliverables") as batch:
        batch.add_column(sa.Column("parent_version", sa.Integer(), nullable=True))

    # Backfill ONLY where there is exactly one candidate.
    #
    # A service with a single parent version has no ambiguity: every deliverable
    # it has can only have been built from that one row. A service with several
    # is the case this column exists for, and is left NULL rather than guessed —
    # release then refuses to flip and says so (`release_parent_unknown`), and a
    # re-release repairs it once the version is known.
    #
    # Written as four statements rather than one because the four parents live in
    # four tables. Each is scoped to rows still NULL so it is safe to re-run.
    for table in (
        "csf_assessments",
        "zt_assessments",
        "attack_assessments",
        "capability_lists",
    ):
        op.execute(sa.text(f"""
                UPDATE deliverables
                   SET parent_version = (
                       SELECT MIN(p.version) FROM {table} p
                        WHERE p.service_id = deliverables.service_id
                   )
                 WHERE parent_version IS NULL
                   AND (
                       SELECT COUNT(*) FROM {table} p
                        WHERE p.service_id = deliverables.service_id
                   ) = 1
                """))  # noqa: S608 - `table` is a literal from the tuple above


def downgrade() -> None:
    with op.batch_alter_table("deliverables") as batch:
        batch.drop_column("parent_version")
