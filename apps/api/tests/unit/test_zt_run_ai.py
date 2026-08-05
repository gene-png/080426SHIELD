"""zt_score Run-AI: current+target suggestions, validation, lock-skip (Work Order D3)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, FixtureProvider]]:
    url = f"sqlite:///{tmp_path / 'shield-ztai.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app
    from app.routes.zt import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    provider = FixtureProvider()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
    with TestClient(app) as c:
        yield c, provider


def _admin_service(c: TestClient, kind: str) -> tuple[dict, str, str]:
    admin = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    bearer = admin.json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Acme"},
    ).json()["id"]
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/zt/services", headers=h, json={"kind": kind, "title": "Acme ZT"})
    return h, svc.json()["id"], cid


@pytest.mark.unit
def test_zt_run_ai_applies_current_and_target(app_client) -> None:
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    provider.register_static(
        "zt_score",
        LLMResponse(
            '{"capabilities": [{"code": "' + code + '", "current": 2, "target": 4}],'
            ' "pillar_narratives": {"ID": "Identity is partial."},'
            ' "executive_summary": "draft", "roadmap_summary": "12-month plan"}'
        ),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    row = next(x for x in body["answers"] if x["capability_code"] == code)
    assert row["maturity_stage"] == 2
    assert row["target_stage"] == 4
    fields = {ch["field"] for ch in body["changed"] if ch["capability_code"] == code}
    assert {"maturity_stage", "target_stage"} <= fields
    assert body["pillar_narratives"]["ID"] == "Identity is partial."
    assert body["executive_summary"] == "draft"


@pytest.mark.unit
def test_zt_run_ai_clamps_out_of_range_for_dod(app_client) -> None:
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_dod")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]
    # DoD max stage is 3; a suggested 4 is out of range and must be ignored.
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 3, "target": 4}]}'),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    row = next(x for x in r.json()["answers"] if x["capability_code"] == code)
    assert row["maturity_stage"] == 3
    assert row["target_stage"] is None  # 4 rejected for DoD


@pytest.mark.unit
def test_build_roadmap_front_loads_priority() -> None:
    from app.zt.scoring import Gap, build_roadmap

    def _gap(code: str, prio: float) -> Gap:
        return Gap(
            code=code,
            pillar_code="ID",
            pillar_name="Identity",
            name=code,
            outcome="o",
            current_stage=1,
            target_stage=3,
            gap_size=2,
            priority_score=prio,
            notes=None,
        )

    gaps = [_gap(f"C{i:02d}", 100 - i) for i in range(24)]  # priority-descending
    rm = build_roadmap(gaps, horizon_months=12)
    assert len(rm) == 24
    assert all(1 <= it.month <= 12 for it in rm)
    assert rm[0].month == 1  # highest priority first
    assert rm[-1].month == 12  # lowest priority last
    assert build_roadmap([]) == ()


@pytest.mark.unit
def test_gap_endpoint_respects_per_capability_target_and_returns_roadmap(app_client) -> None:
    c, _ = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    ans = a.json()["answers"][0]
    code, ans_id = ans["capability_code"], ans["id"]
    # current 1, per-capability target 4 -> a gap to target 4.
    c.patch(f"/zt/answers/{ans_id}", headers=h, json={"maturity_stage": 1, "target_stage": 4})
    g = c.get(f"/zt/services/{svc_id}/gap-analysis", headers=h)
    assert g.status_code == 200, g.text
    body = g.json()
    gap = next(x for x in body["gaps"] if x["code"] == code)
    assert gap["target_stage"] == 4  # per-capability target, not the default 3
    assert any(it["code"] == code for it in body["roadmap"])


@pytest.mark.unit
def test_zt_run_ai_skips_locked(app_client) -> None:
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    ans = a.json()["answers"][0]
    code, ans_id = ans["capability_code"], ans["id"]
    c.patch(f"/zt/answers/{ans_id}", headers=h, json={"locked": True})
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 3, "target": 4}]}'),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    row = next(x for x in r.json()["answers"] if x["capability_code"] == code)
    assert row["maturity_stage"] is None
    assert all(ch["capability_code"] != code for ch in r.json()["changed"])


# --------------------------------------------------------------------------- #
# Fixture output must never overwrite what a client submitted.
#
# The 2026-08-04 review pressed Run AI on a Zero Trust workspace with no API key
# loaded. Fixture mode returned canned demo values and wrote them straight over
# a real client self-assessment: average maturity fell 2.14 -> 1.49 and the
# Identity pillar 3.00 -> 1. `locked` did not help — it records a consultant's
# choice, not provenance — so migration 0035 added `answer_source`.
# --------------------------------------------------------------------------- #


def _submitted_self_assessment(c, h, svc_id: str) -> tuple[str, str]:
    """Answer one capability as the client and submit. Returns (code, answer id)."""
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    ans = a.json()["answers"][0]
    code, ans_id = ans["capability_code"], ans["id"]
    c.patch(f"/zt/answers/{ans_id}", headers=h, json={"maturity_stage": 3})
    submitted = c.post(
        f"/zt/services/{svc_id}/self-assessment/submit",
        headers=h,
        json={"target_stage": 3},
    )
    assert submitted.status_code == 200, submitted.text
    return code, ans_id


@pytest.mark.unit
def test_fixture_run_ai_leaves_client_submitted_answers_untouched(app_client) -> None:
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    code, _ = _submitted_self_assessment(c, h, svc_id)

    # Fixture provider = offline demo output.
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 1, "target": 2}]}'),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    row = next(x for x in body["answers"] if x["capability_code"] == code)
    assert row["maturity_stage"] == 3, "canned output overwrote a client-submitted answer"
    assert all(ch["capability_code"] != code for ch in body["changed"])
    # The skip is reported, not silent.
    assert body["preserved_client_answers"] == 1


@pytest.mark.unit
def test_submit_stamps_client_provenance(app_client) -> None:
    c, _ = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    code, ans_id = _submitted_self_assessment(c, h, svc_id)

    from app.models.zt_assessment import ZtAnswer

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as check:
        row = check.execute(select(ZtAnswer).where(ZtAnswer.capability_code == code)).scalar_one()
        assert row.answer_source == "client"


@pytest.mark.unit
def test_live_run_ai_may_update_client_answers(app_client, monkeypatch) -> None:
    """A LIVE run drafting over a client's self-assessment is the consultant
    workflow — the diff is shown for review. Only fixture output is refused."""
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    code, _ = _submitted_self_assessment(c, h, svc_id)

    # Present the same canned response as if it came from a real provider.
    monkeypatch.setattr(type(provider), "name", "anthropic", raising=False)
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 1, "target": 2}]}'),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    row = next(x for x in body["answers"] if x["capability_code"] == code)
    assert row["maturity_stage"] == 1
    assert body["preserved_client_answers"] == 0
