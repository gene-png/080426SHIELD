"""llm_calls: client_id tenant attribution (Sprint 3 T5)

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-09 00:00:00

Attributes each AI egress row to the client it was run for so the largest
cross-assessment payload (risk synthesis) is tenant-attributable. Additive +
nullable (C0 pattern): old rows parse unchanged; a null means the call was made
without a resolved client. SET NULL on delete so the audit row outlives the
tenant. SQLite-safe via batch_alter_table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("llm_calls") as batch:
        batch.add_column(sa.Column("client_id", _UUID, nullable=True))
        batch.create_foreign_key(
            "fk_llm_calls_client_id_client",
            "client",
            ["client_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_llm_calls_client_id", "llm_calls", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_calls_client_id", table_name="llm_calls")
    with op.batch_alter_table("llm_calls") as batch:
        batch.drop_constraint("fk_llm_calls_client_id_client", type_="foreignkey")
        batch.drop_column("client_id")
