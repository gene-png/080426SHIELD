"""tech debt: services, capability_lists, capability_items, deliverables

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-19 00:05:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
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
        "services",
        _uuid_col("id", primary_key=True, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("title", sa.String(255), nullable=False),
        _uuid_col("source_request_id"),
        _uuid_col("opened_by", nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_request_id"],
            ["service_requests.id"],
            name="fk_services_source_request_id_service_requests",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["opened_by"],
            ["users.id"],
            name="fk_services_opened_by_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_services_kind", "services", ["kind"])
    op.create_index("ix_services_status", "services", ["status"])

    op.create_table(
        "capability_lists",
        _uuid_col("id", primary_key=True, nullable=False),
        _uuid_col("service_id", nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        _uuid_col("approved_by"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name="fk_capability_lists_service_id_services",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name="fk_capability_lists_approved_by_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("service_id", "version", name="uq_capability_lists_service_id_version"),
    )

    op.create_table(
        "capability_items",
        _uuid_col("id", primary_key=True, nullable=False),
        _uuid_col("capability_list_id", nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("vendor", sa.String(255)),
        sa.Column("category", sa.String(128)),
        sa.Column("function", sa.String(255)),
        sa.Column("annual_cost_usd", sa.Numeric(14, 2)),
        sa.Column("license_count", sa.Integer),
        sa.Column("notes", sa.Text),
        sa.Column("confidence_pct", sa.Integer),
        _uuid_col("source_artifact_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["capability_list_id"],
            ["capability_lists.id"],
            name="fk_capability_items_capability_list_id_capability_lists",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"],
            ["artifacts.id"],
            name="fk_capability_items_source_artifact_id_artifacts",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_capability_items_list", "capability_items", ["capability_list_id"])

    op.create_table(
        "deliverables",
        _uuid_col("id", primary_key=True, nullable=False),
        _uuid_col("service_id", nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        _uuid_col("pdf_artifact_id"),
        _uuid_col("xlsx_artifact_id"),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        _uuid_col("finalized_by"),
        sa.Column("released_to_client_at", sa.DateTime(timezone=True)),
        _uuid_col("superseded_by"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name="fk_deliverables_service_id_services",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pdf_artifact_id"],
            ["artifacts.id"],
            name="fk_deliverables_pdf_artifact_id_artifacts",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["xlsx_artifact_id"],
            ["artifacts.id"],
            name="fk_deliverables_xlsx_artifact_id_artifacts",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["finalized_by"],
            ["users.id"],
            name="fk_deliverables_finalized_by_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by"],
            ["deliverables.id"],
            name="fk_deliverables_superseded_by_deliverables",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_deliverables_service_id", "deliverables", ["service_id"])
    op.create_index(
        "ix_deliverables_released",
        "deliverables",
        ["released_to_client_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_deliverables_released", table_name="deliverables")
    op.drop_index("ix_deliverables_service_id", table_name="deliverables")
    op.drop_table("deliverables")
    op.drop_index("ix_capability_items_list", table_name="capability_items")
    op.drop_table("capability_items")
    op.drop_table("capability_lists")
    op.drop_index("ix_services_status", table_name="services")
    op.drop_index("ix_services_kind", table_name="services")
    op.drop_table("services")
