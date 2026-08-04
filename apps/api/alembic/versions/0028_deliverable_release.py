"""deliverables: release-to-client fields (Sprint 5 T1, D-025)

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-10 00:00:00

Reintroduces an explicit release-to-client step (Master Spec §12; D-025) after
migration 0015 dropped the reviewer-era `released_to_client_at` (D-023). Adds
`released_at` (nullable DateTime) + `released_by` (nullable FK users.id). Both
additive + nullable (C0 pattern): old rows parse as UNRELEASED, so the client
sees nothing until a consultant explicitly releases. SET NULL on delete so the
deliverable outlives the releasing user. SQLite-safe via batch_alter_table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: str | Sequence[str] | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("deliverables") as batch:
        batch.add_column(sa.Column("released_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("released_by", _UUID, nullable=True))
        batch.create_foreign_key(
            "fk_deliverables_released_by_users",
            "users",
            ["released_by"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("deliverables") as batch:
        batch.drop_constraint("fk_deliverables_released_by_users", type_="foreignkey")
        batch.drop_column("released_by")
        batch.drop_column("released_at")
