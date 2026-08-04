"""intake: client.intake_completed_at, service_requests table

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-19 00:02:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
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
    op.add_column(
        "client",
        sa.Column("intake_completed_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "service_requests",
        _uuid_col("id", primary_key=True, nullable=False),
        sa.Column("service_type", sa.String(32), nullable=False),
        _uuid_col("requested_by", nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("deadline", sa.DateTime(timezone=True)),
        _uuid_col("fulfilled_service_id"),
        sa.Column("declined_at", sa.DateTime(timezone=True)),
        sa.Column("declined_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name="fk_service_requests_requested_by_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_service_requests_requested_at",
        "service_requests",
        ["requested_at"],
    )
    op.create_index(
        "ix_service_requests_service_type",
        "service_requests",
        ["service_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_service_requests_service_type", table_name="service_requests")
    op.drop_index("ix_service_requests_requested_at", table_name="service_requests")
    op.drop_table("service_requests")
    op.drop_column("client", "intake_completed_at")
