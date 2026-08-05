"""client.archived_at for admin tenant removal (issue 3)

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-04 00:00:00

Adds a nullable ``archived_at`` timestamp to ``client``. The admin console had
no way to remove a tenant; ``DELETE /admin/clients/{cid}`` now stamps this
column instead of destroying the row, mirroring the existing ``archive_service``
precedent. Data is retained per policy: assessments, deliverables, and the
append-only audit trail all keep referencing the tenant, and the action is
reversible.

Wholly additive (C0 pattern): the column is nullable, so every pre-migration
row parses unchanged as "not archived". SQLite-safe via ``batch_alter_table``
(tests run SQLite, prod runs Postgres).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | Sequence[str] | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("client") as batch:
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("client") as batch:
        batch.drop_column("archived_at")
