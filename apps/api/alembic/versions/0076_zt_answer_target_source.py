"""ZT per-capability target provenance (#982, option (A)).

Revision ID: 0076
Revises: 0075

Numbered 0076 by the advisor's ruling (#736 6217663777). `down_revision` is
the single head on main when this was last merged (0075, CSF, #1203). It is
re-derived if 0074 (Tech Debt, #1060) lands first, so main has one head at
every merge.

The AI stopped writing targets with #981 (2026-10-13), and the advisor ruled
that targets earlier AI runs wrote stay. Nothing recorded who set a target, so
an AI-set target and a consultant's look the same. This adds
`zt_answers.target_source` (VARCHAR(16), nullable, no default, no backfill):

- the consultant's PATCH stamps `'consultant'`; clearing a target clears it;
- NULL means "origin not recorded", which is every target stored before this
  migration. Missing data defaults to unconfirmed: none of them is presented as
  consultant-chosen, and the consultant workspace discloses them.

## Blast radius

Additive and nullable; every existing row reads NULL, which is the true state
of what is known. No figure moves.

## Downgrade

Drops the column. A re-upgrade gives NULL back ("not recorded"), which is the
honest reading of a fact that was lost, so the downgrade does not refuse.

`batch_alter_table`, so it runs on SQLite (tests) and Postgres alike.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0076"
down_revision: str | Sequence[str] | None = "0075"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("zt_answers") as batch:
        batch.add_column(sa.Column("target_source", sa.String(16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("zt_answers") as batch:
        batch.drop_column("target_source")
