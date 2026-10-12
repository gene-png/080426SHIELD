"""Evidence intake fields, the evidence link table, and `evidence_basis` (N5, for #1071).

Revision ID: 0068
Revises: 0067

The design note rev 4, sections 5 and 10.1 (schema approved by the advisor,
#736 6115899208 and 6116092992). One migration covers all three:

- `artifacts` gains `description`, `doc_status`, `doc_status_set_by` and
  `doc_status_set_at`, all nullable. A NULL `doc_status` reads as `not_sure`.
- New table `evidence_links`: one client file linked to one assessment row.
  Uniqueness is two partial unique indexes (untiered rows on four columns,
  tiered rows on five), because `tier` is NULL on every ZT and ATT&CK link and
  a plain UNIQUE treats NULLs as distinct. A CHECK holds `tier` to CSF rows.
  `assessment_id` has no FK: three assessment tables are three referents.
- `csf_dimension_scores.evidence_basis` (`MANUAL_FROZEN` | `LINKED`), nullable.

Enum columns follow the `ai_runs` convention (`native_enum=False`, no
`values_callable`): plain VARCHARs holding the member NAME.

## Blast radius

Additive only. No existing row changes and NOTHING IS BACKFILLED:
`evidence_basis` lands NULL on every row, because the Q9 grace rule that
decides it is still Gene's call, and nothing reads it for scoring. The
existing `evidence_artifact_id` columns are untouched.

The downgrade REFUSES while any row records something this migration added: an
evidence link, an artifact description or document status, or an
`evidence_basis`. Dropping them would delete what a client said about a file and
the links a consultant confirmed, without a trace.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import conv

revision: str = "0068"
down_revision: str | Sequence[str] | None = "0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UNTIERED = "tier IS NULL"
_TIERED = "tier IS NOT NULL"

_RECORDED = {
    "evidence links": "SELECT COUNT(*) FROM evidence_links",
    "artifacts with a description or document status": (
        "SELECT COUNT(*) FROM artifacts WHERE description IS NOT NULL "
        "OR doc_status IS NOT NULL OR doc_status_set_by IS NOT NULL "
        "OR doc_status_set_at IS NOT NULL"
    ),
    "Working Profile rows with an evidence basis": (
        "SELECT COUNT(*) FROM csf_dimension_scores WHERE evidence_basis IS NOT NULL"
    ),
}


def _uuid(name: str, *, nullable: bool = True, primary_key: bool = False) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
        primary_key=primary_key,
        nullable=nullable,
    )


def _fk(column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    referred = target.split(".")[0]
    return sa.ForeignKeyConstraint(
        [column],
        [target],
        name=conv(f"fk_evidence_links_{column}_{referred}"),
        ondelete=ondelete,
    )


def upgrade() -> None:
    with op.batch_alter_table("artifacts") as batch:
        batch.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch.add_column(sa.Column("doc_status", sa.String(16), nullable=True))
        batch.add_column(
            sa.Column(
                "doc_status_set_by",
                postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("doc_status_set_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            conv("fk_artifacts_doc_status_set_by_users"),
            "users",
            ["doc_status_set_by"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("csf_dimension_scores") as batch:
        batch.add_column(sa.Column("evidence_basis", sa.String(16), nullable=True))

    op.create_table(
        "evidence_links",
        _uuid("id", primary_key=True, nullable=False),
        _uuid("client_id", nullable=False),
        _uuid("artifact_id", nullable=False),
        _uuid("assessment_id", nullable=False),
        sa.Column("target_kind", sa.String(32), nullable=False),
        sa.Column("target_code", sa.String(32), nullable=False),
        sa.Column("tier", sa.String(16)),
        sa.Column("supports", postgresql.JSONB().with_variant(sa.JSON, "sqlite"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        _uuid("suggested_by_run_id"),
        sa.Column("quote", sa.Text),
        _uuid("confirmed_by"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        _fk("client_id", "client.id", "CASCADE"),
        _fk("artifact_id", "artifacts.id", "CASCADE"),
        _fk("suggested_by_run_id", "ai_runs.id", "SET NULL"),
        _fk("confirmed_by", "users.id", "SET NULL"),
        sa.CheckConstraint(
            "(target_kind = 'CSF_ROW' AND tier IS NOT NULL) "
            "OR (target_kind <> 'CSF_ROW' AND tier IS NULL)",
            name=conv("ck_evidence_links_tier_iff_csf_row"),
        ),
    )
    op.create_index("ix_evidence_links_client_id", "evidence_links", ["client_id"])
    op.create_index("ix_evidence_links_artifact_id", "evidence_links", ["artifact_id"])
    op.create_index("ix_evidence_links_assessment_id", "evidence_links", ["assessment_id"])
    op.create_index(
        "uq_evidence_links_untiered",
        "evidence_links",
        ["artifact_id", "assessment_id", "target_kind", "target_code"],
        unique=True,
        sqlite_where=sa.text(_UNTIERED),
        postgresql_where=sa.text(_UNTIERED),
    )
    op.create_index(
        "uq_evidence_links_tiered",
        "evidence_links",
        ["artifact_id", "assessment_id", "target_kind", "target_code", "tier"],
        unique=True,
        sqlite_where=sa.text(_TIERED),
        postgresql_where=sa.text(_TIERED),
    )


def downgrade() -> None:
    bind = op.get_bind()
    counts = {what: bind.execute(sa.text(query)).scalar_one() for what, query in _RECORDED.items()}
    held = {what: n for what, n in counts.items() if n}
    if held:
        listed = ", ".join(f"{n} {what}" for what, n in held.items())
        raise RuntimeError(
            f"Refusing to downgrade 0068: {listed}. Dropping them would delete what "
            "a client said about a file and the links a consultant confirmed, "
            "without a trace."
        )
    op.drop_index("uq_evidence_links_tiered", table_name="evidence_links")
    op.drop_index("uq_evidence_links_untiered", table_name="evidence_links")
    op.drop_index("ix_evidence_links_assessment_id", table_name="evidence_links")
    op.drop_index("ix_evidence_links_artifact_id", table_name="evidence_links")
    op.drop_index("ix_evidence_links_client_id", table_name="evidence_links")
    op.drop_table("evidence_links")
    with op.batch_alter_table("csf_dimension_scores") as batch:
        batch.drop_column("evidence_basis")
    with op.batch_alter_table("artifacts") as batch:
        batch.drop_constraint("fk_artifacts_doc_status_set_by_users", type_="foreignkey")
        batch.drop_column("doc_status_set_at")
        batch.drop_column("doc_status_set_by")
        batch.drop_column("doc_status")
        batch.drop_column("description")
