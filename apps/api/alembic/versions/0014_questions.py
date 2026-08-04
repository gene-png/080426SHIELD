"""questionnaire question catalog: questions

Adds the `questions` table that holds the rich interview prompts extracted
from the Kentro Step 1.1/1.2/1.3 .docx files (one row per question, keyed by
framework_key + external_id). It sits alongside csf_assessments/csf_answers;
no foreign keys (it is static reference seed data).

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-16 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_col(name: str = "id", *, primary_key: bool = False, nullable: bool = True) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
        primary_key=primary_key,
        nullable=nullable,
    )


# Native JSONB on Postgres, generic JSON on SQLite (tests).
_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "questions",
        _uuid_col("id", primary_key=True, nullable=False),
        sa.Column("framework_key", sa.String(40), nullable=False),
        sa.Column("external_id", sa.String(40), nullable=False),
        sa.Column("pillar", sa.String(120), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("stem", sa.Text, nullable=False),
        sa.Column("cues", _JSON),
        sa.Column("phase", sa.String(40)),
        sa.Column("framework_activities", _JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "framework_key",
            "external_id",
            name="uq_questions_framework_external_id",
        ),
    )
    op.create_index("ix_questions_framework_key", "questions", ["framework_key"])
    op.create_index("ix_questions_pillar", "questions", ["pillar"])


def downgrade() -> None:
    op.drop_index("ix_questions_pillar", table_name="questions")
    op.drop_index("ix_questions_framework_key", table_name="questions")
    op.drop_table("questions")
