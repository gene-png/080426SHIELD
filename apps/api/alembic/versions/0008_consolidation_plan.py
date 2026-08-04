"""consolidation plan: capability_items.disposition + rationale + target

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-19 00:07:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite can't ALTER constraints, so we use batch mode (Alembic
    # copies the table, applies the schema, swaps). On Postgres the
    # batch wraps to a plain ALTER TABLE.
    with op.batch_alter_table("capability_items") as batch:
        batch.add_column(sa.Column("disposition", sa.String(16)))
        batch.add_column(sa.Column("disposition_rationale", sa.Text))
        batch.add_column(
            sa.Column(
                "consolidation_target_id",
                postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
            )
        )
        batch.create_foreign_key(
            "fk_capability_items_consolidation_target_id",
            "capability_items",
            ["consolidation_target_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("capability_items") as batch:
        batch.drop_constraint("fk_capability_items_consolidation_target_id", type_="foreignkey")
        batch.drop_column("consolidation_target_id")
        batch.drop_column("disposition_rationale")
        batch.drop_column("disposition")
