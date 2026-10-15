"""One draft per service, and the revision link (#1120, Option A).

Revision ID: 0073
Revises: 0070

The design note rev 10, sections 2, 3 and 6, ruled by the advisor
(#736 6136101129, item 8). The number 0073 is the advisor's; `down_revision`
is main's head (0070 since #1077 merged) and is re-pointed onto main's head
at merge (single-head rule).

For each of `attack_assessments`, `csf_assessments`, `zt_assessments` and
`capability_lists`:

- `revision_of`: a nullable self-FK, `ON DELETE SET NULL`. It names the record a
  "Start a revision" copied from. NULL on every existing row; nothing clears it.
- `uq_<table>_one_draft`: a UNIQUE index on `(service_id)` WHERE
  `status = 'DRAFT'`, with BOTH dialect clauses. One clause alone becomes a
  plain UNIQUE index on the other dialect, which would refuse a second record
  EVER (the same reason `uq_ai_runs_one_running`, 0057, carries both).
  `'DRAFT'` is the member NAME, which `native_enum=False` stores.
- `status`'s `server_default` becomes `'DRAFT'`. Migrations 0006, 0009, 0010 and
  0011 created it as lowercase `'draft'`: a status-omitted INSERT stored a value
  the ORM cannot load (`LookupError`) and the index above would not count.
  No writer omits `status` today; this closes the gap for the next one.

## Blast radius, measured before choosing

Schema only: no existing row is changed or backfilled (demo data only,
#736 6130059800). `seed_demo.py` seeds no DRAFT record, and no route can put
two drafts in one service (`create_assessment` reuses an open draft; Tech Debt's
extract POST returns or refuses one, and its job re-checks).

## Upgrading over two drafts in one service

The upgrade REFUSES, before changing anything, when any service already holds
more than one DRAFT in one of the four tables, and names the table and the
service ids. The index creation would fail on that data anyway; this says why
in words. The remedy on a demo database is `docker compose down -v` and a
reseed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0073"
down_revision: str | Sequence[str] | None = "0070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The four record tables (#1120 rev 10, section 6).
TABLES: tuple[str, ...] = (
    "attack_assessments",
    "csf_assessments",
    "zt_assessments",
    "capability_lists",
)

_DRAFT = sa.text("status = 'DRAFT'")


def _duplicate_drafts(bind: sa.engine.Connection, table: str) -> list[str]:
    """Service ids holding more than one DRAFT in `table`. Matched
    case-insensitively, so a lowercase `'draft'` row written through the old
    server default is counted too."""
    rows = bind.execute(
        sa.text(
            f"SELECT service_id FROM {table} WHERE UPPER(status) = 'DRAFT' "  # nosec B608
            "GROUP BY service_id HAVING COUNT(*) > 1"
        )
    ).all()
    return sorted(str(r[0]) for r in rows)


def upgrade() -> None:
    bind = op.get_bind()
    found = {t: _duplicate_drafts(bind, t) for t in TABLES}
    found = {t: ids for t, ids in found.items() if ids}
    if found:
        listed = "; ".join(f"{t}: {', '.join(ids)}" for t, ids in sorted(found.items()))
        raise RuntimeError(
            "0073 refuses to upgrade: these services already hold more than one DRAFT, "
            f"so the one-draft index cannot be created. {listed}. Nothing was changed."
        )
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column(
                    "revision_of",
                    postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
                    nullable=True,
                )
            )
            batch.create_foreign_key(
                f"fk_{table}_revision_of",
                table,
                ["revision_of"],
                ["id"],
                ondelete="SET NULL",
            )
            batch.alter_column("status", server_default="DRAFT")
        op.create_index(
            f"uq_{table}_one_draft",
            table,
            ["service_id"],
            unique=True,
            sqlite_where=_DRAFT,
            postgresql_where=_DRAFT,
        )
    print("[0073] one-draft index and revision_of added to: " + ", ".join(TABLES))


def downgrade() -> None:
    for table in TABLES:
        op.drop_index(f"uq_{table}_one_draft", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.alter_column("status", server_default="draft")
            batch.drop_constraint(f"fk_{table}_revision_of", type_="foreignkey")
            batch.drop_column("revision_of")
