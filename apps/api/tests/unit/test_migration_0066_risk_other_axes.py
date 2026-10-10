"""Migration 0066: `risk_entries.other_axes` (#806 G1 option 3, for #474).

The approval (#736 6094620397, Risk E item 1) has three conditions, and each
has a test here:

- the column is NULLABLE and ADDITIVE: a row that existed before 0066 survives
  the upgrade unchanged, with `other_axes` NULL ("not recorded"), and the
  column carries no server default that would invent a value for it;
- the upgrade and the downgrade both run, and round-trip;
- the downgrade REFUSES while any row records a value, `[]` included, because
  `[]` is the positive claim "no other axis" and dropping it loses that claim.

`batch_alter_table` is what lets the downgrade drop the column on SQLite;
these tests run on SQLite, so a downgrade that bypassed it would surface here.

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

_NOW = "2026-10-10 00:00:00"


def _cfg(url: str) -> Config:
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _columns(engine: sa.Engine) -> dict[str, dict]:
    return {c["name"]: c for c in sa.inspect(engine).get_columns("risk_entries")}


def _insert_entry(engine: sa.Engine, *, title: str) -> str:
    entry_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO risk_entries (id, register_id, client_id, title, axis, "
                "origin, created_at, updated_at) VALUES "
                "(:id, :r, :c, :t, 'detection', 'ai_generated', :now, :now)"
            ),
            {
                "id": entry_id,
                "r": str(uuid.uuid4()),
                "c": str(uuid.uuid4()),
                "t": title,
                "now": _NOW,
            },
        )
    return entry_id


def _row(engine: sa.Engine, entry_id: str) -> dict:
    with engine.begin() as conn:
        return dict(
            conn.execute(sa.text("SELECT * FROM risk_entries WHERE id = :id"), {"id": entry_id})
            .mappings()
            .one()
        )


@pytest.mark.unit
def test_0066_adds_a_nullable_column_and_leaves_an_existing_row_unrecorded(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'm0066.db'}"
    command.upgrade(_cfg(url), "0065")
    engine = sa.create_engine(url, future=True)
    assert "other_axes" not in _columns(engine)
    entry_id = _insert_entry(engine, title="Credential dumping goes undetected")
    before = _row(engine, entry_id)

    command.upgrade(_cfg(url), "0066")

    column = _columns(engine)["other_axes"]
    assert column["nullable"] is True
    assert column["default"] is None
    after = _row(engine, entry_id)
    assert after.pop("other_axes") is None
    assert after == before


@pytest.mark.unit
def test_0066_downgrade_drops_the_column_when_nothing_is_recorded_and_round_trips(
    tmp_path,
) -> None:
    url = f"sqlite:///{tmp_path / 'm0066-down.db'}"
    command.upgrade(_cfg(url), "0066")
    engine = sa.create_engine(url, future=True)
    entry_id = _insert_entry(engine, title="Ransomware recovery untested")

    command.downgrade(_cfg(url), "0065")
    assert "other_axes" not in _columns(engine)
    assert _row(engine, entry_id)["title"] == "Ransomware recovery untested"

    command.upgrade(_cfg(url), "0066")
    assert "other_axes" in _columns(engine)
    assert _row(engine, entry_id)["other_axes"] is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "stored", ['["prevention", "response"]', "[]"], ids=["a-list", "the-empty-claim"]
)
def test_0066_downgrade_refuses_while_an_entry_records_other_axes(tmp_path, stored: str) -> None:
    url = f"sqlite:///{tmp_path / 'm0066-refuse.db'}"
    command.upgrade(_cfg(url), "0066")
    engine = sa.create_engine(url, future=True)
    entry_id = _insert_entry(engine, title="Phishing response has no owner")
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE risk_entries SET other_axes = :v WHERE id = :id"),
            {"v": stored, "id": entry_id},
        )

    with pytest.raises(
        RuntimeError, match="Refusing to downgrade 0066: 1 Risk Register entry records"
    ):
        command.downgrade(_cfg(url), "0065")
    assert "other_axes" in _columns(engine)
    assert _row(engine, entry_id)["other_axes"] == stored
