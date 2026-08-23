"""Runtime fixture-mode AI: all 5 purposes registered, parseable, 503 on miss.

T6b: fixture mode must make the demo/dev stack exercisable OFFLINE. These tests
drive the runtime provider directly (via build_runtime_provider / from_settings)
WITHOUT any pytest FastAPI dependency overrides, proving the provider the app
actually builds in fixture mode carries a deterministic response for every job.
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

from app.ai.engine import run_job
from app.ai.fixtures import (
    ALL_PURPOSES,
    MissingFixtureError,
    RuntimeFixtureProvider,
    build_runtime_provider,
)
from app.ai.llm import LLMClient
from app.config import Settings
from app.models.llm_call import LLMCall, LLMCallStatus


@pytest.fixture()
def db_session(tmp_path) -> Iterator[Session]:
    url = f"sqlite:///{tmp_path / 'shield-runtime-fixtures.db'}"
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


@pytest.mark.unit
def test_runtime_provider_registers_all_five_purposes() -> None:
    provider = build_runtime_provider()
    assert set(provider._fixtures) >= set(ALL_PURPOSES)
    assert len(ALL_PURPOSES) == 5


@pytest.mark.unit
def test_from_settings_fixture_mode_uses_runtime_provider() -> None:
    """The provider the app builds in fixture mode is the preloaded runtime one."""
    settings = Settings(shield_llm_mode="fixture")
    client = LLMClient.from_settings(settings)
    assert isinstance(client.provider, RuntimeFixtureProvider)
    assert set(client.provider._fixtures) >= set(ALL_PURPOSES)


@pytest.mark.unit
def test_run_job_mitre_map_is_parseable_without_overrides(db_session) -> None:
    llm = LLMClient(build_runtime_provider())
    result = run_job(
        db_session,
        llm,
        "mitre_map",
        inputs={
            "capability_list": ["CrowdStrike Falcon", "Splunk"],
            "technique_codes": ["T1003", "T1059", "T1566"],
        },
        requested_by=uuid.uuid4(),
    )
    assert isinstance(result.data, dict)
    techniques = result.data["techniques"]
    assert len(techniques) == 3
    codes = {t["technique_code"] for t in techniques}
    assert codes == {"T1003", "T1059", "T1566"}
    # Every drafted technique carries a status; cited tools come only from the
    # supplied capability list.
    for t in techniques:
        assert t["status"] in {"covered", "partial", "gap", "not_applicable"}
        for cited in t["detection_tools"] + t["response_tools"]:
            assert cited in {"CrowdStrike Falcon", "Splunk"}
    row = db_session.execute(select(LLMCall)).scalars().one()
    assert row.purpose == "mitre_map"
    assert row.status == LLMCallStatus.COMPLETED


@pytest.mark.unit
def test_run_job_zt_score_cisa_is_parseable_without_overrides(db_session) -> None:
    llm = LLMClient(build_runtime_provider())
    result = run_job(
        db_session,
        llm,
        "zt_score",
        inputs={"framework": "cisa_ztmm_2_0", "capabilities": ["ID.1", "ID.2", "DE.1"]},
        requested_by=uuid.uuid4(),
    )
    assert isinstance(result.data, dict)
    caps = result.data["capabilities"]
    assert {c["code"] for c in caps} == {"ID.1", "ID.2", "DE.1"}
    for c in caps:
        assert 1 <= c["current"] <= 4
        assert 1 <= c["target"] <= 4


@pytest.mark.unit
def test_zt_score_dod_respects_three_stage_clamp(db_session) -> None:
    """DoD ZTRA maxes at stage 3; the fixture must never emit a 4."""
    llm = LLMClient(build_runtime_provider())
    result = run_job(
        db_session,
        llm,
        "zt_score",
        inputs={"framework": "dod_ztra", "capabilities": ["ID.1", "ID.2", "AC.1"]},
        requested_by=uuid.uuid4(),
    )
    caps = result.data["capabilities"]
    assert caps, "expected at least one drafted capability"
    for c in caps:
        assert 1 <= c["current"] <= 3
        assert 1 <= c["target"] <= 3


@pytest.mark.unit
def test_all_purposes_return_valid_json_for_their_parser(db_session) -> None:
    """Every purpose produces a result its job parser accepts (no raw crash)."""
    llm = LLMClient(build_runtime_provider())
    cases = {
        "mitre_map": {"technique_codes": ["T1003"], "capability_list": ["Splunk"]},
        "zt_score": {"framework": "cisa_ztmm_2_0", "capabilities": ["ID.1"]},
        "csf_score": {"tiers": ["high"], "subcategories": ["GV.OC-01"]},
        "tech_debt_extract": {"rows": [{"name": "Okta"}], "context": {}},
        "risk_synthesize": {
            "findings": [{"source": "coverage_finding", "source_id": "T1003", "kind": "attack"}],
            "valid_techniques": ["T1003"],
            "valid_controls": [],
        },
    }
    for job_name, inputs in cases.items():
        result = run_job(db_session, llm, job_name, inputs=inputs, requested_by=uuid.uuid4())
        assert result.data is not None
    # tech_debt parser returns a list of ExtractedCapability; the others dicts.
    td = run_job(
        db_session,
        llm,
        "tech_debt_extract",
        inputs={"rows": [{"name": "Okta"}], "context": {}},
        requested_by=uuid.uuid4(),
    )
    assert td.data and td.data[0].confidence_pct is not None


@pytest.mark.unit
def test_missing_fixture_raises_typed_503_not_raw_keyerror(db_session) -> None:
    """A missing fixture is an operator-actionable 503, never a raw 500 KeyError."""
    provider = RuntimeFixtureProvider()  # nothing registered
    llm = LLMClient(provider)
    with pytest.raises(MissingFixtureError) as exc_info:
        run_job(
            db_session,
            llm,
            "mitre_map",
            inputs={"technique_codes": ["T1003"]},
            requested_by=uuid.uuid4(),
        )
    err = exc_info.value
    assert err.status_code == 503
    assert isinstance(err.detail, dict)
    assert err.detail["reason"] == "ai_fixture_unavailable"
    # The failed call is still audited.
    row = db_session.execute(select(LLMCall)).scalars().one()
    assert row.status == LLMCallStatus.FAILED


@pytest.mark.unit
def test_mitre_map_fixture_reads_enriched_capability_objects() -> None:
    """The single highest-risk item in plan part 1B, and it is a CI-only failure.

    `_fixture_mitre_map` called `_strs(payload["capability_list"])`, which keeps
    only `isinstance(v, str)`. The moment the payload carries objects, that
    returns `[]` — so fixture mode cites ZERO tools, and fixture mode is what CI
    runs. Every existing assertion about tool citations (s5-attack among them)
    would have gone red at once, with the cause three files away from the
    failure.

    Both shapes are accepted deliberately rather than switching over: a stored
    payload written before the enrichment (an `llm_calls` row being replayed, an
    older preview) is still a list of strings, and the C0 pattern says those must
    keep parsing.
    """
    from app.ai.fixtures import _fixture_mitre_map

    enriched = _fixture_mitre_map(
        {
            "technique_codes": ["T1003", "T1059"],
            "capability_list": [
                {
                    "name": "CrowdStrike Falcon",
                    "vendor": "CrowdStrike",
                    "category": "EDR",
                    "security_functions": ["detect", "respond"],
                },
                {"name": "Splunk Enterprise", "vendor": "Splunk", "category": "SIEM"},
            ],
        }
    )
    cited = json.loads(enriched.content)["techniques"]
    named = {t for row in cited for t in row["detection_tools"] + row["response_tools"]}
    assert named, "fixture mode cited no tools at all from an enriched payload"
    assert named <= {"CrowdStrike Falcon", "Splunk Enterprise"}, named


@pytest.mark.unit
def test_mitre_map_fixture_still_reads_a_bare_string_list() -> None:
    """C0: an older stored payload is a list of strings and must keep working."""
    from app.ai.fixtures import _fixture_mitre_map

    legacy = _fixture_mitre_map(
        {"technique_codes": ["T1003"], "capability_list": ["CrowdStrike Falcon"]}
    )
    rows = json.loads(legacy.content)["techniques"]
    named = {t for row in rows for t in row["detection_tools"] + row["response_tools"]}
    assert named == {"CrowdStrike Falcon"}


@pytest.mark.unit
def test_mitre_map_fixture_ignores_an_object_with_no_usable_name() -> None:
    """A malformed entry must not become a citation of the empty string, which
    the resolver would then count as unusable on every technique."""
    from app.ai.fixtures import _fixture_mitre_map

    out = _fixture_mitre_map(
        {
            "technique_codes": ["T1003"],
            "capability_list": [{"vendor": "Nobody"}, {"name": ""}, {"name": "Wiz"}],
        }
    )
    rows = json.loads(out.content)["techniques"]
    named = {t for row in rows for t in row["detection_tools"] + row["response_tools"]}
    assert named == {"Wiz"}
