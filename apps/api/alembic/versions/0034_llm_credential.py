"""llm_credential — runtime provider API key, encrypted at rest (issue 2)

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-04 00:00:00

Adds the table backing ``POST/DELETE /admin/llm-key``. Before this the only
way to supply a provider key was an environment variable read once at boot, so
an admin who noticed AI was offline could not fix it without a redeploy.

``encrypted_key`` holds Fernet ciphertext, never the key itself — see
``app/ai/keystore.py``. ``provider`` is UNIQUE so setting a key twice replaces
it instead of accumulating stale credentials.

Wholly additive: a new table, no changes to existing rows. SQLite-safe (plain
``create_table``; tests run SQLite, prod runs Postgres).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | Sequence[str] | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_credential",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("encrypted_key", sa.String(length=2048), nullable=False),
        sa.Column("set_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", name="uq_llm_credential_provider"),
    )


def downgrade() -> None:
    op.drop_table("llm_credential")
