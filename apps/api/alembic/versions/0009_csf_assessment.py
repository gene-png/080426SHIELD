"""csf 2.0 assessment: csf_assessments + csf_answers

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-19 16:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
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
        "csf_assessments",
        _uuid_col("id", primary_key=True, nullable=False),
        _uuid_col("service_id", nullable=False),
        _uuid_col("client_id"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        _uuid_col("approved_by"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name="fk_csf_assessments_service_id_services",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["client.id"],
            name="fk_csf_assessments_client_id_client",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name="fk_csf_assessments_approved_by_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("service_id", "version", name="uq_csf_assessments_service_version"),
    )
    op.create_index("ix_csf_assessments_service_id", "csf_assessments", ["service_id"])
    op.create_index("ix_csf_assessments_status", "csf_assessments", ["status"])

    op.create_table(
        "csf_answers",
        _uuid_col("id", primary_key=True, nullable=False),
        _uuid_col("assessment_id", nullable=False),
        _uuid_col("client_id"),
        sa.Column("subcategory_code", sa.String(16), nullable=False),
        sa.Column("maturity_tier", sa.SmallInteger),
        sa.Column("notes", sa.Text),
        _uuid_col("evidence_artifact_id"),
        _uuid_col("answered_by"),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["csf_assessments.id"],
            name="fk_csf_answers_assessment_id_csf_assessments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["client.id"],
            name="fk_csf_answers_client_id_client",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_artifact_id"],
            ["artifacts.id"],
            name="fk_csf_answers_evidence_artifact_id_artifacts",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["answered_by"],
            ["users.id"],
            name="fk_csf_answers_answered_by_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "assessment_id",
            "subcategory_code",
            name="uq_csf_answers_assessment_subcategory",
        ),
    )
    op.create_index("ix_csf_answers_assessment_id", "csf_answers", ["assessment_id"])
    op.create_index("ix_csf_answers_subcategory_code", "csf_answers", ["subcategory_code"])


def downgrade() -> None:
    op.drop_index("ix_csf_answers_subcategory_code", table_name="csf_answers")
    op.drop_index("ix_csf_answers_assessment_id", table_name="csf_answers")
    op.drop_table("csf_answers")
    op.drop_index("ix_csf_assessments_status", table_name="csf_assessments")
    op.drop_index("ix_csf_assessments_service_id", table_name="csf_assessments")
    op.drop_table("csf_assessments")
