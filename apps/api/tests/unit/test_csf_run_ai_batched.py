"""csf_score in batches (#479), through CSF's Run-AI endpoint.

A full Working Profile is 106 subcategories x 3 tiers = 318 (tier,
subcategory) rows. One call over all of them could not fit any provider's
output cap, so the run splits them.

The cap these tests hold the batches to is derived from the PROVIDERS, not from
the code under test. Every figure is restated here, from its source:

* 8192 output tokens: the non-streamed adapters' cap for csf_score
  (`non_streamed_output_cap`, `app/ai/llm.py`);
* 2048 of those spent on thinking by gemini-2.5+ on Gemini and Vertex
  (`_THINKING_BUDGET_TOKENS`, the same file);
* ~575 output tokens per row: a mitre_map row as measured live on 2026-08-07
  (the comment above `_MITRE_BATCH_SIZE`, `routes/attack.py`), the high
  estimate the `llm.py` comment gives for a csf_score row.

So at most (8192 - 2048) / 575 = 10.7, i.e. 10, rows a batch.

The fixture answers are written from the PROMPT ("for every subcategory code
emit one row per tier listed in tiers"), never from the parser's constants.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.llm_call import LLMCall
from tests._ai_runs import csf_run_ai, get_run, start_run

# The provider figures above, restated rather than imported (see the docstring).
_NON_STREAMED_CAP = 8192
_GEMINI_THINKING_BUDGET = 2048
_HIGH_TOKENS_PER_ROW = 575
_TIERS = ["high", "low", "moderate"]


@dataclass
class World:
    c: TestClient
    sessions: sessionmaker
    provider: FixtureProvider
    h: dict
    svc_id: str


@pytest.fixture()
def world(tmp_path) -> Iterator[World]:
    url = f"sqlite:///{tmp_path / 'shield-csfbatch.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app
    from app.models.client import Client
    from app.models.client_domain import ClientDomain
    from app.routes.csf import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    provider = FixtureProvider()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
    with sessions() as seed:
        tenant = Client(legal_name="Test Tenant")
        seed.add(tenant)
        seed.flush()
        seed.add(ClientDomain(client_id=tenant.id, domain="example.com"))
        seed.commit()
        cid = str(tenant.id)
    with TestClient(app, headers={"X-Client-Id": cid}) as c:
        bearer = c.post(
            "/auth/register",
            json={
                "email": "admin@example.com",
                "password": "correct horse battery staple!",
                "display_name": "A",
            },
        ).json()["tokens"]["access_token"]
        h = {"Authorization": f"Bearer {bearer}"}
        svc_id = c.post(
            "/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}
        ).json()["id"]
        a = c.post(f"/csf/services/{svc_id}/assessments", headers=h)
        assert a.status_code in (200, 201), a.text
        seeded = c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": _TIERS})
        assert seeded.status_code in (200, 201), seeded.text
        yield World(c, sessions, provider, h, svc_id)


def _rows_asked(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """The (tier, subcategory) rows a payload asks for, as the prompt defines
    them: one row per tier listed, for every subcategory code."""
    return [(t, code) for t in payload["tiers"] for code in payload["subcategories"]]


def _answer_as_the_prompt_asks(payload: dict[str, Any]) -> LLMResponse:
    scores = [
        {
            "tier": t,
            "subcategory_code": code,
            "governance": 1,
            "policy": 1,
            "implementation": 1,
            "monitoring": 1,
            "improvement": 1,
            "what_we_found": "Drafted.",
        }
        for t, code in _rows_asked(payload)
    ]
    return LLMResponse(json.dumps({"scores": scores, "executive_summary": "Draft."}))


class _Recorder:
    """Records every payload the provider receives, from every batch thread."""

    def __init__(self, fail_when=None) -> None:
        self.payloads: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._fail_when = fail_when

    def __call__(self, payload: dict[str, Any]) -> LLMResponse:
        with self._lock:
            self.payloads.append(payload)
        if self._fail_when is not None and self._fail_when(payload):
            raise RuntimeError("provider closed the connection")
        return _answer_as_the_prompt_asks(payload)


def _profile_rows(world: World) -> list[tuple[str, str]]:
    out = []
    for tier in _TIERS:
        rows = world.c.get(f"/csf/services/{world.svc_id}/profile/{tier}", headers=world.h)
        assert rows.status_code == 200, rows.text
        out += [(tier, r["subcategory_code"]) for r in rows.json()["rows"]]
    return out


@pytest.mark.unit
def test_a_full_working_profile_is_asked_for_in_batches_no_larger_than_the_cap(world) -> None:
    profile = _profile_rows(world)
    assert len(profile) == 318, "the Working Profile this test is about"
    rec = _Recorder()
    world.provider.register("csf_score", rec)

    result = csf_run_ai(world.c, world.svc_id, world.h)

    # Each tier's 106 subcategories in tens: 11 batches a tier, 33 in all.
    assert len(rec.payloads) == 33
    assert result["batches_total"] == 33
    assert result["batches_failed"] == 0
    cap_rows = (_NON_STREAMED_CAP - _GEMINI_THINKING_BUDGET) // _HIGH_TOKENS_PER_ROW
    assert cap_rows == 10
    for p in rec.payloads:
        asked = _rows_asked(p)
        assert 0 < len(asked) <= cap_rows, (len(asked), p["tiers"])
        assert len(asked) * _HIGH_TOKENS_PER_ROW <= _NON_STREAMED_CAP - _GEMINI_THINKING_BUDGET
    # Every row asked for exactly once: none lost between batches, none twice.
    asked_all = [r for p in rec.payloads for r in _rows_asked(p)]
    assert sorted(asked_all) == sorted(profile)
    # Every value of every row is accounted for, as in the single-call run.
    assert result["suggestions_received"] == 318 * 6
    assert result["suggestions_applied"] == 318 * 6
    assert result["dropped"] == []


@pytest.mark.unit
def test_every_batch_carries_the_interview_answers(world) -> None:
    rows = world.c.get(f"/csf/services/{world.svc_id}/assessments/latest", headers=world.h).json()
    answer = rows["answers"][0]
    r = world.c.patch(
        f"/csf/answers/{answer['id']}",
        headers=world.h,
        json={"maturity_tier": 3, "notes": "Documented policy exists."},
    )
    assert r.status_code == 200, r.text
    rec = _Recorder()
    world.provider.register("csf_score", rec)

    csf_run_ai(world.c, world.svc_id, world.h)

    assert len(rec.payloads) == 33
    for p in rec.payloads:
        assert p["answers"][answer["subcategory_code"]]["maturity_tier"] == 3


@pytest.mark.unit
def test_a_failed_batch_leaves_a_partial_run_that_says_so(world) -> None:
    profile = _profile_rows(world)
    first_low = sorted(code for t, code in profile if t == "low")[0]

    def _fails(payload: dict[str, Any]) -> bool:
        return payload["tiers"] == ["low"] and first_low in payload["subcategories"]

    rec = _Recorder(fail_when=_fails)
    world.provider.register("csf_score", rec)

    started = start_run(world.c, f"/csf/services/{world.svc_id}/run-ai", world.h)
    run = get_run(world.c, started["run_id"], world.h)

    assert run["status"] == "completed", run
    assert run["batches_total"] == 33
    assert run["batches_failed"] == 1
    result = run["result"]
    assert result["batches_total"] == 33
    assert result["batches_failed"] == 1
    lost = [p for p in rec.payloads if _fails(p)]
    assert len(lost) == 1
    lost_rows = set(_rows_asked(lost[0]))
    assert len(lost_rows) == 10
    # The 308 rows that came back are applied; the 10 that did not are left as
    # they were, and are not counted as received or dropped -- the model never
    # answered for them. The batch count is what says they are missing.
    assert result["suggestions_received"] == 308 * 6
    assert result["suggestions_applied"] == 308 * 6
    untouched = [
        r
        for r in result["rows"]
        if (r["tier"], r["subcategory_code"]) in lost_rows and r["what_we_found"] is None
    ]
    assert len(untouched) == 10
    # The failed call is on record, as every billable call is.
    with world.sessions() as s:
        calls = s.execute(select(LLMCall).where(LLMCall.purpose == "csf_score")).scalars().all()
    assert len(calls) == 33
    assert sum(1 for c in calls if c.status.value.lower() == "failed") == 1


@pytest.mark.unit
def test_every_batch_failing_fails_the_run_with_the_providers_reason(world) -> None:
    rec = _Recorder(fail_when=lambda _p: True)
    world.provider.register("csf_score", rec)

    started = start_run(world.c, f"/csf/services/{world.svc_id}/run-ai", world.h)
    run = get_run(world.c, started["run_id"], world.h)

    assert run["status"] == "failed", run
    assert run["error_reason"] == "ai_call_failed"
    assert len(rec.payloads) == 33
