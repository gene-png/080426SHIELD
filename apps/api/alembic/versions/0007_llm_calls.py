"""llm_calls table

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-19 00:06:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
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
        "llm_calls",
        _uuid_col("id", primary_key=True, nullable=False),
        _uuid_col("service_id"),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text),
        _uuid_col("response_artifact_id"),
        _uuid_col("requested_by", nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "redacted_counts",
            postgresql.JSONB().with_variant(sa.JSON, "sqlite"),
        ),
        sa.Column("correlation_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["service_id"], ["services.id"], name="fk_llm_calls_service_id", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["response_artifact_id"],
            ["artifacts.id"],
            name="fk_llm_calls_response_artifact_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name="fk_llm_calls_requested_by_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_llm_calls_service_id", "llm_calls", ["service_id"])
    op.create_index("ix_llm_calls_requested_at", "llm_calls", ["requested_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_calls_requested_at", table_name="llm_calls")
    op.drop_index("ix_llm_calls_service_id", table_name="llm_calls")
    op.drop_table("llm_calls")
