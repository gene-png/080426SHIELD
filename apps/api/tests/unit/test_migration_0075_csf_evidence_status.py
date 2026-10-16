"""Migration 0075: `csf_dimension_scores.has_evidence` becomes the three-valued
`evidence_status` (Gene, #736 6201691989 item 2: "existing true reads as
Evidence on file, false as Neither").

The stored spellings are typed here from that ruling and the migration's
docstring, never imported from the code under test. Rows are written by raw
SQL in the shape every pre-0075 row has.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

pytestmark = pytest.mark.unit

API_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-10-15 00:00:00"

_TEMPLATE: dict[str, Path] = {}


def _cfg(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture(autouse=True)
def _template_0072(tmp_path_factory) -> None:
    """One database migrated to 0072, built once and copied per test."""
    if "0072" not in _TEMPLATE:
        path = tmp_path_factory.mktemp("tpl0075") / "0072.db"
        command.upgrade(_cfg(f"sqlite:///{path}"), "0072")
        _TEMPLATE["0072"] = path


def _at_0072(tmp_path) -> tuple[str, sa.Engine]:
    target = tmp_path / "db.sqlite"
    shutil.copyfile(_TEMPLATE["0072"], target)
    url = f"sqlite:///{target}"
    return url, sa.create_engine(url, future=True)


def _columns(engine: sa.Engine) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns("csf_dimension_scores")}


def _world(engine: sa.Engine, *, rollup_rules: int | None = None) -> dict[str, str]:
    """A client, a user, a service, an assessment and two Working Profile
    rows: one with `has_evidence` true, one false."""
    ids = {k: str(uuid.uuid4()) for k in ("client", "user", "service", "assessment")}
    ids["ticked"] = str(uuid.uuid4())
    ids["unticked"] = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO client (id, created_at, updated_at) VALUES (:id, :n, :n)"),
            {"id": ids["client"], "n": NOW},
        )
        conn.execute(
            sa.text(
                "INSERT INTO users (id, email, password_hash, role, timezone, is_active, "
                "mfa_enrolled, failed_login_count, created_at, updated_at) VALUES "
                "(:id, :e, 'x', 'CLIENT', 'UTC', 1, 0, 0, :n, :n)"
            ),
            {"id": ids["user"], "e": f"{ids['user']}@atlas.example", "n": NOW},
        )
        conn.execute(
            sa.text(
                "INSERT INTO services (id, kind, status, title, opened_by, client_id, "
                "created_at, updated_at) VALUES "
                "(:id, 'NIST_CSF', 'DRAFT', 'CSF', :u, :c, :n, :n)"
            ),
            {"id": ids["service"], "u": ids["user"], "c": ids["client"], "n": NOW},
        )
        conn.execute(
            sa.text(
                "INSERT INTO csf_assessments (id, service_id, client_id, version, status, "
                "documents_stale, rollup_rules, created_at, updated_at) VALUES "
                "(:id, :s, :c, 1, 'DRAFT', 0, :r, :n, :n)"
            ),
            {
                "id": ids["assessment"],
                "s": ids["service"],
                "c": ids["client"],
                "r": rollup_rules,
                "n": NOW,
            },
        )
        for key, code, ticked in (("ticked", "GV.OC-01", 1), ("unticked", "GV.OC-02", 0)):
            conn.execute(
                sa.text(
                    "INSERT INTO csf_dimension_scores (id, assessment_id, client_id, tier, "
                    "subcategory_code, governance, policy, implementation, monitoring, "
                    "improvement, in_scope, has_evidence, locked, created_at, updated_at) "
                    "VALUES (:id, :a, :c, 'high', :code, 2, 2, 2, 2, 2, 1, :t, 0, :n, :n)"
                ),
                {
                    "id": ids[key],
                    "a": ids["assessment"],
                    "c": ids["client"],
                    "code": code,
                    "t": ticked,
                    "n": NOW,
                },
            )
    return ids


def _status(engine: sa.Engine, row_id: str) -> str:
    with engine.connect() as conn:
        return conn.execute(
            sa.text("SELECT evidence_status FROM csf_dimension_scores WHERE id = :id"),
            {"id": row_id},
        ).scalar_one()


def test_upgrade_maps_true_to_on_file_and_false_to_neither(tmp_path) -> None:
    url, engine = _at_0072(tmp_path)
    ids = _world(engine)
    assert "has_evidence" in _columns(engine)  # positive first: the old shape
    command.upgrade(_cfg(url), "0075")
    cols = _columns(engine)
    assert "evidence_status" in cols and "has_evidence" not in cols, cols
    assert _status(engine, ids["ticked"]) == "on_file"
    assert _status(engine, ids["unticked"]) == "neither"


def test_a_row_inserted_without_the_column_reads_neither(tmp_path) -> None:
    """The server default: a writer that names no evidence column (as every
    pre-0075 writer did when false) stores `neither`, never NULL."""
    url, engine = _at_0072(tmp_path)
    ids = _world(engine)
    command.upgrade(_cfg(url), "0075")
    new_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO csf_dimension_scores (id, assessment_id, client_id, tier, "
                "subcategory_code, governance, policy, implementation, monitoring, "
                "improvement, in_scope, locked, created_at, updated_at) VALUES "
                "(:id, :a, :c, 'low', 'GV.OC-03', 0, 0, 0, 0, 0, 1, 0, :n, :n)"
            ),
            {"id": new_id, "a": ids["assessment"], "c": ids["client"], "n": NOW},
        )
    assert _status(engine, new_id) == "neither"


def test_downgrade_round_trips_the_two_old_values(tmp_path) -> None:
    url, engine = _at_0072(tmp_path)
    ids = _world(engine)
    command.upgrade(_cfg(url), "0075")
    command.downgrade(_cfg(url), "0072")
    cols = _columns(engine)
    assert "has_evidence" in cols and "evidence_status" not in cols, cols
    with engine.connect() as conn:
        got = dict(conn.execute(sa.text("SELECT id, has_evidence FROM csf_dimension_scores")).all())
    assert got == {ids["ticked"]: 1, ids["unticked"]: 0}, got


def test_downgrade_refuses_to_erase_confirmed_in_discussion(tmp_path) -> None:
    url, engine = _at_0072(tmp_path)
    ids = _world(engine)
    command.upgrade(_cfg(url), "0075")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE csf_dimension_scores SET evidence_status = 'confirmed_in_discussion' "
                "WHERE id = :id"
            ),
            {"id": ids["unticked"]},
        )
    with pytest.raises(RuntimeError, match="1 CSF Working Profile row"):
        command.downgrade(_cfg(url), "0072")
    assert _status(engine, ids["unticked"]) == "confirmed_in_discussion"


def test_downgrade_refuses_an_assessment_approved_without_the_cap(tmp_path) -> None:
    url, engine = _at_0072(tmp_path)
    _world(engine, rollup_rules=3)
    command.upgrade(_cfg(url), "0075")
    with pytest.raises(RuntimeError, match="rollup_rules = 3"):
        command.downgrade(_cfg(url), "0072")
    assert "evidence_status" in _columns(engine)
