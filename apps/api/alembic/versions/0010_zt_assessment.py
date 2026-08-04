"""zero trust: zt_assessments + zt_answers

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-20 09:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
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
        "zt_assessments",
        _uuid_col("id", primary_key=True, nullable=False),
        _uuid_col("service_id", nullable=False),
        _uuid_col("client_id"),
        sa.Column("framework", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        _uuid_col("approved_by"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name="fk_zt_assessments_service_id_services",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["client.id"],
            name="fk_zt_assessments_client_id_client",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name="fk_zt_assessments_approved_by_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("service_id", "version", name="uq_zt_assessments_service_version"),
    )
    op.create_index("ix_zt_assessments_service_id", "zt_assessments", ["service_id"])
    op.create_index("ix_zt_assessments_status", "zt_assessments", ["status"])

    op.create_table(
        "zt_answers",
        _uuid_col("id", primary_key=True, nullable=False),
        _uuid_col("assessment_id", nullable=False),
        _uuid_col("client_id"),
        sa.Column("capability_code", sa.String(32), nullable=False),
        sa.Column("maturity_stage", sa.SmallInteger),
        sa.Column("notes", sa.Text),
        _uuid_col("evidence_artifact_id"),
        _uuid_col("answered_by"),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["zt_assessments.id"],
            name="fk_zt_answers_assessment_id_zt_assessments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["client.id"],
            name="fk_zt_answers_client_id_client",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_artifact_id"],
            ["artifacts.id"],
            name="fk_zt_answers_evidence_artifact_id_artifacts",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["answered_by"],
            ["users.id"],
            name="fk_zt_answers_answered_by_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "assessment_id",
            "capability_code",
            name="uq_zt_answers_assessment_capability",
        ),
    )
    op.create_index("ix_zt_answers_assessment_id", "zt_answers", ["assessment_id"])
    op.create_index("ix_zt_answers_capability_code", "zt_answers", ["capability_code"])


def downgrade() -> None:
    op.drop_index("ix_zt_answers_capability_code", table_name="zt_answers")
    op.drop_index("ix_zt_answers_assessment_id", table_name="zt_answers")
    op.drop_table("zt_answers")
    op.drop_index("ix_zt_assessments_status", table_name="zt_assessments")
    op.drop_index("ix_zt_assessments_service_id", table_name="zt_assessments")
    op.drop_table("zt_assessments")
