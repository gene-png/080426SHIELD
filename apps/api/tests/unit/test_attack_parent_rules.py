"""#620 (D-094, migration 0054): which rule set an assessment renders under.

Gene's condition, 2026-09-25: a released assessment keeps rendering what was
delivered. Tests here: the reader for all four values (Gene's addition 1),
and the migration's backfill, run against a database that holds assessments
in every status BEFORE 0054 is applied.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.attack.rules import UnknownParentRules, parents_computed

API_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, True), (2, True), (1, False)],
    ids=["NULL-a-draft-new-rules", "2-new-rules", "1-old-rules"],
)
def test_the_three_known_values(value, expected) -> None:
    assert parents_computed(SimpleNamespace(id="a", parent_rules=value)) is expected


@pytest.mark.unit
@pytest.mark.parametrize("value", [0, 3, "2", True])
def test_an_unknown_value_raises_and_never_defaults(value) -> None:
    # `True` and "2" are here on purpose: `True == 1` in Python, and a string
    # that looks right is still not the stored integer.
    with pytest.raises(UnknownParentRules):
        parents_computed(SimpleNamespace(id="a", parent_rules=value))


def _cfg(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.mark.unit
def test_the_migration_backfills_approved_and_released_to_the_old_rules(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'shield-0054.db'}"
    os.environ["DATABASE_URL"] = url
    cfg = _cfg(url)
    command.upgrade(cfg, "0052")  # the revision before 0054
    engine = create_engine(url, future=True)
    ids = {}
    with engine.begin() as db:
        client = str(uuid.uuid4())
        db.execute(
            text(
                "INSERT INTO client (id, legal_name, created_at, updated_at) "
                "VALUES (:id, 'T', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": client},
        )
        # The stored form is the enum NAME, as on the dev database.
        for status in ("DRAFT", "APPROVED", "RELEASED", "DISCARDED"):
            ids[status] = str(uuid.uuid4())
            db.execute(
                text(
                    "INSERT INTO attack_assessments "
                    "(id, service_id, client_id, version, status, documents_stale, "
                    "created_at, updated_at) VALUES "
                    "(:id, :svc, :client, 1, :status, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": ids[status], "svc": str(uuid.uuid4()), "client": client, "status": status},
            )
    command.upgrade(cfg, "0054")
    with engine.connect() as db:
        got = dict(db.execute(text("SELECT status, parent_rules FROM attack_assessments")).all())
    assert got == {"DRAFT": None, "APPROVED": 1, "RELEASED": 1, "DISCARDED": None}


def _db_at_0054_with(tmp_path, rules: int | None) -> tuple[Config, object]:
    url = f"sqlite:///{tmp_path / 'shield-0054-down.db'}"
    os.environ["DATABASE_URL"] = url
    cfg = _cfg(url)
    command.upgrade(cfg, "0054")
    engine = create_engine(url, future=True)
    with engine.begin() as db:
        client = str(uuid.uuid4())
        db.execute(
            text(
                "INSERT INTO client (id, legal_name, created_at, updated_at) "
                "VALUES (:id, 'T', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": client},
        )
        db.execute(
            text(
                "INSERT INTO attack_assessments "
                "(id, service_id, client_id, version, status, documents_stale, parent_rules, "
                "created_at, updated_at) VALUES "
                "(:id, :svc, :client, 1, 'RELEASED', 0, :rules, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": str(uuid.uuid4()), "svc": str(uuid.uuid4()), "client": client, "rules": rules},
        )
    return cfg, engine


@pytest.mark.unit
def test_downgrading_0054_refuses_while_an_assessment_was_approved_under_d094(tmp_path) -> None:
    """#620 round 4. A downgrade drops the column; the re-upgrade backfills every
    APPROVED and RELEASED row to 1 -- so a rule-2 release would silently render
    under the old rules afterwards. Refused, loudly, and nothing is dropped."""
    cfg, engine = _db_at_0054_with(tmp_path, 2)
    with pytest.raises(Exception, match="parent_rules = 2"):
        command.downgrade(cfg, "0052")
    with engine.connect() as db:
        assert db.execute(text("SELECT parent_rules FROM attack_assessments")).scalar_one() == 2


@pytest.mark.unit
def test_downgrading_0054_succeeds_when_nothing_was_approved_under_d094(tmp_path) -> None:
    cfg, engine = _db_at_0054_with(tmp_path, 1)
    command.downgrade(cfg, "0052")
    with engine.connect() as db:
        cols = [r[1] for r in db.execute(text("PRAGMA table_info(attack_assessments)"))]
    assert "parent_rules" not in cols
