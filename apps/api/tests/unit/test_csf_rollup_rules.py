"""#1031 / #1077, ruling 3 (#736 6116519635): released numbers freeze.

An APPROVED or RELEASED CSF assessment keeps the Enterprise roll-up rule it was
approved under: every in-scope tier, unscored seed tiers included. Only new or
re-approved versions use #1031's rule (scored tiers only). Migration 0070
records it in `csf_assessments.rollup_rules`, as ATT&CK's `status_rules` does:

* `1` -- approved before #1031: every in-scope tier rolls up;
* `2` -- approved under #1031: scored tiers only. Written at approve;
* NULL -- not yet approved: scored tiers only.

Tests here: the reader for every value, the migration's backfill against a
database holding assessments in every status BEFORE 0070, and the downgrade
guard.
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

from app.csf.rules import UnknownRollupRules, scored_tiers_only

API_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, True), (2, True), (1, False)],
    ids=["NULL-a-draft-scored-only", "2-scored-only", "1-every-tier"],
)
def test_the_three_known_values(value, expected) -> None:
    assert scored_tiers_only(SimpleNamespace(id="a", rollup_rules=value)) is expected


@pytest.mark.parametrize("value", [0, 3, "2", True])
def test_an_unknown_value_raises_and_never_defaults(value) -> None:
    with pytest.raises(UnknownRollupRules):
        scored_tiers_only(SimpleNamespace(id="a", rollup_rules=value))


def _cfg(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


_BEFORE_0070 = text(
    "INSERT INTO csf_assessments "
    "(id, service_id, client_id, version, status, documents_stale, created_at, updated_at) "
    "VALUES (:id, :svc, :client, 1, :status, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
)
_AFTER_0070 = text(
    "INSERT INTO csf_assessments "
    "(id, service_id, client_id, version, status, documents_stale, rollup_rules, "
    "created_at, updated_at) VALUES "
    "(:id, :svc, :client, 1, :status, 0, :rules, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
)


def _insert(db, status: str, *, rules: object = None, before: bool = True) -> None:
    client = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO client (id, legal_name, created_at, updated_at) "
            "VALUES (:id, 'T', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"id": client},
    )
    sql = _AFTER_0070 if not before else _BEFORE_0070
    db.execute(
        sql,
        {
            "id": str(uuid.uuid4()),
            "svc": str(uuid.uuid4()),
            "client": client,
            "status": status,
            "rules": rules,
        },
    )


def test_the_migration_backfills_approved_and_released_to_every_tier(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'shield-0070.db'}"
    os.environ["DATABASE_URL"] = url
    cfg = _cfg(url)
    command.upgrade(cfg, "0066")  # the revision before 0070 on main
    engine = create_engine(url, future=True)
    with engine.begin() as db:
        # The stored form is the enum NAME, as on the dev database (0054).
        for status in ("DRAFT", "SUBMITTED", "APPROVED", "RELEASED", "DISCARDED"):
            _insert(db, status)
    command.upgrade(cfg, "0070")
    with engine.connect() as db:
        got = dict(db.execute(text("SELECT status, rollup_rules FROM csf_assessments")).all())
    assert got == {
        "DRAFT": None,
        "SUBMITTED": None,
        "APPROVED": 1,
        "RELEASED": 1,
        "DISCARDED": None,
    }


def _db_at_0070(tmp_path, rules: int | None) -> Config:
    url = f"sqlite:///{tmp_path / 'shield-0070d.db'}"
    os.environ["DATABASE_URL"] = url
    cfg = _cfg(url)
    command.upgrade(cfg, "0070")
    with create_engine(url, future=True).begin() as db:
        _insert(db, "APPROVED", rules=rules, before=False)
    return cfg


def test_downgrading_0070_refuses_while_an_assessment_was_approved_under_1031(tmp_path) -> None:
    cfg = _db_at_0070(tmp_path, 2)
    with pytest.raises(RuntimeError, match="rollup_rules = 2"):
        command.downgrade(cfg, "0066")


def test_downgrading_0070_succeeds_when_nothing_was_approved_under_1031(tmp_path) -> None:
    cfg = _db_at_0070(tmp_path, 1)
    command.downgrade(cfg, "0066")
