"""client_domain: approved email domains per client (Work Order B1)

A self-registering user whose email domain matches an approved row joins
that client as role `client`. One client may own several domains; a domain
is globally unique (it can only point at one client).

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-25 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_col(name: str = "id", *, primary_key: bool = False, nullable: bool = True) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
        primary_key=primary_key,
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "client_domain",
        _uuid_col("id", primary_key=True, nullable=False),
        _uuid_col("client_id", nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        _uuid_col("created_by", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["client.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("domain", name="uq_client_domain_domain"),
    )
    op.create_index("ix_client_domain_client_id", "client_domain", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_client_domain_client_id", table_name="client_domain")
    op.drop_table("client_domain")
