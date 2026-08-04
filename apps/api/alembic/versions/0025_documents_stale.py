"""assessments: documents_stale flag (Work Order C3)

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-26 00:00:00

An AI run sets this true; finalize/export clears it, so the workspace can nudge
the admin to regenerate documents that no longer reflect the latest scoring.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("attack_assessments", "csf_assessments", "zt_assessments")


def upgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column(
                    "documents_stale",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )


def downgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column("documents_stale")
