"""Migration 0060: the ATT&CK what-if's two tables (#802 slice A).

Additive: two new tables, no existing row touched. The downgrade REFUSES while
any scenario exists, because dropping the table would erase a change list an
admin confirmed and the AI run it paid for.

Rows are written by raw SQL: this is the world the migration meets, not the
app's writers.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def _cfg(url: str) -> Config:
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _tables(engine: sa.Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def _insert_scenario(engine: sa.Engine) -> None:
    now = "2026-10-03 00:00:00"
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO attack_scenarios (id, client_id, service_id, base_assessment_id, "
                "base_version, base_catalog_version, base_status_rules, change_list, "
                "affected_codes, state, created_by, created_at, updated_at) VALUES "
                "(:id, :c, :s, :a, 3, '17.1', 2, :cl, :ac, 'DRAFT', :u, :now, :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "c": str(uuid.uuid4()),
                "s": str(uuid.uuid4()),
                "a": str(uuid.uuid4()),
                "cl": '{"removed": ["Tool A"], "added": []}',
                "ac": '["T1003"]',
                "u": str(uuid.uuid4()),
                "now": now,
            },
        )


@pytest.mark.unit
def test_0060_creates_both_tables_and_drops_them_when_empty(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'm0060.db'}"
    command.upgrade(_cfg(url), "0059")
    engine = sa.create_engine(url, future=True)
    assert not {"attack_scenarios", "attack_scenario_rows"} & _tables(engine)

    command.upgrade(_cfg(url), "0060")
    assert {"attack_scenarios", "attack_scenario_rows"} <= _tables(engine)
    columns = {c["name"] for c in sa.inspect(engine).get_columns("attack_scenarios")}
    assert {
        "base_assessment_id",
        "base_version",
        "base_catalog_version",
        "base_status_rules",
        "change_list",
        "affected_codes",
        "state",
        "ai_run_id",
        "dropped",
        "not_reassessed",
        "scored_higher",
        "tools_added_since_base",
        "created_by",
    } <= columns

    command.downgrade(_cfg(url), "0059")
    assert not {"attack_scenarios", "attack_scenario_rows"} & _tables(engine)
    command.upgrade(_cfg(url), "0060")
    assert {"attack_scenarios", "attack_scenario_rows"} <= _tables(engine)


@pytest.mark.unit
def test_0060_cascades_on_scenario_rows_only(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'm0060-fk.db'}"
    command.upgrade(_cfg(url), "0060")
    inspector = sa.inspect(sa.create_engine(url, future=True))

    row_fks = {
        fk["referred_table"]: fk["options"].get("ondelete")
        for fk in inspector.get_foreign_keys("attack_scenario_rows")
    }
    assert row_fks == {"attack_scenarios": "CASCADE"}

    scenario_fks = {
        fk["referred_table"]: fk["options"].get("ondelete")
        for fk in inspector.get_foreign_keys("attack_scenarios")
    }
    assert set(scenario_fks) == {"client", "services", "attack_assessments", "ai_runs", "users"}
    assert "CASCADE" not in scenario_fks.values(), scenario_fks


@pytest.mark.unit
def test_0060_one_row_per_technique_per_scenario(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'm0060-uq.db'}"
    command.upgrade(_cfg(url), "0060")
    engine = sa.create_engine(url, future=True)
    sid = str(uuid.uuid4())
    insert = sa.text(
        "INSERT INTO attack_scenario_rows (id, scenario_id, technique_code, detection_tools, "
        "prevention_tools, response_tools, ai_rows, created_at, updated_at) VALUES "
        "(:id, :sid, 'T1003', '[]', '[]', '[]', '[]', :now, :now)"
    )
    now = "2026-10-03 00:00:00"
    with engine.begin() as conn:
        conn.execute(insert, {"id": str(uuid.uuid4()), "sid": sid, "now": now})
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        conn.execute(insert, {"id": str(uuid.uuid4()), "sid": sid, "now": now})


@pytest.mark.unit
def test_0060_downgrade_refuses_while_a_scenario_exists(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'm0060-refuse.db'}"
    command.upgrade(_cfg(url), "0060")
    engine = sa.create_engine(url, future=True)
    _insert_scenario(engine)

    with pytest.raises(RuntimeError, match="Refusing to downgrade 0060: 1 ATT&CK what-if"):
        command.downgrade(_cfg(url), "0059")
    assert {"attack_scenarios", "attack_scenario_rows"} <= _tables(engine)
