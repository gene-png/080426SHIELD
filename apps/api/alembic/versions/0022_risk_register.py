"""risk_registers + risk_entries (Work Order E)

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-25 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _uuid(name: str, *, pk: bool = False, nullable: bool = True) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
        primary_key=pk,
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "risk_registers",
        _uuid("id", pk=True, nullable=False),
        _uuid("client_id", nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        _uuid("generated_by", nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        _uuid("superseded_by", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["client.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generated_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["superseded_by"], ["risk_registers.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_risk_registers_client_id", "risk_registers", ["client_id"])

    op.create_table(
        "risk_entries",
        _uuid("id", pk=True, nullable=False),
        _uuid("register_id", nullable=False),
        _uuid("client_id", nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("axis", sa.String(16), nullable=True),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column("source_id", sa.String(64), nullable=True),
        sa.Column("linked_techniques", _JSON, nullable=True),
        sa.Column("linked_controls", _JSON, nullable=True),
        sa.Column("likelihood", sa.String(16), nullable=True),
        sa.Column("impact", sa.String(16), nullable=True),
        sa.Column("tier", sa.String(16), nullable=True),
        sa.Column("compensating_controls", sa.Text, nullable=True),
        sa.Column("residual_risk", sa.Text, nullable=True),
        sa.Column("recommended_action", sa.String(16), nullable=True),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("origin", sa.String(24), nullable=False, server_default="ai_generated"),
        sa.Column("trust", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["register_id"], ["risk_registers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["client.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_risk_entries_register_id", "risk_entries", ["register_id"])
    op.create_index("ix_risk_entries_client_id", "risk_entries", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_risk_entries_client_id", table_name="risk_entries")
    op.drop_index("ix_risk_entries_register_id", table_name="risk_entries")
    op.drop_table("risk_entries")
    op.drop_index("ix_risk_registers_client_id", table_name="risk_registers")
    op.drop_table("risk_registers")
