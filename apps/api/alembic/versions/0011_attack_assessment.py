"""attack coverage: attack_assessments + attack_coverage

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-20 10:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
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
        "attack_assessments",
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
            name="fk_attack_assessments_service_id_services",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["client.id"],
            name="fk_attack_assessments_client_id_client",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name="fk_attack_assessments_approved_by_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("service_id", "version", name="uq_attack_assessments_service_version"),
    )
    op.create_index("ix_attack_assessments_service_id", "attack_assessments", ["service_id"])
    op.create_index("ix_attack_assessments_status", "attack_assessments", ["status"])

    op.create_table(
        "attack_coverage",
        _uuid_col("id", primary_key=True, nullable=False),
        _uuid_col("assessment_id", nullable=False),
        _uuid_col("client_id"),
        sa.Column("technique_code", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32)),
        sa.Column("notes", sa.Text),
        _uuid_col("evidence_artifact_id"),
        _uuid_col("answered_by"),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["attack_assessments.id"],
            name="fk_attack_coverage_assessment_id_attack_assessments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["client.id"],
            name="fk_attack_coverage_client_id_client",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_artifact_id"],
            ["artifacts.id"],
            name="fk_attack_coverage_evidence_artifact_id_artifacts",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["answered_by"],
            ["users.id"],
            name="fk_attack_coverage_answered_by_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "assessment_id",
            "technique_code",
            name="uq_attack_coverage_assessment_technique",
        ),
    )
    op.create_index("ix_attack_coverage_assessment_id", "attack_coverage", ["assessment_id"])
    op.create_index("ix_attack_coverage_technique_code", "attack_coverage", ["technique_code"])


def downgrade() -> None:
    op.drop_index("ix_attack_coverage_technique_code", table_name="attack_coverage")
    op.drop_index("ix_attack_coverage_assessment_id", table_name="attack_coverage")
    op.drop_table("attack_coverage")
    op.drop_index("ix_attack_assessments_status", table_name="attack_assessments")
    op.drop_index("ix_attack_assessments_service_id", table_name="attack_assessments")
    op.drop_table("attack_assessments")
