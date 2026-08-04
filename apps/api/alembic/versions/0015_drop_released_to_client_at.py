"""drop deliverables.released_to_client_at (Work Order A1)

Deliverables become admin-only: there is no client release path and no
client-visibility timestamp. `version` and `superseded_by` keep internal
history. The reviewer role (Work Order A3) is a string enum value, so no
DB enum change is needed there; we simply stop issuing it.

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-24 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop the index first (from 0006) so the SQLite batch rebuild does not
    # try to recreate an index on the column we are removing.
    op.drop_index("ix_deliverables_released", table_name="deliverables")
    # batch_alter_table so SQLite (tests) can drop the column too.
    with op.batch_alter_table("deliverables") as batch:
        batch.drop_column("released_to_client_at")


def downgrade() -> None:
    with op.batch_alter_table("deliverables") as batch:
        batch.add_column(
            sa.Column("released_to_client_at", sa.DateTime(timezone=True), nullable=True)
        )
    op.create_index(
        "ix_deliverables_released",
        "deliverables",
        ["released_to_client_at"],
    )
