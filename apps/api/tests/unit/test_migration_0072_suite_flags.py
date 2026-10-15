"""Migration 0072 (TD-2 part A, for #1058): the suite, recognition and
purchase-status columns on `capability_items`.

All seven columns are nullable and nothing is backfilled: a row extracted
before TD-2 keeps NULL in every one, which part B reads as "not checked for
suites", never as "not a suite". The downgrade REFUSES while any row holds a
value 0072 added (the 0068 pattern), and the documented clearing statements let
it through.

Names, spellings and the purchase-status vocabulary are typed here from the
design (td2) and the approval of the four statuses (Purchased and in use;
Purchased, not deployed; Not purchased; Unknown), stored as the member NAME per
the repo's `native_enum=False` convention -- never imported from the code
under test. Stored bytes are written and read with raw SQL.
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
NEW_COLUMNS = {
    "is_suite",
    "recognized",
    "purchase_status",
    "client_unconfirmed_name",
    "client_unconfirmed_reason",
    "client_unconfirmed_at",
    "client_unconfirmed_by",
}
STATUSES = ("PURCHASED_IN_USE", "PURCHASED_NOT_DEPLOYED", "NOT_PURCHASED", "UNKNOWN")

_TEMPLATE: dict[str, Path] = {}


def _cfg(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _engine(url: str) -> sa.Engine:
    engine = sa.create_engine(url, future=True)

    @sa.event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record) -> None:  # noqa: ANN001
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


@pytest.fixture(autouse=True)
def _template_0073(tmp_path_factory) -> None:
    """0072 chains after 0073 (numbered out of order), so the base is 0073."""
    if "0073" not in _TEMPLATE:
        path = tmp_path_factory.mktemp("tpl0072") / "0073.db"
        command.upgrade(_cfg(f"sqlite:///{path}"), "0073")
        _TEMPLATE["0073"] = path


def _at_0073(tmp_path) -> tuple[str, sa.Engine]:
    target = tmp_path / "db.sqlite"
    shutil.copyfile(_TEMPLATE["0073"], target)
    url = f"sqlite:///{target}"
    return url, _engine(url)


def _columns(engine: sa.Engine) -> dict[str, dict]:
    return {c["name"]: c for c in sa.inspect(engine).get_columns("capability_items")}


def _list_and_item(engine: sa.Engine) -> tuple[str, str, str]:
    """A user, a service, a list and one top-level item, by raw SQL, naming none
    of 0072's columns: the shape every pre-0072 row has."""
    # `.hex`: the spelling the ORM's `Uuid` type writes and looks up on SQLite.
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
                "(:id, :lst, 'Microsoft 365 G5', 0, 0, :n, :n)"
            ),
            {"id": item, "lst": lst, "n": NOW},
        )
    return user, lst, item


def _component(engine: sa.Engine, lst: str, parent: str, **values) -> str:
    cid = uuid.uuid4().hex
    row = {
        "id": cid,
        "capability_list_id": lst,
        "parent_item_id": parent,
        "name": "Defender for Endpoint",
        "locked": 0,
        "security_class_confirmed": 0,
        "created_at": NOW,
        "updated_at": NOW,
        **values,
    }
    names = ", ".join(row)
    params = ", ".join(f":{k}" for k in row)
    with engine.begin() as conn:
        conn.execute(
            sa.text(f"INSERT INTO capability_items ({names}) VALUES ({params})"), row  # noqa: S608
        )
    return cid


def _head(engine: sa.Engine) -> str:
    with engine.connect() as conn:
        return conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()


def test_upgrade_adds_every_column_nullable_and_null_on_existing_rows(tmp_path) -> None:
    url, engine = _at_0073(tmp_path)
    _, _, item = _list_and_item(engine)
    assert NEW_COLUMNS.isdisjoint(_columns(engine))  # positive control: absent before
    command.upgrade(_cfg(url), "0072")
    cols = _columns(engine)
    assert set(cols) >= NEW_COLUMNS
    assert all(cols[name]["nullable"] for name in NEW_COLUMNS)
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT "  # noqa: S608  (a fixed column list typed above, no input)
                + ", ".join(sorted(NEW_COLUMNS))
                + " FROM capability_items WHERE id = :id"
            ),
            {"id": item},
        ).one()
    assert tuple(row) == (None,) * len(NEW_COLUMNS)


@pytest.mark.parametrize("status", STATUSES)
def test_each_approved_purchase_status_is_accepted_on_a_component(tmp_path, status: str) -> None:
    url, engine = _at_0073(tmp_path)
    _, lst, item = _list_and_item(engine)
    command.upgrade(_cfg(url), "0072")
    cid = _component(engine, lst, item, purchase_status=status)
    with engine.connect() as conn:
        stored = conn.execute(
            sa.text("SELECT purchase_status FROM capability_items WHERE id = :id"), {"id": cid}
        ).scalar_one()
    assert stored == status


@pytest.mark.parametrize("bad", ["purchased_in_use", "Purchased and in use", "IN_USE", ""])
def test_a_purchase_status_off_the_list_is_refused(tmp_path, bad: str) -> None:
    url, engine = _at_0073(tmp_path)
    _, lst, item = _list_and_item(engine)
    command.upgrade(_cfg(url), "0072")
    with pytest.raises(sa.exc.IntegrityError, match="purchase_status_vocabulary"):
        _component(engine, lst, item, purchase_status=bad)


def test_a_purchase_status_on_a_top_level_row_is_refused(tmp_path) -> None:
    url, engine = _at_0073(tmp_path)
    _, lst, item = _list_and_item(engine)
    command.upgrade(_cfg(url), "0072")
    _component(engine, lst, item, purchase_status="UNKNOWN")  # positive first
    refused = pytest.raises(sa.exc.IntegrityError, match="purchase_status_on_component")
    with refused, engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE capability_items SET purchase_status = 'UNKNOWN' WHERE id = :id"),
            {"id": item},
        )


def test_the_model_reads_the_new_columns(tmp_path) -> None:
    from sqlalchemy.orm import Session

    from app.models.capability import CapabilityItem, PurchaseStatus

    url, engine = _at_0073(tmp_path)
    user, lst, item = _list_and_item(engine)
    command.upgrade(_cfg(url), "0072")
    cid = _component(engine, lst, item, purchase_status="PURCHASED_NOT_DEPLOYED")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE capability_items SET is_suite = 1, recognized = 0, "
                "client_unconfirmed_name = 'Pat Lee', client_unconfirmed_reason = 'No records', "
                "client_unconfirmed_at = :n, client_unconfirmed_by = :u WHERE id = :id"
            ),
            {"n": NOW, "u": user, "id": item},
        )
    with Session(engine) as s:
        parent = s.get(CapabilityItem, uuid.UUID(item))
        comp = s.get(CapabilityItem, uuid.UUID(cid))
        assert parent.is_suite is True
        assert parent.recognized is False
        assert parent.client_unconfirmed_name == "Pat Lee"
        assert parent.client_unconfirmed_reason == "No records"
        assert parent.client_unconfirmed_at is not None
        assert parent.client_unconfirmed_by == uuid.UUID(user)
        assert parent.purchase_status is None
        assert comp.purchase_status is PurchaseStatus.PURCHASED_NOT_DEPLOYED
        assert comp.is_suite is None
        assert comp.recognized is None


def test_the_model_declares_the_checks_the_migration_creates(tmp_path) -> None:
    from app.models.capability import CapabilityItem

    url, engine = _at_0073(tmp_path)
    command.upgrade(_cfg(url), "0072")
    created = {c["name"] for c in sa.inspect(engine).get_check_constraints("capability_items")}
    declared = {
        c.name for c in CapabilityItem.__table__.constraints if isinstance(c, sa.CheckConstraint)
    }
    expected = {
        "ck_capability_items_purchase_status_vocabulary",
        "ck_capability_items_purchase_status_on_component",
    }
    assert expected <= created
    assert expected <= declared


def test_a_clean_downgrade_removes_every_column(tmp_path) -> None:
    url, engine = _at_0073(tmp_path)
    _list_and_item(engine)
    command.upgrade(_cfg(url), "0072")
    command.downgrade(_cfg(url), "0073")
    assert _head(engine) == "0073"
    assert NEW_COLUMNS.isdisjoint(_columns(engine))
    checks = {c["name"] for c in sa.inspect(engine).get_check_constraints("capability_items")}
    assert not any("purchase_status" in (name or "") for name in checks)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("is_suite", 0),
        ("recognized", 1),
        ("client_unconfirmed_name", "Pat Lee"),
        ("client_unconfirmed_reason", "No records"),
        ("client_unconfirmed_at", NOW),
        ("client_unconfirmed_by", "USER"),
        ("purchase_status", "UNKNOWN"),
    ],
)
def test_the_downgrade_refuses_while_any_row_holds_a_0072_value(
    tmp_path, column: str, value: object
) -> None:
    """Including a recorded False: "not a suite" is a decision a re-upgrade
    could not recover, so it is data like any other."""
    url, engine = _at_0073(tmp_path)
    user, lst, item = _list_and_item(engine)
    command.upgrade(_cfg(url), "0072")
    target = item
    if column == "purchase_status":
        target = _component(engine, lst, item)
    if value == "USER":
        value = user
    with engine.begin() as conn:
        conn.execute(
            sa.text(f"UPDATE capability_items SET {column} = :v WHERE id = :id"),  # noqa: S608
            {"v": value, "id": target},
        )
    with pytest.raises(RuntimeError, match=r"Refusing to downgrade 0072: 1 capability item"):
        command.downgrade(_cfg(url), "0073")
    assert _head(engine) == "0072"
    assert set(_columns(engine)) >= NEW_COLUMNS


def test_the_refusal_names_the_clearing_statement_and_it_lets_the_downgrade_through(
    tmp_path,
) -> None:
    url, engine = _at_0073(tmp_path)
    _, lst, item = _list_and_item(engine)
    command.upgrade(_cfg(url), "0072")
    _component(engine, lst, item, purchase_status="NOT_PURCHASED")
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE capability_items SET is_suite = 1 WHERE id = :id"), {"id": item}
        )
    with pytest.raises(RuntimeError) as refused:
        command.downgrade(_cfg(url), "0073")
    message = str(refused.value)
    assert "Refusing to downgrade 0072: 2 capability items" in message
    statement = re.search(r"(UPDATE capability_items SET .+? = NULL)(?:\.|$)", message)
    assert statement, message
    with engine.begin() as conn:
        conn.execute(sa.text(statement.group(1)))
    command.downgrade(_cfg(url), "0073")
    assert _head(engine) == "0073"
    assert NEW_COLUMNS.isdisjoint(_columns(engine))
