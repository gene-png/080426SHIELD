"""AI engine job-registry tests (Work Order C1)."""

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

from app.ai.engine import parse_json, registered_jobs, run_job
from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.llm_call import LLMCall, LLMCallStatus


@pytest.fixture()
def db_session(tmp_path) -> Iterator[Session]:
    url = f"sqlite:///{tmp_path / 'shield-ai.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


def _client(provider: FixtureProvider) -> LLMClient:
    return LLMClient(provider)


@pytest.mark.unit
def test_all_five_jobs_registered() -> None:
    names = registered_jobs()
    assert {
        "tech_debt_extract",
        "csf_score",
        "zt_score",
        "mitre_map",
        "risk_synthesize",
    } <= set(names)


@pytest.mark.unit
def test_parse_json_tolerates_code_fences() -> None:
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('{"b": 2}') == {"b": 2}


@pytest.mark.unit
def test_run_job_csf_score_returns_suggestions_and_logs_call(db_session) -> None:
    provider = FixtureProvider()
    canned = LLMResponse(
        '{"subcategories": [{"code": "GV.OC-01", "governance": 1, "policy": 1,'
        ' "implementation": 0, "monitoring": 0, "improvement": 0,'
        ' "what_we_found": "partial"}], "executive_summary": "draft"}',
        input_tokens=100,
        output_tokens=40,
    )
    provider.register_static("csf_score", canned)

    result = run_job(
        db_session,
        _client(provider),
        "csf_score",
        inputs={"answers": ["..."]},
        requested_by=uuid.uuid4(),
    )
    assert result.data["subcategories"][0]["code"] == "GV.OC-01"
    # The call was logged with token counts.
    row = db_session.execute(select(LLMCall)).scalars().one()
    assert row.purpose == "csf_score"
    assert row.status == LLMCallStatus.COMPLETED
    assert row.input_tokens == 100
    assert row.output_tokens == 40


@pytest.mark.unit
def test_run_job_each_suggestion_job_in_fixture_mode(db_session) -> None:
    provider = FixtureProvider()
    for purpose in ("zt_score", "mitre_map", "risk_synthesize"):
        provider.register_static(purpose, LLMResponse("{}"))
    for purpose in ("zt_score", "mitre_map", "risk_synthesize"):
        result = run_job(
            db_session,
            _client(provider),
            purpose,
            inputs={"x": 1},
            requested_by=uuid.uuid4(),
        )
        assert result.data == {}
    # Three calls logged.
    rows = db_session.execute(select(LLMCall)).scalars().all()
    assert {r.purpose for r in rows} == {"zt_score", "mitre_map", "risk_synthesize"}


@pytest.mark.unit
def test_unknown_job_raises(db_session) -> None:
    provider = FixtureProvider()
    with pytest.raises(KeyError):
        run_job(
            db_session,
            _client(provider),
            "no_such_job",
            inputs={},
            requested_by=uuid.uuid4(),
        )
