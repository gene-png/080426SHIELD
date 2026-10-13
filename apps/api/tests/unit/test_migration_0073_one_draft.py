"""Migration 0073 (#1120, Option A): one DRAFT per service, in the database.

Stored bytes, read and written with raw SQL after `alembic upgrade`, never
through the ORM, because the claim is about what the database refuses:

* two `'DRAFT'` rows for one service are refused (`uq_<table>_one_draft`), in
  each of the four tables, while a DRAFT beside an APPROVED row is accepted;
* a status-OMITTED insert stores `'DRAFT'` (the corrected `server_default`), so
  two of them are refused too, and one loads through the ORM as DRAFT;
* the upgrade REFUSES over a database that already holds two drafts for one
  service, names the table and service, and changes nothing.

The value spelling `'draft'` matches nothing in the index predicate, so a
migration written with it would leave every case here red.
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
NOW = "2026-10-13 00:00:00"
TABLES = ("attack_assessments", "csf_assessments", "zt_assessments", "capability_lists")

_TEMPLATE: dict[str, Path] = {}


def _cfg(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture(autouse=True)
def _template_0070(tmp_path_factory) -> None:
    if "0070" not in _TEMPLATE:
        path = tmp_path_factory.mktemp("tpl0073") / "0070.db"
        command.upgrade(_cfg(f"sqlite:///{path}"), "0070")
        _TEMPLATE["0070"] = path


def _at_0070(tmp_path) -> tuple[str, sa.Engine]:
    target = tmp_path / "db.sqlite"
    shutil.copyfile(_TEMPLATE["0070"], target)
    url = f"sqlite:///{target}"
    return url, sa.create_engine(url, future=True)


def _filler(col: dict) -> object:
    t = str(col["type"]).upper()
    if "INT" in t or "NUMERIC" in t or "BOOL" in t:
        return 0
    if "DATE" in t or "TIME" in t:
        return NOW
    if "JSON" in t:
        return "[]"
    return "x"


def _insert(engine: sa.Engine, table: str, service_id: str, version: int, **values) -> str:
    """One row of `table`, every NOT NULL column without a server default
    filled by type. `status` is written only when given in `values`."""
    row_id = str(uuid.uuid4())
    cols = sa.inspect(engine).get_columns(table)
    row: dict[str, object] = {"id": row_id, "service_id": service_id, "version": version}
    for col in cols:
        name = col["name"]
        if name in row or name == "status" or col["nullable"] or col.get("default") is not None:
            continue
        row[name] = _filler(col)
    row.update(values)
    names = ", ".join(row)
    params = ", ".join(f":{k}" for k in row)
    with engine.begin() as conn:
        conn.execute(sa.text(f"INSERT INTO {table} ({names}) VALUES ({params})"), row)  # noqa: S608
    return row_id


@pytest.mark.parametrize("table", TABLES)
def test_two_drafts_for_one_service_are_refused(tmp_path, table: str) -> None:
    url, engine = _at_0070(tmp_path)
    command.upgrade(_cfg(url), "0073")
    svc = str(uuid.uuid4())
    _insert(engine, table, svc, 1, status="APPROVED")
    _insert(engine, table, svc, 2, status="DRAFT")  # positive first: one draft is fine
    _insert(engine, table, str(uuid.uuid4()), 1, status="DRAFT")  # another service's draft
    with pytest.raises(sa.exc.IntegrityError, match="UNIQUE"):
        _insert(engine, table, svc, 3, status="DRAFT")


@pytest.mark.parametrize("table", TABLES)
def test_a_status_omitted_insert_stores_the_name_spelling(tmp_path, table: str) -> None:
    url, engine = _at_0070(tmp_path)
    command.upgrade(_cfg(url), "0073")
    svc = str(uuid.uuid4())
    first = _insert(engine, table, svc, 1)
    with engine.connect() as conn:
        stored = conn.execute(
            sa.text(f"SELECT status FROM {table} WHERE id = :id"),  # noqa: S608
            {"id": first},
        ).scalar_one()
    assert stored == "DRAFT"
    with pytest.raises(sa.exc.IntegrityError, match="UNIQUE"):
        _insert(engine, table, svc, 2)


def test_a_status_omitted_row_loads_through_the_orm(tmp_path) -> None:
    from sqlalchemy.orm import Session

    from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus

    url, engine = _at_0070(tmp_path)
    command.upgrade(_cfg(url), "0073")
    row_id = _insert(engine, "csf_assessments", str(uuid.uuid4()), 1)
    with Session(engine) as s:
        status = s.execute(
            sa.text("SELECT status FROM csf_assessments WHERE id = :id"), {"id": row_id}
        ).scalar_one()
        loaded = s.execute(sa.select(CsfAssessment.status)).scalar_one()
    assert status == "DRAFT"
    assert loaded == CsfAssessmentStatus.DRAFT


@pytest.mark.parametrize("table", TABLES)
def test_the_upgrade_refuses_over_two_drafts_and_changes_nothing(tmp_path, table: str) -> None:
    url, engine = _at_0070(tmp_path)
    svc = str(uuid.uuid4())
    _insert(engine, table, svc, 1, status="DRAFT")
    _insert(engine, table, svc, 2, status="DRAFT")
    with pytest.raises(RuntimeError, match=f"0073 refuses to upgrade.*{table}: {svc}"):
        command.upgrade(_cfg(url), "0073")
    with engine.connect() as conn:
        head = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert head == "0070"
    assert "revision_of" not in {c["name"] for c in sa.inspect(engine).get_columns(table)}


def test_revision_of_is_added_to_every_table_and_removed_by_downgrade(tmp_path) -> None:
    url, engine = _at_0070(tmp_path)
    command.upgrade(_cfg(url), "0073")
    for table in TABLES:
        cols = {c["name"] for c in sa.inspect(engine).get_columns(table)}
        assert "revision_of" in cols, table
        idx = {i["name"] for i in sa.inspect(engine).get_indexes(table)}
        assert f"uq_{table}_one_draft" in idx, table
    command.downgrade(_cfg(url), "0070")
    engine.dispose()
    for table in TABLES:
        cols = {c["name"] for c in sa.inspect(engine).get_columns(table)}
        assert "revision_of" not in cols, table
