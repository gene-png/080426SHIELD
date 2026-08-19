"""csf_dimension_scores.answer_source — who supplied each Working Profile score

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-19 00:00:00

Adds a nullable ``answer_source`` ('ai' | 'consultant') to
``csf_dimension_scores``, so an offline (fixture) Run-AI can leave alone the
scores a human typed.

REVERSES A STATED RATIONALE, deliberately — read this before assuming 0035 was
wrong. Migration 0035 added the same column to ``zt_answers`` and said:

    Zero Trust ONLY, deliberately. CSF's Run-AI writes ``csf_dimension_scores``
    and never touches the client's ``csf_answers``, so provenance there survives
    in ``answered_by`` and needs no new column.

That reasoning was correct about the question it asked. CSF's Run-AI genuinely
does not touch ``csf_answers``, so the CLIENT's self-assessment was never at
risk on the CSF side, and 0035's scope was right for the incident it responded
to (a fixture run destroying a client's Zero Trust submission).

What it did not consider is the other population. ``csf_dimension_scores`` is
where a CONSULTANT types the Working Profile by hand, and an offline Run-AI
overwrote those unless the row had been explicitly locked first. Different
owner, same loss: work a human did, replaced by canned demo values, with nothing
afterwards able to tell them apart. Issue #67.

WHY A COLUMN AND NOT A VALUE TEST. ZT could ask "is this row answered?" because
``maturity_stage`` is nullable — an untouched row is NULL. Every dimension on
``csf_dimension_scores`` is ``NOT NULL DEFAULT 0``, so "has a value" is true for
every seeded row the moment a profile is created, and 0 is a legitimate score.
Protection therefore has to key on "somebody actually wrote this", which nothing
in the schema recorded. Hence the column.

NULL keeps its meaning from 0035: provenance unknown, treated as NOT
protected. That is what lets a fixture run populate an empty Playbook, which the
D-017 demos and the e2e suite depend on — and it is why this is safe to add to a
live table: every pre-migration row reads exactly as it did before.

STATE THE COST OF THAT, because it is not only demo safety: hand-typed scores
that already exist on a live database are NOT protected by this migration. They
are indistinguishable from seeded defaults, and no backfill can tell them apart.
They become protected the first time a consultant edits them again. Backfilling
"everything existing is consultant work" was considered and rejected — it would
freeze every seeded row against offline runs, breaking the demos this column was
written to keep working.

Wholly additive (C0 pattern): nullable, no backfill, no default written.
SQLite-safe via ``batch_alter_table`` (tests run SQLite, prod runs Postgres).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("csf_dimension_scores") as batch:
        batch.add_column(sa.Column("answer_source", sa.String(length=16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("csf_dimension_scores") as batch:
        batch.drop_column("answer_source")
