"""Findings reports, recommendations and integration runs (N4, for #1063).

Revision ID: 0067
Revises: 0066

The design note rev 4, section 5 (schema approved by the advisor, #736
6115899208 and 6116092992):

- `findings_reports` (output A): one row per generated client findings report,
  pinned to its deliverable. `status` DRAFT | APPROVED.
- `integration_runs`: a client-level snapshot of the integration layer's
  inputs, crosswalks and code-computed findings (section 12).
- `recommendations` (output B), one row per item, admin only. `scope` is
  SERVICE or CLIENT; two CHECKs hold a client-scope row to no service and no
  deliverable, and a service-scope row to a service. A third CHECK holds
  `origin` to `ai` | `edited` | `consultant` (ruling #736 6128447366, (d)).
  `effect_status` is NOT NULL with a server default of `'SUGGESTED'`: missing
  data is unconfirmed, never NULL.
  No artifact column.

Enum columns follow the `ai_runs` convention (`native_enum=False`, no
`values_callable`): plain VARCHARs holding the member NAME, so the CHECKs are
written against `'CLIENT'` and `'SERVICE'`.

## Blast radius

Additive only: three new tables. No existing row changes and nothing is
backfilled. Nothing reads any of the three yet.

The downgrade REFUSES while any of the three tables holds a row: dropping them
would erase reports a consultant reviewed, recommendations they accepted, and
the snapshots those were computed from.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import conv

revision: str = "0067"
down_revision: str | Sequence[str] | None = "0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COUNTS = {
    "recommendations": "SELECT COUNT(*) FROM recommendations",
    "integration_runs": "SELECT COUNT(*) FROM integration_runs",
    "findings_reports": "SELECT COUNT(*) FROM findings_reports",
}


def _uuid(name: str, *, nullable: bool = True, primary_key: bool = False) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
        primary_key=primary_key,
        nullable=nullable,
    )


def _json(name: str) -> sa.Column:
    return sa.Column(name, postgresql.JSONB().with_variant(sa.JSON, "sqlite"), nullable=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    referred = target.split(".")[0]
    return sa.ForeignKeyConstraint(
        [column], [target], name=conv(f"fk_{table}_{column}_{referred}"), ondelete=ondelete
    )


def upgrade() -> None:
    t = "findings_reports"
    op.create_table(
        t,
        _uuid("id", primary_key=True, nullable=False),
        _uuid("service_id", nullable=False),
        _uuid("deliverable_id", nullable=False),
        _json("sections"),
        _json("cross_facts"),
        sa.Column("prompt_version", sa.String(64)),
        _uuid("ai_run_id"),
        sa.Column("status", sa.String(16), nullable=False),
        _uuid("approved_by"),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        _uuid("pdf_artifact_id"),
        _uuid("docx_artifact_id"),
        *_timestamps(),
        _fk(t, "service_id", "services.id", "CASCADE"),
        _fk(t, "deliverable_id", "deliverables.id", "CASCADE"),
        _fk(t, "ai_run_id", "ai_runs.id", "SET NULL"),
        _fk(t, "approved_by", "users.id", "SET NULL"),
        _fk(t, "pdf_artifact_id", "artifacts.id", "SET NULL"),
        _fk(t, "docx_artifact_id", "artifacts.id", "SET NULL"),
    )
    op.create_index("ix_findings_reports_service_id", t, ["service_id"])
    op.create_index("ix_findings_reports_deliverable_id", t, ["deliverable_id"])

    t = "integration_runs"
    op.create_table(
        t,
        _uuid("id", primary_key=True, nullable=False),
        _uuid("client_id", nullable=False),
        _uuid("created_by"),
        _json("inputs"),
        _json("crosswalks"),
        _json("findings"),
        _uuid("ai_run_id"),
        *_timestamps(),
        _fk(t, "client_id", "client.id", "CASCADE"),
        _fk(t, "created_by", "users.id", "SET NULL"),
        _fk(t, "ai_run_id", "ai_runs.id", "SET NULL"),
    )
    op.create_index("ix_integration_runs_client_id", t, ["client_id"])

    t = "recommendations"
    op.create_table(
        t,
        _uuid("id", primary_key=True, nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        _uuid("client_id", nullable=False),
        _uuid("service_id"),
        _uuid("deliverable_id"),
        _uuid("integration_run_id"),
        sa.Column("finding_id", sa.String(64)),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("rationale", sa.Text),
        sa.Column("tool", sa.String(255)),
        sa.Column("axis", sa.String(16)),
        sa.Column("configuration", sa.Text),
        _json("expected_effect"),
        sa.Column(
            "effect_status", sa.String(16), nullable=False, server_default=sa.text("'SUGGESTED'")
        ),
        _json("priority_inputs"),
        sa.Column("priority_rank", sa.Integer),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        _uuid("reviewed_by"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        _uuid("ai_run_id"),
        *_timestamps(),
        _fk(t, "client_id", "client.id", "CASCADE"),
        _fk(t, "service_id", "services.id", "CASCADE"),
        _fk(t, "deliverable_id", "deliverables.id", "CASCADE"),
        _fk(t, "integration_run_id", "integration_runs.id", "SET NULL"),
        _fk(t, "reviewed_by", "users.id", "SET NULL"),
        _fk(t, "ai_run_id", "ai_runs.id", "SET NULL"),
        sa.CheckConstraint(
            "scope <> 'CLIENT' OR (service_id IS NULL AND deliverable_id IS NULL)",
            name=conv("ck_recommendations_client_scope_has_no_service"),
        ),
        sa.CheckConstraint(
            "scope <> 'SERVICE' OR service_id IS NOT NULL",
            name=conv("ck_recommendations_service_scope_has_service"),
        ),
        sa.CheckConstraint(
            "origin IN ('ai', 'edited', 'consultant')",
            name=conv("ck_recommendations_origin_vocabulary"),
        ),
    )
    op.create_index("ix_recommendations_client_id", t, ["client_id"])
    op.create_index("ix_recommendations_service_id", t, ["service_id"])


def downgrade() -> None:
    bind = op.get_bind()
    counts = {table: bind.execute(sa.text(query)).scalar_one() for table, query in _COUNTS.items()}
    held = {table: n for table, n in counts.items() if n}
    if held:
        listed = ", ".join(f"{n} in {table}" for table, n in held.items())
        raise RuntimeError(
            f"Refusing to downgrade 0067: rows exist ({listed}). Dropping the tables "
            "would erase reviewed reports, accepted recommendations and the snapshots "
            "they were computed from."
        )
    op.drop_index("ix_recommendations_service_id", table_name="recommendations")
    op.drop_index("ix_recommendations_client_id", table_name="recommendations")
    op.drop_table("recommendations")
    op.drop_index("ix_integration_runs_client_id", table_name="integration_runs")
    op.drop_table("integration_runs")
    op.drop_index("ix_findings_reports_deliverable_id", table_name="findings_reports")
    op.drop_index("ix_findings_reports_service_id", table_name="findings_reports")
    op.drop_table("findings_reports")
