"""A Run-AI is a row of its own, and runs in the background (#645).

Run-AI was one HTTP request. ATT&CK's mitre_map makes ~26 provider calls per
run and outlasts the request timeout, so the browser gave up while the server
went on spending. A run is now started by a POST that returns 202 and finished
by a background job. `ai_runs` is what the two share and what the workspace
polls; `llm_calls` keeps one row per provider call and now says which run it
belonged to.

- `ai_runs`: one row per run. `status` follows the `llm_calls` convention
  (`native_enum=False`, no `values_callable`), so the stored value is the
  member NAME (`RUNNING`). `result` holds every disclosure the workspace renders
  about the run, so it survives a reload (#271). `subject_id` is what the run
  works on (the assessment, or the inventory document of a Tech Debt
  extract): a second POST joins a run only when it names the same one.
- `uq_ai_runs_one_running`: at most one RUNNING run per service and purpose. A
  PARTIAL unique index, declared for both dialects: CI runs SQLite only, so the
  Postgres clause is exercised by nothing in CI. Without `postgresql_where`
  Postgres would build a plain unique index and refuse a second run ever.
- `llm_calls.ai_run_id`: nullable, SET NULL. NULL for calls made outside a run
  and for every row written before this migration.

## Blast radius

Additive only: one new table, one nullable column. No existing row changes and
nothing is backfilled. A run that was in flight when this migration ran was a
synchronous request and left no `ai_runs` row, which is the truth.

SQLite-safe via `batch_alter_table` (core principle 6).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0057"
down_revision: str | Sequence[str] | None = "0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, nullable: bool = True, primary_key: bool = False) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
        primary_key=primary_key,
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "ai_runs",
        _uuid("id", primary_key=True, nullable=False),
        _uuid("client_id", nullable=False),
        _uuid("service_id", nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        _uuid("subject_id", nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("boot_id", sa.String(36), nullable=False),
        sa.Column("batches_total", sa.Integer),
        sa.Column("batches_failed", sa.Integer),
        sa.Column("applied_count", sa.Integer),
        sa.Column("result", postgresql.JSONB().with_variant(sa.JSON, "sqlite")),
        sa.Column("error_reason", sa.String(64)),
        sa.Column("error_message", sa.Text),
        sa.Column("charged_likely", sa.Boolean),
        _uuid("requested_by", nullable=False),
        sa.Column("correlation_id", sa.String(128)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["client_id"], ["client.id"], name="fk_ai_runs_client_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["service_id"], ["services.id"], name="fk_ai_runs_service_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name="fk_ai_runs_requested_by_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_ai_runs_service_purpose", "ai_runs", ["service_id", "purpose"])
    op.create_index(
        "uq_ai_runs_one_running",
        "ai_runs",
        ["service_id", "purpose"],
        unique=True,
        sqlite_where=sa.text("status = 'RUNNING'"),
        postgresql_where=sa.text("status = 'RUNNING'"),
    )
    with op.batch_alter_table("llm_calls") as batch:
        batch.add_column(
            sa.Column(
                "ai_run_id",
                postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
                nullable=True,
            )
        )
        batch.create_foreign_key(
            "fk_llm_calls_ai_run_id", "ai_runs", ["ai_run_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("llm_calls") as batch:
        batch.drop_constraint("fk_llm_calls_ai_run_id", type_="foreignkey")
        batch.drop_column("ai_run_id")
    op.drop_index("uq_ai_runs_one_running", table_name="ai_runs")
    op.drop_index("ix_ai_runs_service_purpose", table_name="ai_runs")
    op.drop_table("ai_runs")
