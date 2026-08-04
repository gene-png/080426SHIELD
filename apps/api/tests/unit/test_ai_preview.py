"""Redaction preview gate: POST /ai/preview (Sprint 5 T6).

Locks the two invariants that make preview safe and honest:
  1. The preview payload equals what a real Run-AI would egress (the redacted
     builder output) and the removed counts match the run's recorded counts.
  2. Preview writes NO ``llm_calls`` row and constructs NO provider (no egress);
     it is admin-only.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.csf.catalog import SUBCATEGORIES
from app.models.llm_call import LLMCall


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, FixtureProvider, sessionmaker]]:
    url = f"sqlite:///{tmp_path / 'shield-aiprev.db'}"
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
    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain
    from app.routes.csf import _llm_dep

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
    _seed = TestSession()
    tenant = _Client(legal_name="Test Tenant")
    _seed.add(tenant)
    _seed.flush()
    _seed.add(_ClientDomain(client_id=tenant.id, domain="example.com"))
    _seed.commit()
    cid = str(tenant.id)
    with TestClient(app, headers={"X-Client-Id": cid}) as c:
        yield c, provider, TestSession


def _admin_headers(c: TestClient) -> dict:
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}


def _bootstrap_csf(c: TestClient) -> tuple[dict, str, str]:
    h = _admin_headers(c)
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()[
        "id"
    ]
    c.post(f"/csf/services/{svc_id}/assessments", headers=h)
    c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})
    code = SUBCATEGORIES[0].code
    # Give one subcategory interview signal WITH an email so redaction has work.
    latest = c.get(f"/csf/services/{svc_id}/assessments/latest", headers=h).json()
    answer_id = next(a["id"] for a in latest["answers"] if a["subcategory_code"] == code)
    r = c.patch(
        f"/csf/answers/{answer_id}",
        headers=h,
        json={"maturity_tier": 3, "notes": "Reach the IAM owner at owner@acme.example."},
    )
    assert r.status_code == 200, r.text
    return h, svc_id, code


@pytest.mark.unit
def test_preview_equals_run_ai_egress_and_counts_match(app_client) -> None:
    """The redacted preview payload equals what run-ai actually egresses, and the
    preview's removed_counts equal the counts the run records."""
    c, provider, _ = app_client
    h, svc_id, _code = _bootstrap_csf(c)

    # Capture the post-redaction payload that reaches the provider on a real run.
    captured: dict = {}

    def _capture(payload: dict) -> LLMResponse:
        captured.clear()
        captured.update(payload)
        return LLMResponse('{"scores": []}')  # empty -> run-ai mutates no rows

    provider.register("csf_score", _capture)

    # Preview FIRST (before any run), so state is identical for both.
    prev = c.post("/ai/preview", json={"service_id": svc_id}, headers=h)
    assert prev.status_code == 200, prev.text
    body = prev.json()
    assert body["purpose"] == "csf_score"
    # Redaction actually happened: the seeded email was stripped.
    assert body["removed_counts"].get("email") == 1
    assert "owner@acme.example" not in str(body["payload"])

    # Now a real run: what egresses (minus the __purpose__ control key) must equal
    # the previewed payload.
    run = c.post(f"/csf/services/{svc_id}/run-ai", headers=h)
    assert run.status_code == 200, run.text
    egress = {k: v for k, v in captured.items() if not str(k).startswith("__")}
    assert body["payload"] == egress


@pytest.mark.unit
def test_preview_writes_no_llm_call_and_is_admin_only(app_client) -> None:
    c, _provider, TestSession = app_client
    h, svc_id, _code = _bootstrap_csf(c)

    # No fixture registered and no provider needed: preview must still work
    # (proves it never constructs a provider / egresses).
    prev = c.post("/ai/preview", json={"service_id": svc_id}, headers=h)
    assert prev.status_code == 200, prev.text

    # Zero llm_calls rows written by the preview.
    with TestSession() as db:
        count = db.execute(select(func.count()).select_from(LLMCall)).scalar_one()
    assert count == 0, "preview must not write an llm_calls row"

    # Admin-only: a client-role user under the tenant domain is forbidden.
    client_user = c.post(
        "/auth/register",
        json={
            "email": "user@example.com",
            "password": "correct horse battery staple!",
            "display_name": "U",
        },
    )
    ch = {"Authorization": f"Bearer {client_user.json()['tokens']['access_token']}"}
    forbidden = c.post("/ai/preview", json={"service_id": svc_id}, headers=ch)
    assert forbidden.status_code == 403, forbidden.text


@pytest.mark.unit
def test_preview_counts_match_recorded_run(app_client) -> None:
    """The redacted_counts a run records equal the preview's removed_counts."""
    c, provider, TestSession = app_client
    h, svc_id, _code = _bootstrap_csf(c)
    provider.register_static("csf_score", LLMResponse('{"scores": []}'))

    prev = c.post("/ai/preview", json={"service_id": svc_id}, headers=h).json()
    assert c.post(f"/csf/services/{svc_id}/run-ai", headers=h).status_code == 200

    with TestSession() as db:
        row = db.execute(select(LLMCall)).scalars().one()
    assert (row.redacted_counts or {}) == prev["removed_counts"]


@pytest.mark.unit
def test_preview_404_for_missing_assessment(app_client) -> None:
    c, _provider, _ = app_client
    h = _admin_headers(c)
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()[
        "id"
    ]
    # No assessment created yet -> same typed 404 run-ai raises.
    r = c.post("/ai/preview", json={"service_id": svc_id}, headers=h)
    assert r.status_code == 404, r.text
