"""AI engine job-registry tests (Work Order C1)."""

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

from app.ai.engine import (
    AIResponseShapeError,
    get_job,
    parse_json,
    registered_jobs,
    run_job,
)
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


# --------------------------------------------------------------------------- #
# Issue #41: a response whose TOP LEVEL is not an object was flattened to `{}`
# by every consumer (`csf.py`, `zt.py`, `risk.py`, `attack.py`), so a model that
# returned its list unwrapped had every suggestion discarded and the run
# reported zero changes — indistinguishable from "the AI agreed with everything".
#
# `parse_json` cannot catch this: `json.loads` is perfectly happy with a list.
# The four prompts all mandate an object (`{"scores": …}`, `{"capabilities": …}`,
# `{"entries": …}`, `{"techniques": …}`), so a non-object top level is always a
# contract violation and never a valid empty answer.
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_parse_json_object_accepts_an_object() -> None:
    from app.ai.engine import parse_json_object

    assert parse_json_object('{"scores": []}') == {"scores": []}
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}


@pytest.mark.unit
def test_parse_json_object_refuses_a_non_object_top_level() -> None:
    """Refuse, loudly. Returning `{}` is what made this invisible.

    A bare list is the classic drift off a wrapped-object contract and the most
    likely of these in practice — the model returns the array it was asked to
    put under a key.
    """
    from app.ai.engine import AIResponseShapeError, parse_json_object

    for payload in ('[{"code": "X"}]', '"just a string"', "7", "null"):
        with pytest.raises(AIResponseShapeError) as exc:
            parse_json_object(payload)
        # Must name what ARRIVED, or the operator cannot tell a provider bug
        # from a prompt bug. Asserting on "object" alone would pass on the
        # constant prefix even if the type were dropped from the message.
        assert type(json.loads(payload)).__name__ in str(exc.value), payload


@pytest.mark.unit
@pytest.mark.parametrize("job_name", registered_jobs())
def test_every_registered_job_rejects_a_bare_list_top_level(job_name: str) -> None:
    """D-052's invariant, mechanised. Found unpinned by the item-3b audit.

    D-052 states: "`jobs.py`'s carve-out comment is removed: every registered job
    carries a top-level shape guard, and that sentence is now writable." Nothing
    checked it. `test_ai_engine` asserted the five job NAMES are registered and
    stopped there, so a future `AIJob(name=..., parser=parse_json)` reopens the
    hole with the whole suite green — the #72 shape applied to an invariant
    rather than to a single behaviour.

    Parametrised over `registered_jobs()` rather than a hardcoded list, so a
    SIXTH job is covered the day it is added instead of the day someone
    remembers. That is the point: the failure mode is a job nobody thought about.

    The two shapes are D-052's own: a bare list where an object belongs
    (`decoded.get("items", []) if isinstance(decoded, dict) else []` swallowed it
    whole), and a non-list under the expected key (`for item in raw_items`
    iterated the KEYS). Either reported zero, indistinguishable from a real
    inventory holding nothing recognisable — and for `mitre_map` that feeds the
    ATT&CK allow-list, where an empty capability list once produced 607
    fabricated `gap` rows.
    """
    parser = get_job(job_name).parser
    with pytest.raises(AIResponseShapeError):
        parser('[{"a": 1}]')


@pytest.mark.unit
@pytest.mark.parametrize("job_name", registered_jobs())
def test_every_registered_job_rejects_a_non_list_under_its_own_key(job_name: str) -> None:
    """The other half of the same guard.

    The key each job expects is not knowable from here without importing the
    module's private constants -- which is precisely what the test-integrity gate
    forbids -- so this drives the parser with a payload whose EVERY plausible
    list key holds a dict. A parser that guards its key raises; one that does
    `data.get(key) or []` iterates the dict's keys and returns junk.

    **A `DID NOT RAISE` here means one of two things and both need a human.**
    Either a job lost its shape guard, or a NEW job uses a list key this payload
    does not carry — in which case `require_list_at`'s `data.get(key, [])`
    default returned an empty list and the guard was never reached. That second
    case is #46 (a wrong top-level key collapses to zero, silently), and it is
    why the payload must be extended rather than the test relaxed. Writing this
    test surfaced it immediately: the first draft omitted `scores` and `csf_score`
    reported DID NOT RAISE without any guard being missing.
    """
    payload = (
        '{"items": {"0": "x"}, "techniques": {"0": "x"}, "scores": {"0": "x"}, '
        '"capabilities": {"0": "x"}, "entries": {"0": "x"}, "rows": {"0": "x"}}'
    )
    parser = get_job(job_name).parser
    with pytest.raises(AIResponseShapeError):
        parser(payload)
