"""csf_gap_actions - CSF POA&M / action-plan per enterprise gap (Sprint 5 T5)

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-10 00:00:00

Spec step 10 (Master Spec :1345/:1346): per-gap Characterize / Prioritize /
Action items / POA&M linkage. New `csf_gap_actions` table keyed to
(assessment, subcategory); every annotation field is nullable so an older
assessment simply parses with zero action rows (C0 additive pattern). Additive
create_table only — no existing table is altered, and it is SQLite-safe (tests
run SQLite, prod runs Postgres).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: str | Sequence[str] | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    op.create_table(
        "csf_gap_actions",
        sa.Column("id", _UUID, primary_key=True, nullable=False),
        sa.Column("assessment_id", _UUID, nullable=False),
        sa.Column("client_id", _UUID, nullable=False),
        sa.Column("subcategory_code", sa.String(16), nullable=False),
        sa.Column("characterization", sa.String(16), nullable=True),
        sa.Column("priority_override", sa.String(2), nullable=True),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("deadline", sa.String(64), nullable=True),
        sa.Column("resources", sa.Text, nullable=True),
        sa.Column("success_criteria", sa.Text, nullable=True),
        sa.Column("poam_ref", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["csf_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["client.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "assessment_id",
            "subcategory_code",
            name="uq_csf_gap_actions_assessment_subcat",
        ),
    )
    op.create_index("ix_csf_gap_actions_assessment_id", "csf_gap_actions", ["assessment_id"])
    op.create_index("ix_csf_gap_actions_client_id", "csf_gap_actions", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_csf_gap_actions_client_id", table_name="csf_gap_actions")
    op.drop_index("ix_csf_gap_actions_assessment_id", table_name="csf_gap_actions")
    op.drop_table("csf_gap_actions")
