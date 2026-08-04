"""`audit()` helper produces a correctly-shaped row, including correlation ID."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.logging import correlation_id_var
from app.models.audit_entry import AuditEntry


@pytest.fixture()
def db_session(tmp_path) -> Session:
    db_path = tmp_path / "shield-test.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url

    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    with Session(engine) as s:
        yield s


@pytest.mark.unit
def test_audit_writes_row_with_correlation_id(db_session) -> None:
    token = correlation_id_var.set("cid-spine-001")
    try:
        target = uuid.uuid4()
        audit(
            db_session,
            action="thing.created",
            target_type="thing",
            target_id=target,
            details={"foo": "bar"},
        )
        db_session.commit()
    finally:
        correlation_id_var.reset(token)

    row = db_session.execute(select(AuditEntry)).scalar_one()
    assert row.action == "thing.created"
    assert row.target_type == "thing"
    assert row.target_id == target
    assert row.correlation_id == "cid-spine-001"
    assert row.details == {"foo": "bar"}


@pytest.mark.unit
def test_audit_writes_row_without_correlation_id_when_none_set(db_session) -> None:
    audit(db_session, action="thing.deleted", target_type="thing")
    db_session.commit()
    row = db_session.execute(select(AuditEntry)).scalar_one()
    assert row.correlation_id is None
    assert row.target_id is None
