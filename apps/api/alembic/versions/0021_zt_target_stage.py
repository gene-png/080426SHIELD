"""zt_answers.target_stage - per-capability target (Work Order D3)

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-25 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("zt_answers") as batch:
        batch.add_column(sa.Column("target_stage", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("zt_answers") as batch:
        batch.drop_column("target_stage")
