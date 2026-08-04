"""messages: per-service admin<->client thread (Work Order C7)

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-25 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_col(name: str = "id", *, primary_key: bool = False, nullable: bool = True) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
        primary_key=primary_key,
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "messages",
        _uuid_col("id", primary_key=True, nullable=False),
        _uuid_col("client_id", nullable=False),
        _uuid_col("service_id", nullable=False),
        _uuid_col("author_user_id", nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["client.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_messages_client_id", "messages", ["client_id"])
    op.create_index("ix_messages_service_id", "messages", ["service_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_service_id", table_name="messages")
    op.drop_index("ix_messages_client_id", table_name="messages")
    op.drop_table("messages")
