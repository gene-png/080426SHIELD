"""Multi-tenant: add client_id to services/service_requests/artifacts; enforce NOT NULL across business tables.

Pre-0013 the platform was single-tenant: exactly one `client` row per
deployment, and queries were implicitly scoped to that singleton. To
support multiple clients per deployment we need every business row to
declare which client it belongs to.

This migration:
  1. Adds nullable `client_id` to `services`, `service_requests`, `artifacts`.
  2. Backfills client_id everywhere from the existing singleton client
     (creates a placeholder client if data exists but no Client row does).
  3. Backfills the previously-unpopulated client_id on `csf_assessments`,
     `csf_answers`, `zt_assessments`, `zt_answers`, `attack_assessments`,
     `attack_coverage` via their parent service.
  4. Alters every business client_id to NOT NULL and indexes it.

User.client_id stays nullable on purpose: admin/reviewer rows with
client_id=NULL are platform-wide and can switch between clients.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-21 00:00:01

"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UUID_TYPE = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")

# Tables that gain a client_id column outright.
_NEW_CLIENT_ID_TABLES = ("services", "service_requests", "artifacts")

# Tables where the client_id column already exists (nullable) and needs to
# be backfilled + made NOT NULL. Each entry: (table, parent_table, parent_fk).
_EXISTING_CLIENT_ID_TABLES = (
    ("csf_assessments", "services", "service_id"),
    ("zt_assessments", "services", "service_id"),
    ("attack_assessments", "services", "service_id"),
    ("csf_answers", "csf_assessments", "assessment_id"),
    ("zt_answers", "zt_assessments", "assessment_id"),
    ("attack_coverage", "attack_assessments", "assessment_id"),
)


def _resolve_anchor_client(conn) -> str | None:
    """Return the client id we'll backfill everything to.

    Pre-multi-tenant invariant: at most one Client row exists. If business
    data exists but no Client row does (e.g. orphaned dev DB), create a
    "(legacy backfill)" client to anchor the data.
    """
    rows = conn.execute(sa.text("SELECT id FROM client")).fetchall()
    if len(rows) > 1:
        raise RuntimeError(
            "0013 multi-tenant migration assumes <= 1 existing client; "
            f"found {len(rows)}. Resolve manually before proceeding."
        )
    if len(rows) == 1:
        return str(rows[0][0])

    has_data = False
    for tbl in _NEW_CLIENT_ID_TABLES:
        n = conn.execute(sa.text(f"SELECT COUNT(*) FROM {tbl}")).scalar_one()
        if n > 0:
            has_data = True
            break
    if not has_data:
        return None

    new_id = str(_uuid.uuid4())
    now = datetime.now(UTC)
    conn.execute(
        sa.text(
            "INSERT INTO client (id, legal_name, created_at, updated_at) "
            "VALUES (:cid, :name, :created_at, :updated_at)"
        ),
        {"cid": new_id, "name": "(legacy backfill)", "created_at": now, "updated_at": now},
    )
    return new_id


def upgrade() -> None:
    conn = op.get_bind()

    for tbl in _NEW_CLIENT_ID_TABLES:
        op.add_column(tbl, sa.Column("client_id", _UUID_TYPE, nullable=True))

    anchor = _resolve_anchor_client(conn)
    if anchor is not None:
        for tbl in _NEW_CLIENT_ID_TABLES:
            conn.execute(
                sa.text(f"UPDATE {tbl} SET client_id = :cid WHERE client_id IS NULL"),
                {"cid": anchor},
            )
        for tbl, parent, fk in _EXISTING_CLIENT_ID_TABLES:
            conn.execute(
                sa.text(
                    f"UPDATE {tbl} SET client_id = ("
                    f"SELECT client_id FROM {parent} WHERE {parent}.id = {tbl}.{fk}"
                    f") WHERE client_id IS NULL"
                )
            )

    for tbl in _NEW_CLIENT_ID_TABLES:
        with op.batch_alter_table(tbl) as batch:
            batch.alter_column("client_id", existing_type=_UUID_TYPE, nullable=False)
            batch.create_foreign_key(
                f"fk_{tbl}_client_id",
                "client",
                ["client_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        op.create_index(f"ix_{tbl}_client_id", tbl, ["client_id"])

    for tbl, _parent, _fk in _EXISTING_CLIENT_ID_TABLES:
        with op.batch_alter_table(tbl) as batch:
            batch.alter_column("client_id", existing_type=_UUID_TYPE, nullable=False)
        op.create_index(f"ix_{tbl}_client_id", tbl, ["client_id"])

    # User.client_id stays nullable (platform admin/reviewer = NULL); index it
    # since per-tenant filtering on users will be hot.
    op.create_index("ix_users_client_id", "users", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_users_client_id", table_name="users")

    for tbl, _parent, _fk in _EXISTING_CLIENT_ID_TABLES:
        op.drop_index(f"ix_{tbl}_client_id", table_name=tbl)
        with op.batch_alter_table(tbl) as batch:
            batch.alter_column("client_id", existing_type=_UUID_TYPE, nullable=True)

    for tbl in _NEW_CLIENT_ID_TABLES:
        op.drop_index(f"ix_{tbl}_client_id", table_name=tbl)
        with op.batch_alter_table(tbl) as batch:
            batch.drop_constraint(f"fk_{tbl}_client_id", type_="foreignkey")
        op.drop_column(tbl, "client_id")
