"""llm_calls tenant attribution (Sprint 3 T5).

Every AI egress row should carry the client it was run for, so the largest
cross-assessment payload (risk synthesis) is attributable to a tenant. The
column is additive + nullable (C0 pattern): old rows and calls made without a
client_id parse unchanged.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.engine import run_job
from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.llm_call import LLMCall

_PURPOSES = ("tech_debt_extract", "csf_score", "zt_score", "mitre_map", "risk_synthesize")


@pytest.fixture()
def db_session(tmp_path) -> Iterator[Session]:
    url = f"sqlite:///{tmp_path / 'shield-attr.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    # Upgrading to head on SQLite proves the migration is batch_alter_table-safe.
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.mark.unit
def test_run_job_attributes_client_id_on_all_five_purposes(db_session) -> None:
    provider = FixtureProvider()
    # Register a catch-all so every job's call_purpose resolves (tech_debt_extract
    # keeps the historical "extract.capabilities" purpose, so name != purpose).
    provider.register_static("default", LLMResponse("{}"))

    seen: set[uuid.UUID] = set()
    for job_name in _PURPOSES:
        client_id = uuid.uuid4()
        run_job(
            db_session,
            LLMClient(provider),
            job_name,
            inputs={"x": 1},
            requested_by=uuid.uuid4(),
            client_id=client_id,
        )
        seen.add(client_id)

    rows = db_session.execute(select(LLMCall)).scalars().all()
    assert len(rows) == len(_PURPOSES)
    assert {r.client_id for r in rows} == seen


@pytest.mark.unit
def test_client_id_is_optional_additive(db_session) -> None:
    """A call with no client_id still writes a row (nullable, C0)."""
    provider = FixtureProvider()
    provider.register_static("csf_score", LLMResponse("{}"))
    run_job(
        db_session,
        LLMClient(provider),
        "csf_score",
        inputs={"x": 1},
        requested_by=uuid.uuid4(),
    )
    row = db_session.execute(select(LLMCall)).scalars().one()
    assert row.client_id is None
