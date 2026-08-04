"""Email verification + password-reset tokens (Sprint 6 T5, D-028)

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-12 00:00:00

Real email verification + password reset (D-028). Adds a brand-new
``email_tokens`` table holding SHA-256-hashed single-use tokens with a purpose
(email verification or password reset), an expiry, and a used-at marker. Wholly
additive (C0 pattern) — no existing table changes, so older rows parse
unchanged. The FK cascade-deletes tokens with the user. SQLite-safe.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031"
down_revision: str | Sequence[str] | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    op.create_table(
        "email_tokens",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_email_tokens_user", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_email_tokens"),
    )
    op.create_index("ix_email_tokens_user_id", "email_tokens", ["user_id"], unique=False)
    op.create_index("ix_email_tokens_token_hash", "email_tokens", ["token_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_email_tokens_token_hash", table_name="email_tokens")
    op.drop_index("ix_email_tokens_user_id", table_name="email_tokens")
    op.drop_table("email_tokens")
