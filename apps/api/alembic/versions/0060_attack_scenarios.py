"""The ATT&CK what-if: a scenario and its re-assessed techniques (#802 slice A).

- `attack_scenarios`: one row per what-if. It pins its base (the confirmed
  assessment it is compared with, with that assessment's version, catalog
  version and status rules at creation), the confirmed change list, the
  techniques the change affects, its state, its run, and what the run
  disclosed: drops by reason, techniques no batch re-assessed, how many
  affected techniques would score HIGHER than in the base, and the offered
  tools added to the client's list since the base was approved (NULL when
  that could not be checked). `state` follows the
  `ai_runs` convention (`native_enum=False`, no `values_callable`), so the
  stored value is the member NAME (`DRAFT`).
- `attack_scenario_rows`: one row per affected technique, its three tool
  lists under the scenario and the accepted AI rows behind them. CASCADE on
  the scenario only; every other foreign key RESTRICTs, so a scenario never
  disappears because something it points at did.

## Blast radius

Additive only: two new tables. No existing row changes and nothing is
backfilled. Nothing in the real assessment, a deliverable or the client's view
reads either table.

The downgrade REFUSES while any scenario exists: dropping the table would erase
a change list an admin confirmed and the AI run it paid for.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0060"
down_revision: str | Sequence[str] | None = "0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, nullable: bool = True, primary_key: bool = False) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
        primary_key=primary_key,
        nullable=nullable,
    )


def _json(name: str, *, nullable: bool = True) -> sa.Column:
    return sa.Column(name, postgresql.JSONB().with_variant(sa.JSON, "sqlite"), nullable=nullable)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _restrict(column: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [target], name=f"fk_attack_scenarios_{column}", ondelete="RESTRICT"
    )


def upgrade() -> None:
    op.create_table(
        "attack_scenarios",
        _uuid("id", primary_key=True, nullable=False),
        _uuid("client_id", nullable=False),
        _uuid("service_id", nullable=False),
        _uuid("base_assessment_id", nullable=False),
        sa.Column("base_version", sa.Integer, nullable=False),
        sa.Column("base_catalog_version", sa.String(16)),
        sa.Column("base_status_rules", sa.Integer, nullable=False),
        _json("change_list", nullable=False),
        _json("affected_codes", nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        _uuid("ai_run_id"),
        _json("dropped"),
        _json("not_reassessed"),
        sa.Column("scored_higher", sa.Integer),
        _json("tools_added_since_base"),
        _uuid("created_by", nullable=False),
        *_timestamps(),
        _restrict("client_id", "client.id"),
        _restrict("service_id", "services.id"),
        _restrict("base_assessment_id", "attack_assessments.id"),
        _restrict("ai_run_id", "ai_runs.id"),
        _restrict("created_by", "users.id"),
    )
    op.create_index("ix_attack_scenarios_client_id", "attack_scenarios", ["client_id"])
    op.create_index("ix_attack_scenarios_service_id", "attack_scenarios", ["service_id"])

    op.create_table(
        "attack_scenario_rows",
        _uuid("id", primary_key=True, nullable=False),
        _uuid("scenario_id", nullable=False),
        sa.Column("technique_code", sa.String(32), nullable=False),
        _json("detection_tools", nullable=False),
        _json("prevention_tools", nullable=False),
        _json("response_tools", nullable=False),
        _json("ai_rows", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["attack_scenarios.id"],
            name="fk_attack_scenario_rows_scenario_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "scenario_id", "technique_code", name="uq_attack_scenario_rows_scenario_technique"
        ),
    )
    op.create_index("ix_attack_scenario_rows_scenario_id", "attack_scenario_rows", ["scenario_id"])


def downgrade() -> None:
    bind = op.get_bind()
    scenarios = bind.execute(sa.text("SELECT COUNT(*) FROM attack_scenarios")).scalar_one()
    if scenarios:
        raise RuntimeError(
            f"Refusing to downgrade 0060: {scenarios} ATT&CK what-if scenario(s) exist. "
            "Dropping the table would erase change lists an admin confirmed and the "
            "AI runs they paid for."
        )
    op.drop_index("ix_attack_scenario_rows_scenario_id", table_name="attack_scenario_rows")
    op.drop_table("attack_scenario_rows")
    op.drop_index("ix_attack_scenarios_service_id", table_name="attack_scenarios")
    op.drop_index("ix_attack_scenarios_client_id", table_name="attack_scenarios")
    op.drop_table("attack_scenarios")
