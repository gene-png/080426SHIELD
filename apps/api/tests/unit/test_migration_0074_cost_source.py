"""Migration 0074 (TD-5, for #1060): where an item's annual cost came from.

Two nullable columns, nothing backfilled: every existing row keeps NULL, which
reads as "not an estimate". The vocabulary (`ai_estimate`, `consultant`) is
typed here from the approved proposal (#736 6205600298, ruled in 6206818759),
never imported from the code under test. The downgrade REFUSES while any row
holds a value 0074 added (the 0068/0072 pattern), and its clearing statement
lets it through. Stored bytes are written and read with raw SQL.
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
NOW = "2026-10-16 00:00:00"
NEW_COLUMNS = {"cost_source", "cost_estimate_basis"}
SOURCES = ("ai_estimate", "consultant")

_TEMPLATE: dict[str, Path] = {}


def _cfg(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture(autouse=True)
def _template_0072(tmp_path_factory) -> None:
    """0074's parent is 0072 (which chains after 0073)."""
    if "0072" not in _TEMPLATE:
        path = tmp_path_factory.mktemp("tpl0074") / "0072.db"
        command.upgrade(_cfg(f"sqlite:///{path}"), "0072")
        _TEMPLATE["0072"] = path


def _at_0072(tmp_path) -> tuple[str, sa.Engine]:
    target = tmp_path / "db.sqlite"
    shutil.copyfile(_TEMPLATE["0072"], target)
    url = f"sqlite:///{target}"
    return url, sa.create_engine(url, future=True)


def _columns(engine: sa.Engine) -> dict[str, dict]:
    return {c["name"]: c for c in sa.inspect(engine).get_columns("capability_items")}


def _head(engine: sa.Engine) -> str:
    with engine.connect() as conn:
        return conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()


def _item(engine: sa.Engine) -> str:
    """One costed top-level item, by raw SQL, naming none of 0074's columns."""
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
                "INSERT INTO capability_items (id, capability_list_id, name, annual_cost_usd, "
                "locked, security_class_confirmed, created_at, updated_at) VALUES "
                "(:id, :lst, 'Tool A', 1200, 0, 0, :n, :n)"
            ),
            {"id": item, "lst": lst, "n": NOW},
        )
    return item


def _set(engine: sa.Engine, item: str, **values) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in values)
    with engine.begin() as conn:
        conn.execute(
            sa.text(f"UPDATE capability_items SET {sets} WHERE id = :id"),  # noqa: S608
            {**values, "id": item},
        )


def test_upgrade_adds_both_columns_nullable_and_null_on_existing_rows(tmp_path) -> None:
    url, engine = _at_0072(tmp_path)
    item = _item(engine)
    assert NEW_COLUMNS.isdisjoint(_columns(engine))  # positive control: absent before
    command.upgrade(_cfg(url), "0074")
    cols = _columns(engine)
    assert set(cols) >= NEW_COLUMNS
    assert all(cols[name]["nullable"] for name in NEW_COLUMNS)
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT cost_source, cost_estimate_basis, annual_cost_usd "
                "FROM capability_items WHERE id = :id"
            ),
            {"id": item},
        ).one()
    # The existing cost is untouched and not labelled an estimate.
    assert tuple(row) == (None, None, 1200)


@pytest.mark.parametrize("source", SOURCES)
def test_each_recorded_source_is_accepted(tmp_path, source: str) -> None:
    url, engine = _at_0072(tmp_path)
    item = _item(engine)
    command.upgrade(_cfg(url), "0074")
    _set(engine, item, cost_source=source)
    with engine.connect() as conn:
        stored = conn.execute(
            sa.text("SELECT cost_source FROM capability_items WHERE id = :id"), {"id": item}
        ).scalar_one()
    assert stored == source


@pytest.mark.parametrize("bad", ["AI_ESTIMATE", "AI estimate", "upload", "estimate", ""])
def test_a_source_off_the_list_is_refused(tmp_path, bad: str) -> None:
    url, engine = _at_0072(tmp_path)
    item = _item(engine)
    command.upgrade(_cfg(url), "0074")
    with pytest.raises(sa.exc.IntegrityError, match="cost_source_vocabulary"):
        _set(engine, item, cost_source=bad)


@pytest.mark.parametrize(
    "values",
    [{"cost_source": "ai_estimate"}, {"cost_source": "consultant"}, {"cost_estimate_basis": "x"}],
    ids=["ai_estimate", "consultant", "basis-only"],
)
def test_the_downgrade_refuses_while_a_row_holds_a_value_0074_added(tmp_path, values) -> None:
    url, engine = _at_0072(tmp_path)
    item = _item(engine)
    command.upgrade(_cfg(url), "0074")
    _set(engine, item, **values)
    with pytest.raises(RuntimeError, match=r"Refusing to downgrade 0074: 1 capability item holds"):
        command.downgrade(_cfg(url), "0072")
    assert _head(engine) == "0074"
    assert set(_columns(engine)) >= NEW_COLUMNS


def test_the_refusal_names_the_clearing_statements_and_they_let_the_downgrade_through(
    tmp_path,
) -> None:
    url, engine = _at_0072(tmp_path)
    item = _item(engine)
    command.upgrade(_cfg(url), "0074")
    _set(engine, item, cost_source="ai_estimate", cost_estimate_basis="List price.")
    with pytest.raises(RuntimeError) as refused:
        command.downgrade(_cfg(url), "0072")
    message = str(refused.value)
    clear_estimates = (
        "UPDATE capability_items SET annual_cost_usd = NULL WHERE cost_source = 'ai_estimate'"
    )
    clear_labels = "UPDATE capability_items SET cost_source = NULL, cost_estimate_basis = NULL"
    assert clear_estimates in message
    assert clear_labels in message
    with engine.begin() as conn:
        conn.execute(sa.text(clear_estimates))
        conn.execute(sa.text(clear_labels))
    command.downgrade(_cfg(url), "0072")
    assert _head(engine) == "0072"
    assert NEW_COLUMNS.isdisjoint(_columns(engine))
    with engine.connect() as conn:
        cost = conn.execute(
            sa.text("SELECT annual_cost_usd FROM capability_items WHERE id = :id"), {"id": item}
        ).scalar_one()
    # The estimate did not survive its label.
    assert cost is None


def test_an_empty_downgrade_goes_through(tmp_path) -> None:
    url, engine = _at_0072(tmp_path)
    _item(engine)
    command.upgrade(_cfg(url), "0074")
    command.downgrade(_cfg(url), "0072")
    assert _head(engine) == "0072"
    assert NEW_COLUMNS.isdisjoint(_columns(engine))
