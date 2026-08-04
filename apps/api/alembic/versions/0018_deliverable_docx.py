"""deliverables.docx_artifact_id - Word deliverable (Work Order C4)

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-25 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("deliverables") as batch:
        batch.add_column(
            sa.Column(
                "docx_artifact_id",
                postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("deliverables") as batch:
        batch.drop_column("docx_artifact_id")
