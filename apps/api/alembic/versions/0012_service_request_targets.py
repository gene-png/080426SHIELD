"""service_request: client-supplied assessment targets

Adds CSF target tier + profile and ZT target stage to service_requests so the
client can set their goal at intake (consultant validates rather than guesses).

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-21 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "service_requests",
        sa.Column("csf_target_tier", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "service_requests",
        sa.Column("csf_profile", sa.String(8), nullable=True),
    )
    op.add_column(
        "service_requests",
        sa.Column("zt_target_stage", sa.SmallInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("service_requests", "zt_target_stage")
    op.drop_column("service_requests", "csf_profile")
    op.drop_column("service_requests", "csf_target_tier")
