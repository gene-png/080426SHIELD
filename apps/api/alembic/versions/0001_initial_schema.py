"""initial schema: client, users, audit_entries with append-only trigger

Revision ID: 0001
Revises:
Create Date: 2026-05-19 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_col(name: str = "id", *, primary_key: bool = False, nullable: bool = True) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
        primary_key=primary_key,
        nullable=nullable,
    )


def _jsonb_col(name: str, *, nullable: bool = True) -> sa.Column:
    return sa.Column(name, postgresql.JSONB().with_variant(sa.JSON, "sqlite"), nullable=nullable)


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    op.create_table(
        "client",
        _uuid_col("id", primary_key=True, nullable=False),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("dba_name", sa.String(255)),
        sa.Column("website", sa.String(512)),
        sa.Column("size_band", sa.String(64)),
        sa.Column("industry", sa.String(128)),
        sa.Column("address_line1", sa.String(255)),
        sa.Column("address_line2", sa.String(255)),
        sa.Column("city", sa.String(128)),
        sa.Column("state", sa.String(64)),
        sa.Column("postal_code", sa.String(32)),
        sa.Column("country", sa.String(64)),
        _uuid_col("primary_poc_user_id"),
        sa.Column("prompting_context", sa.Text),
        sa.Column(
            "service_interests",
            postgresql.ARRAY(sa.String(32)).with_variant(sa.JSON, "sqlite"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "users",
        _uuid_col("id", primary_key=True, nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("title", sa.String(255)),
        sa.Column("phone", sa.String(64)),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        _uuid_col("client_id"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("mfa_enrolled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["client.id"],
            name="fk_users_client_id_client",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "audit_entries",
        _uuid_col("id", primary_key=True, nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        _uuid_col("actor_user_id"),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        _uuid_col("target_id"),
        _jsonb_col("details"),
        sa.Column("correlation_id", sa.String(128)),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_audit_entries_actor_user_id_users",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_audit_entries_at", "audit_entries", ["at"])
    op.create_index("ix_audit_entries_target", "audit_entries", ["target_type", "target_id"])
    op.create_index("ix_audit_entries_correlation", "audit_entries", ["correlation_id"])

    # Append-only enforcement at the DB layer (Postgres only).
    # The application also enforces this via SQLAlchemy event listeners
    # (apps/api/app/models/audit_entry.py) so SQLite tests catch logic
    # bugs that try to mutate audit rows.
    if dialect_name == "postgresql":
        op.execute("""
            CREATE OR REPLACE FUNCTION audit_entries_block_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'audit_entries rows are append-only (%)', TG_OP;
            END;
            $$ LANGUAGE plpgsql;
            """)
        op.execute("""
            CREATE TRIGGER audit_entries_no_update
            BEFORE UPDATE ON audit_entries
            FOR EACH ROW EXECUTE FUNCTION audit_entries_block_mutation();
            """)
        op.execute("""
            CREATE TRIGGER audit_entries_no_delete
            BEFORE DELETE ON audit_entries
            FOR EACH ROW EXECUTE FUNCTION audit_entries_block_mutation();
            """)


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_entries_no_delete ON audit_entries")
        op.execute("DROP TRIGGER IF EXISTS audit_entries_no_update ON audit_entries")
        op.execute("DROP FUNCTION IF EXISTS audit_entries_block_mutation()")

    op.drop_index("ix_audit_entries_correlation", table_name="audit_entries")
    op.drop_index("ix_audit_entries_target", table_name="audit_entries")
    op.drop_index("ix_audit_entries_at", table_name="audit_entries")
    op.drop_table("audit_entries")
    op.drop_table("users")
    op.drop_table("client")
