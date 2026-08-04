"""MFA TOTP: users.mfa_totp_secret + user_recovery_codes (Sprint 6 T4, D-027)

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-12 00:00:00

Real TOTP MFA (D-027). Adds an encrypted TOTP secret column to ``users`` and a
``user_recovery_codes`` table holding Argon2-hashed one-time recovery codes.
Both changes are additive (C0 pattern): ``mfa_totp_secret`` is nullable so old
rows parse as "not enrolled", and the recovery-codes table is brand new. The
FK cascade-deletes recovery codes with the user. SQLite-safe via
``batch_alter_table``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: str | Sequence[str] | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("mfa_totp_secret", sa.String(length=512), nullable=True))

    op.create_table(
        "user_recovery_codes",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("code_hash", sa.String(length=512), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_recovery_codes_user", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_recovery_codes"),
    )
    op.create_index(
        "ix_user_recovery_codes_user_id", "user_recovery_codes", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_user_recovery_codes_user_id", table_name="user_recovery_codes")
    op.drop_table("user_recovery_codes")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("mfa_totp_secret")
