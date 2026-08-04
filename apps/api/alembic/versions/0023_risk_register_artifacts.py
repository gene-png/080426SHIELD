"""risk_registers export artifact columns (Work Order E)

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-25 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


def _uuid_col(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
        nullable=True,
    )


revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("risk_registers") as batch:
        batch.add_column(_uuid_col("xlsx_artifact_id"))
        batch.add_column(_uuid_col("pdf_artifact_id"))
        batch.add_column(_uuid_col("docx_artifact_id"))


def downgrade() -> None:
    with op.batch_alter_table("risk_registers") as batch:
        batch.drop_column("docx_artifact_id")
        batch.drop_column("pdf_artifact_id")
        batch.drop_column("xlsx_artifact_id")
