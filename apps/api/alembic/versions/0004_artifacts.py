"""artifacts table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-19 00:03:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_col(name: str = "id", *, primary_key: bool = False, nullable: bool = True) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
        primary_key=primary_key,
        nullable=nullable,
    )


def _jsonb_col(name: str, *, nullable: bool = True) -> sa.Column:
    return sa.Column(name, postgresql.JSONB().with_variant(sa.JSON, "sqlite"), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "artifacts",
        _uuid_col("id", primary_key=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("file_storage_key", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        _jsonb_col("lineage"),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(64)),
        _uuid_col("uploaded_by", nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        _uuid_col("archived_by"),
        sa.Column("purged_at", sa.DateTime(timezone=True)),
        _uuid_col("purged_by"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name="fk_artifacts_uploaded_by_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_artifacts_uploaded_at", "artifacts", ["uploaded_at"])
    op.create_index("ix_artifacts_uploaded_by", "artifacts", ["uploaded_by"])
    op.create_index("ix_artifacts_sha256", "artifacts", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_sha256", table_name="artifacts")
    op.drop_index("ix_artifacts_uploaded_by", table_name="artifacts")
    op.drop_index("ix_artifacts_uploaded_at", table_name="artifacts")
    op.drop_table("artifacts")
