"""users: active_refresh_jti for refresh-token rotation (Sprint 3 T2)

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-09 00:00:00

Stores the jti of the single currently valid refresh token per user so a
replayed (already-rotated) refresh token can be rejected at /auth/refresh.
Additive + nullable (C0 pattern): old rows parse unchanged; a null means the
user has no active refresh token yet. SQLite-safe via batch_alter_table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("active_refresh_jti", sa.String(length=36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("active_refresh_jti")
