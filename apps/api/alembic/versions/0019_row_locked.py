"""per-row `locked` flag on grid tables (Work Order C2)

A locked row is never overwritten by a Run-AI rerun. Adds `locked` (NOT NULL,
default false) to capability_items, csf_answers, zt_answers, attack_coverage.

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-25 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("capability_items", "csf_answers", "zt_answers", "attack_coverage")


def upgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column(
                    "locked",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )


def downgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column("locked")
