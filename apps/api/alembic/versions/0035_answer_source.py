"""zt_answers.answer_source — who supplied each Zero Trust answer

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-05 00:00:00

Adds a nullable ``answer_source`` ('client' | 'ai' | 'consultant') to
``zt_answers``.

Zero Trust ONLY, deliberately. CSF's Run-AI writes ``csf_dimension_scores`` and
never touches the client's ``csf_answers``, so provenance there survives in
``answered_by`` and needs no new column. Adding one to a table nothing reads
would be speculative.

Motivation (2026-08-04 guided review). Run-AI overwrites every unlocked row and
stamps ``answered_by`` with the ADMIN who pressed the button, so after one run
there was nothing left to say an answer had come from the client. With the
offline guard missing on the Zero Trust workspace, a FIXTURE run overwrote a
real client self-assessment with canned demo values — average maturity fell
from 2.14 to 1.49 and the Identity pillar from 3.00 to 1 — and nothing in the
data could distinguish the two afterwards.

The existing ``locked`` flag already means "never changed by a Run-AI rerun",
but it records a CONSULTANT'S deliberate choice; provenance is a different fact
and needs its own column. With this in place a fixture run treats
client-sourced answers as untouchable.

Wholly additive (C0 pattern): nullable, so every pre-migration row parses
unchanged as "provenance unknown" and is treated as not-client-sourced.
SQLite-safe via ``batch_alter_table`` (tests run SQLite, prod runs Postgres).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | Sequence[str] | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("zt_answers") as batch:
        batch.add_column(sa.Column("answer_source", sa.String(16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("zt_answers") as batch:
        batch.drop_column("answer_source")
