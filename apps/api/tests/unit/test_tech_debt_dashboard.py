"""Client-facing Tech Debt (software portfolio) dashboard endpoint (D-035).

GET /clients/{client_id}/tech-debt/{service_id}/dashboard returns the portfolio
spend/sprawl/redundancy/savings rollup + full inventory, gated on a released
deliverable. Uses the FixtureProvider extract flow to seed real capability items.
"""

from __future__ import annotations

import io
import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.storage.local import LocalFilesystemStorage


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, FixtureProvider]]:
    db_path = tmp_path / "shield-td-dash.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    storage = LocalFilesystemStorage(tmp_path / "storage")
    provider = FixtureProvider()
    llm = LLMClient(provider)

    from app.db.session import get_db
    from app.main import create_app
    from app.routes.artifacts import _storage_dep
    from app.routes.tech_debt import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_storage_dep] = lambda: storage
    app.dependency_overrides[_llm_dep] = lambda: llm

    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain

    _seed = TestSession()
    _tenant = _Client(legal_name="Test Tenant")
    _seed.add(_tenant)
    _seed.flush()
    _seed.add(_ClientDomain(client_id=_tenant.id, domain="example.com"))
    _seed.commit()
    _cid = str(_tenant.id)
    _seed.close()

    with TestClient(app, headers={"X-Client-Id": _cid}) as c:
        yield c, provider


def _register(c: TestClient, email: str) -> dict:
    r = c.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple!",
            "display_name": email.split("@")[0],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


_ITEMS = [
    {
        "name": "CrowdStrike Falcon",
        "vendor": "CrowdStrike",
        "category": "EDR",
        "function": "Endpoint detection",
        "annual_cost_usd": 195000,
        "license_count": 1500,
    },
    {
        "name": "Defender for Endpoint",
        "vendor": "Microsoft",
        "category": "EDR",
        "function": "Endpoint detection",
        "annual_cost_usd": 0,
        "license_count": 1200,
    },
    {
        "name": "CyberArk",
        "vendor": "CyberArk",
        "category": "PAM",
        "function": "Privileged access",
        "annual_cost_usd": 95000,
        "license_count": 200,
    },
    {
        "name": "BeyondTrust",
        "vendor": "BeyondTrust",
        "category": "PAM",
        "function": "Vendor remote access",
        "annual_cost_usd": 38000,
        "license_count": 150,
    },
    {
        "name": "Splunk ES",
        "vendor": "Splunk",
        "category": "SIEM",
        "function": "SOC platform",
        "annual_cost_usd": 380000,
        "license_count": None,
    },
]


def _seed_release(c: TestClient, provider: FixtureProvider, bearer: str, *, release: bool) -> str:
    provider.register(
        "extract.capabilities",
        lambda _p: LLMResponse(
            content=json.dumps(
                {
                    "items": [
                        {**it, "notes": None, "confidence_pct": 90, "source_row_index": i}
                        for i, it in enumerate(_ITEMS)
                    ]
                }
            )
        ),
    )
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = c.post(
        "/tech-debt/services", headers=h, json={"kind": "tech_debt", "title": "Atlas - Tech Debt"}
    ).json()["id"]
    artifact_id = c.post(
        "/artifacts",
        headers=h,
        files={"file": ("inv.csv", io.BytesIO(b"Tool,Cost\nx,1\n"), "text/csv")},
    ).json()["id"]
    ext = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers=h,
        json={"artifact_id": artifact_id},
    ).json()
    list_id = ext["id"]
    # Cut the two duplicate-category tools; keep the rest.
    for item in ext["items"]:
        disp = "cut" if item["name"] in ("BeyondTrust", "Defender for Endpoint") else "keep"
        c.patch(
            f"/tech-debt/capability-items/{item['id']}",
            headers=h,
            json={"disposition": disp},
        )
    c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=h)
    deliv_id = c.post(f"/tech-debt/services/{svc_id}/deliverables/finalize", headers=h).json()["id"]
    if release:
        rel = c.post(f"/tech-debt/deliverables/{deliv_id}/release", headers=h)
        assert rel.status_code == 200, rel.text
    return svc_id


@pytest.mark.unit
def test_tech_debt_dashboard_released(app_client) -> None:
    c, provider = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, provider, bearer_admin, release=True)

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/tech-debt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["total_applications"] == 5
    assert b["annual_spend_usd"] == 708000.0  # 195k + 0 + 95k + 38k + 380k
    assert b["identified_savings_usd"] == 38000.0  # BeyondTrust cut (Defender cut = 0)
    assert b["redundant_category_count"] == 2  # EDR + PAM
    assert len(b["items"]) == 5
    # Spend-by-category is sorted desc; SIEM (380k) leads.
    assert b["spend_by_category"][0]["category"] == "SIEM"


@pytest.mark.unit
def test_tech_debt_dashboard_unreleased_404(app_client) -> None:
    c, provider = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, provider, bearer_admin, release=False)

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/tech-debt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["reason"] == "dashboard_not_released"


@pytest.mark.unit
def test_tech_debt_release_flips_the_capability_list_and_finalize_still_works(app_client) -> None:
    """W4 for Tech Debt, plus the break it would otherwise have shipped.

    Two facts in one test, because they are only dangerous together:

    1. Releasing flips `CapabilityList` to RELEASED, which makes
       `_editable_list_or_404` live — before W4 nothing outside `seed_demo.py`
       ever assigned that status, so the lock was dead code.
    2. Finalizing a SECOND deliverable version still works afterwards. The gate
       was `!= APPROVED` here while csf/zt/attack accept APPROVED or RELEASED,
       so W4 would have made a released tech-debt service unable to produce
       another report — and no test or spec covered it, because the only
       release-then-finalize coverage (`s17-documents`) runs on CSF.
    """
    c, provider = app_client
    bearer_admin = _register(c, "w4-td@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer_admin}"}
    svc_id = _seed_release(c, provider, bearer_admin, release=True)

    latest = c.get(f"/tech-debt/services/{svc_id}/capability-lists/latest", headers=h)
    assert latest.status_code == 200, latest.text
    assert latest.json()["status"] == "released"

    again = c.post(f"/tech-debt/services/{svc_id}/deliverables/finalize", headers=h)
    assert again.status_code == 201, again.text
    assert again.json()["version"] == 2
