"""attack_coverage: detection/prevention/response tools + rationale (Work Order D2)

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-25 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("attack_coverage") as batch:
        batch.add_column(sa.Column("detection_tools", _JSON, nullable=True))
        batch.add_column(sa.Column("prevention_tools", _JSON, nullable=True))
        batch.add_column(sa.Column("response_tools", _JSON, nullable=True))
        batch.add_column(sa.Column("rationale", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("attack_coverage") as batch:
        batch.drop_column("rationale")
        batch.drop_column("response_tools")
        batch.drop_column("prevention_tools")
        batch.drop_column("detection_tools")
