"""csf_dimension_scores - tiered Working Profile (Work Order D4)

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-25 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, pk: bool = False, nullable: bool = True) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
        primary_key=pk,
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "csf_dimension_scores",
        _uuid("id", pk=True, nullable=False),
        _uuid("assessment_id", nullable=False),
        _uuid("client_id", nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("subcategory_code", sa.String(16), nullable=False),
        sa.Column("governance", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("policy", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("implementation", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("monitoring", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("improvement", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("in_scope", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("what_we_found", sa.Text, nullable=True),
        _uuid("evidence_artifact_id", nullable=True),
        sa.Column("has_evidence", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("target_level", sa.SmallInteger, nullable=True),
        sa.Column("locked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["csf_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["client.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["evidence_artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "assessment_id",
            "tier",
            "subcategory_code",
            name="uq_csf_dimension_scores_assessment_tier_subcat",
        ),
    )
    op.create_index(
        "ix_csf_dimension_scores_assessment_id", "csf_dimension_scores", ["assessment_id"]
    )
    op.create_index("ix_csf_dimension_scores_client_id", "csf_dimension_scores", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_csf_dimension_scores_client_id", table_name="csf_dimension_scores")
    op.drop_index("ix_csf_dimension_scores_assessment_id", table_name="csf_dimension_scores")
    op.drop_table("csf_dimension_scores")
