"""user lockout + failed-login bookkeeping columns

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-19 00:01:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "failed_login_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "users",
        sa.Column("last_failed_login_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "users",
        sa.Column("locked_until_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_column("users", "locked_until_at")
    op.drop_column("users", "last_failed_login_at")
    op.drop_column("users", "failed_login_count")
