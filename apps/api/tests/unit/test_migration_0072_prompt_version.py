"""Migration 0072, F1 (for #1058): the `extracted_prompt_version` column.

The advisor's ruling (#736 6160171214, F1 option (a)) adds the column to 0072
itself. It is nullable and not backfilled: a row extracted before TD-2 keeps
NULL, which is what lets part B tell it from a v3.3 row whose flag went
unanswered. Like 0072's other columns it holds a fact a re-upgrade cannot
restore, so the downgrade refuses while any row holds one, and the clearing
statement the refusal prints clears it.

The column name is typed here from the ruling; stored bytes are written and
read with raw SQL.
"""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

pytestmark = pytest.mark.unit

API_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-10-14 00:00:00"
COLUMN = "extracted_prompt_version"

_TEMPLATE: dict[str, Path] = {}


def _cfg(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture(autouse=True)
def _template_0073(tmp_path_factory) -> None:
    """0072 chains after 0073 (numbered out of order), so the base is 0073."""
    if "0073" not in _TEMPLATE:
        path = tmp_path_factory.mktemp("tpl0072v") / "0073.db"
        command.upgrade(_cfg(f"sqlite:///{path}"), "0073")
        _TEMPLATE["0073"] = path


def _at_0073(tmp_path) -> tuple[str, sa.Engine]:
    target = tmp_path / "db.sqlite"
    shutil.copyfile(_TEMPLATE["0073"], target)
    url = f"sqlite:///{target}"
    return url, sa.create_engine(url, future=True)


def _columns(engine: sa.Engine) -> dict[str, dict]:
    return {c["name"]: c for c in sa.inspect(engine).get_columns("capability_items")}


def _item(engine: sa.Engine) -> str:
    """One top-level item by raw SQL, naming none of 0072's columns."""
    client, user, svc, lst, item = (uuid.uuid4().hex for _ in range(5))
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO client (id, created_at, updated_at) VALUES (:id, :n, :n)"),
            {"id": client, "n": NOW},
        )
        conn.execute(
            sa.text(
                "INSERT INTO users (id, email, password_hash, role, timezone, is_active, "
                "mfa_enrolled, failed_login_count, created_at, updated_at) VALUES "
                "(:id, :e, 'x', 'ADMIN', 'UTC', 1, 0, 0, :n, :n)"
            ),
            {"id": user, "e": f"{user}@kentro.example", "n": NOW},
        )
        conn.execute(
            sa.text(
                "INSERT INTO services (id, kind, status, title, opened_by, client_id, "
                "created_at, updated_at) VALUES "
                "(:id, 'TECH_DEBT', 'DRAFT', 'TD', :u, :c, :n, :n)"
            ),
            {"id": svc, "u": user, "c": client, "n": NOW},
        )
        conn.execute(
            sa.text(
                "INSERT INTO capability_lists (id, service_id, version, status, created_at, "
                "updated_at) VALUES (:id, :svc, 1, 'DRAFT', :n, :n)"
            ),
            {"id": lst, "svc": svc, "n": NOW},
        )
        conn.execute(
            sa.text(
                "INSERT INTO capability_items (id, capability_list_id, name, locked, "
                "security_class_confirmed, created_at, updated_at) VALUES "
                "(:id, :lst, 'Okta', 0, 0, :n, :n)"
            ),
            {"id": item, "lst": lst, "n": NOW},
        )
    return item


def _head(engine: sa.Engine) -> str:
    with engine.connect() as conn:
        return conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()


def _set_version(engine: sa.Engine, item: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE capability_items SET extracted_prompt_version = 'v3.3' WHERE id = :id"),
            {"id": item},
        )


def test_upgrade_adds_the_column_nullable_and_null_on_existing_rows(tmp_path) -> None:
    url, engine = _at_0073(tmp_path)
    item = _item(engine)
    assert COLUMN not in _columns(engine)  # positive control: absent before
    command.upgrade(_cfg(url), "0072")
    cols = _columns(engine)
    assert COLUMN in cols
    assert cols[COLUMN]["nullable"] is True
    with engine.connect() as conn:
        stored = conn.execute(
            sa.text("SELECT extracted_prompt_version FROM capability_items WHERE id = :id"),
            {"id": item},
        ).scalar_one()
    assert stored is None


def test_the_model_reads_the_column(tmp_path) -> None:
    from sqlalchemy.orm import Session

    from app.models.capability import CapabilityItem

    url, engine = _at_0073(tmp_path)
    item = _item(engine)
    command.upgrade(_cfg(url), "0072")
    _set_version(engine, item)
    with Session(engine) as s:
        assert s.get(CapabilityItem, uuid.UUID(item)).extracted_prompt_version == "v3.3"


def test_the_downgrade_refuses_while_a_row_holds_a_prompt_version(tmp_path) -> None:
    url, engine = _at_0073(tmp_path)
    item = _item(engine)
    command.upgrade(_cfg(url), "0072")
    _set_version(engine, item)  # the ONLY 0072 value on the row
    with pytest.raises(RuntimeError, match=r"Refusing to downgrade 0072: 1 capability item"):
        command.downgrade(_cfg(url), "0073")
    assert _head(engine) == "0072"
    assert COLUMN in _columns(engine)


def test_the_printed_clearing_statement_clears_it_and_lets_the_downgrade_through(
    tmp_path,
) -> None:
    url, engine = _at_0073(tmp_path)
    item = _item(engine)
    command.upgrade(_cfg(url), "0072")
    _set_version(engine, item)
    with pytest.raises(RuntimeError) as refused:
        command.downgrade(_cfg(url), "0073")
    statement = re.search(r"(UPDATE capability_items SET .+? = NULL)(?:\.|$)", str(refused.value))
    assert statement, str(refused.value)
    assert "extracted_prompt_version = NULL" in statement.group(1)
    with engine.begin() as conn:
        conn.execute(sa.text(statement.group(1)))
    command.downgrade(_cfg(url), "0073")
    assert _head(engine) == "0073"
    assert COLUMN not in _columns(engine)
