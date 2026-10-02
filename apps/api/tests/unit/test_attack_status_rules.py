"""#554 R3 (migration 0059): whether an assessment's statuses are COMPUTED from
Detect / Prevent / Respond.

The advisor's decision (d), 2026-10-02: R3 applies only to assessments approved
after it ships; an assessment approved before keeps its stored statuses on every
surface. Tests here: the reader for every value, the migration's backfill run
against a database holding assessments in every status BEFORE 0059, and the
downgrade guard.
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

from app.attack.rules import UnknownStatusRules, statuses_computed

API_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, True), (2, True), (1, False)],
    ids=["NULL-a-draft-computed", "2-computed", "1-stored"],
)
def test_the_three_known_values(value, expected) -> None:
    assert statuses_computed(SimpleNamespace(id="a", status_rules=value)) is expected


@pytest.mark.unit
@pytest.mark.parametrize("value", [0, 3, "2", True])
def test_an_unknown_value_raises_and_never_defaults(value) -> None:
    with pytest.raises(UnknownStatusRules):
        statuses_computed(SimpleNamespace(id="a", status_rules=value))


def _cfg(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _insert_client(db) -> str:
    client = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO client (id, legal_name, created_at, updated_at) "
            "VALUES (:id, 'T', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"id": client},
    )
    return client


_BEFORE_0059 = text(
    "INSERT INTO attack_assessments "
    "(id, service_id, client_id, version, status, documents_stale, created_at, updated_at) "
    "VALUES (:id, :svc, :client, 1, :status, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
)
_AT_0059 = text(
    "INSERT INTO attack_assessments "
    "(id, service_id, client_id, version, status, documents_stale, status_rules, "
    "created_at, updated_at) VALUES "
    "(:id, :svc, :client, 1, :status, 0, :rules, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
)


def _insert_assessment(db, client: str, status: str, *, rules: object = _BEFORE_0059) -> str:
    """`rules` left out: the table before 0059, which has no `status_rules`."""
    aid = str(uuid.uuid4())
    params = {"id": aid, "svc": str(uuid.uuid4()), "client": client, "status": status}
    if rules is _BEFORE_0059:
        db.execute(_BEFORE_0059, params)
    else:
        db.execute(_AT_0059, {**params, "rules": rules})
    return aid


@pytest.mark.unit
def test_the_migration_backfills_approved_and_released_to_stored_statuses(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'shield-0059.db'}"
    os.environ["DATABASE_URL"] = url
    cfg = _cfg(url)
    command.upgrade(cfg, "0058")  # the revision before 0059
    engine = create_engine(url, future=True)
    with engine.begin() as db:
        client = _insert_client(db)
        # The stored form is the enum NAME, as on the dev database (0054).
        for status in ("DRAFT", "APPROVED", "RELEASED", "DISCARDED"):
            _insert_assessment(db, client, status)
    command.upgrade(cfg, "0059")
    with engine.connect() as db:
        got = dict(db.execute(text("SELECT status, status_rules FROM attack_assessments")).all())
        cols = [r[1] for r in db.execute(text("PRAGMA table_info(attack_coverage)"))]
    assert got == {"DRAFT": None, "APPROVED": 1, "RELEASED": 1, "DISCARDED": None}
    assert {"reviewed_status", "reviewed_by", "reviewed_at"} <= set(cols)


def _db_at_0059(tmp_path, *, rules: int | None, reviewed: str | None) -> tuple[Config, object]:
    url = f"sqlite:///{tmp_path / 'shield-0059-down.db'}"
    os.environ["DATABASE_URL"] = url
    cfg = _cfg(url)
    command.upgrade(cfg, "0059")
    engine = create_engine(url, future=True)
    with engine.begin() as db:
        client = _insert_client(db)
        aid = _insert_assessment(db, client, "APPROVED", rules=rules)
        db.execute(
            text(
                "INSERT INTO attack_coverage "
                "(id, assessment_id, client_id, technique_code, status, locked, "
                "reviewed_status, created_at, updated_at) VALUES "
                "(:id, :aid, :client, 'T1003', 'partial', 0, :reviewed, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": str(uuid.uuid4()), "aid": aid, "client": client, "reviewed": reviewed},
        )
    return cfg, engine


@pytest.mark.unit
def test_downgrading_0059_refuses_while_an_assessment_was_approved_under_r3(tmp_path) -> None:
    """Dropping the column loses which rule an assessment was approved under, and
    a re-upgrade backfills it to 1 -- a computed release would then render its
    stored statuses. Refused, loudly, and nothing is dropped."""
    cfg, engine = _db_at_0059(tmp_path, rules=2, reviewed=None)
    with pytest.raises(Exception, match="status_rules = 2"):
        command.downgrade(cfg, "0058")
    with engine.connect() as db:
        assert db.execute(text("SELECT status_rules FROM attack_assessments")).scalar_one() == 2


@pytest.mark.unit
def test_downgrading_0059_refuses_while_a_review_is_recorded(tmp_path) -> None:
    """A recorded review is who accepted a computed status, which the release
    gate read; dropping it would erase that record."""
    cfg, engine = _db_at_0059(tmp_path, rules=None, reviewed="covered")
    with pytest.raises(Exception, match="reviewed_status set"):
        command.downgrade(cfg, "0058")
    with engine.connect() as db:
        assert db.execute(text("SELECT reviewed_status FROM attack_coverage")).scalar_one() == (
            "covered"
        )


@pytest.mark.unit
def test_downgrading_0059_succeeds_when_nothing_was_approved_or_reviewed(tmp_path) -> None:
    cfg, engine = _db_at_0059(tmp_path, rules=1, reviewed=None)
    command.downgrade(cfg, "0058")
    with engine.connect() as db:
        a_cols = [r[1] for r in db.execute(text("PRAGMA table_info(attack_assessments)"))]
        c_cols = [r[1] for r in db.execute(text("PRAGMA table_info(attack_coverage)"))]
    assert "status_rules" not in a_cols
    assert not {"reviewed_status", "reviewed_by", "reviewed_at"} & set(c_cols)
