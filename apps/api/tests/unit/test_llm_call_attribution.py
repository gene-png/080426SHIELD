"""llm_calls tenant attribution (Sprint 3 T5).

Every AI egress row should carry the client it was run for, so the largest
cross-assessment payload (risk synthesis) is attributable to a tenant. The
column is additive + nullable (C0 pattern): old rows and calls made without a
client_id parse unchanged.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.engine import get_job, run_job
from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.llm_call import LLMCall

_PURPOSES = ("tech_debt_extract", "csf_score", "zt_score", "mitre_map", "risk_synthesize")


def _empty_but_valid(job_name: str) -> str:
    """The job's own "nothing to suggest" answer, in the shape its prompt asks for.

    These tests are about `client_id` attribution; the response body is
    scaffolding. It used to be a bare `{}` for every purpose, which #46 made an
    error -- correctly, because `{}` was indistinguishable from a real empty
    result and no prompt instructs it. The empty answer is `{"<key>": []}`.

    DERIVED from the job's own declaration rather than listed here, so adding a
    suggestion job cannot leave a stale literal behind. `tech_debt_extract`
    keeps its own parser and declares no key, so its "items" is the one thing
    written down -- and `test_the_tech_debt_key_is_still_what_its_parser_wants`
    below fails if that stops being true.
    """
    key = get_job(job_name).top_level_key or _TECH_DEBT_KEY
    return json.dumps({key: []})


# `_parse_response` in `app/tech_debt/extract.py` requires this and, unlike the
# four suggestion jobs, does not declare it on the job -- it keeps a bespoke
# parser for the per-item coercion and the wrap-in-prose retry.
_TECH_DEBT_KEY = "items"


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
    # Registered PER PURPOSE rather than as one catch-all: each job now requires
    # its own top-level key (#46), so no single body can satisfy all five.
    # `call_purpose` is used because `tech_debt_extract` keeps the historical
    # "extract.capabilities" purpose, so name != purpose.
    for name in _PURPOSES:
        provider.register_static(get_job(name).call_purpose, LLMResponse(_empty_but_valid(name)))

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
    provider.register_static("csf_score", LLMResponse(_empty_but_valid("csf_score")))
    run_job(
        db_session,
        LLMClient(provider),
        "csf_score",
        inputs={"x": 1},
        requested_by=uuid.uuid4(),
    )
    row = db_session.execute(select(LLMCall)).scalars().one()
    assert row.client_id is None


@pytest.mark.unit
def test_the_tech_debt_key_is_still_what_its_parser_wants() -> None:
    """`_TECH_DEBT_KEY` is the one literal `_empty_but_valid` cannot derive.

    A literal nothing checks is how the original drift survived, so this pins
    it against the parser rather than against another copy of the same string:
    the key must be ACCEPTED, and a different one must be refused.
    """
    from app.ai.engine import AIResponseShapeError
    from app.tech_debt.extract import _parse_response

    assert _parse_response(json.dumps({_TECH_DEBT_KEY: []})) == []
    with pytest.raises(AIResponseShapeError):
        _parse_response(json.dumps({"not_" + _TECH_DEBT_KEY: []}))
