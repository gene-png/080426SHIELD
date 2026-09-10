"""Client-facing Risk Register dashboard endpoint (D-035).

GET /clients/{client_id}/risk/dashboard returns the 5x5 likelihood x impact
matrix + tier/axis/action mix + full register to the CLIENT, gated on the
register being finalized (exported). Client-level (not per-service).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.storage.local import LocalFilesystemStorage


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "shield-risk-dash.db"
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

    from app.db.session import get_db
    from app.main import create_app
    from app.routes.artifacts import _storage_dep

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_storage_dep] = lambda: storage

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
        yield c


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


def _seed_attack_and_zt(c: TestClient, bearer: str, cid: str) -> None:
    """Unlock the risk gate: an ATT&CK gap + a low ZT answer."""
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    asvc = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "ATT&CK"}
    ).json()
    a = c.post(f"/attack/services/{asvc['id']}/assessments", headers=h).json()
    cov = a["coverage"][0]
    c.patch(f"/attack/coverage/{cov['id']}", headers=h, json={"status": "gap"})

    zsvc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "ZT"}).json()
    za = c.post(f"/zt/services/{zsvc['id']}/assessments", headers=h).json()
    zans = za["answers"][0]
    c.patch(f"/zt/answers/{zans['id']}", headers=h, json={"maturity_stage": 1})
    # Approve both -- #237. Synthesis reads only APPROVED/RELEASED assessments,
    # because what it produces is exported under the client's name. This seed
    # left them DRAFT and the generate below used to succeed.
    assert c.post(f"/attack/assessments/{a['id']}/approve", headers=h).status_code == 200
    assert c.post(f"/zt/assessments/{za['id']}/approve", headers=h).status_code == 200


def _generate_and_finalize(c: TestClient, bearer: str, cid: str) -> None:
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    _seed_attack_and_zt(c, bearer, cid)
    g = c.post(f"/risk/clients/{cid}/register/generate", headers=h)
    assert g.status_code == 201, g.text
    ex = c.post(f"/risk/clients/{cid}/register/export", headers=h)
    assert ex.status_code in (200, 201), ex.text


@pytest.mark.unit
def test_risk_dashboard_finalized_returns_matrix(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    # The admin operates on the client's tenant.
    c.headers["X-Client-Id"] = client_id
    _generate_and_finalize(c, bearer_admin, client_id)

    r = c.get(
        f"/clients/{client_id}/risk/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["total_entries"] >= 1
    assert len(b["matrix"]) == 25  # full 5x5 grid
    assert set(b["matrix"][0].keys()) == {"likelihood", "impact", "tier", "count"}
    assert isinstance(b["tier_counts"], dict)
    assert len(b["entries"]) == b["total_entries"]


@pytest.mark.unit
def test_generating_a_new_version_does_not_retract_the_delivered_one(app_client) -> None:
    """#123. Clicking Generate must not take the client's dashboard away.

    The resolver took the HIGHEST-version register and then 404'd if that one
    was unfinalized. `generate` always mints the next version and only `export`
    sets `finalized_at` -- so the moment a consultant clicked Generate to
    refresh a delivered register, the client's dashboard 404'd with
    "No finalized Risk Register for your organization yet". One existed. They
    had been reading it a minute earlier.

    It also removed the Risk link from Results, because `results/page.tsx`
    probes this endpoint to set `hasRiskDashboard`. And nothing told anyone: it
    stayed gone for as long as the review took.

    Same root cause as #114 -- the numbers must come from the record being
    LABELLED, not from whatever row is newest.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]
    ch = {"Authorization": f"Bearer {bearer_client}"}
    ah = {"Authorization": f"Bearer {bearer_admin}", "X-Client-Id": client_id}

    c.headers["X-Client-Id"] = client_id
    _generate_and_finalize(c, bearer_admin, client_id)

    delivered = c.get(f"/clients/{client_id}/risk/dashboard", headers=ch)
    assert delivered.status_code == 200, delivered.text
    delivered_version = delivered.json()["version"]
    delivered_total = delivered.json()["total_entries"]

    # The consultant refreshes the register. v2 exists and is NOT exported.
    g = c.post(f"/risk/clients/{client_id}/register/generate", headers=ah)
    assert g.status_code == 201, g.text
    assert g.json()["version"] == delivered_version + 1

    # The client must still see the version they were delivered.
    still = c.get(f"/clients/{client_id}/risk/dashboard", headers=ch)
    assert still.status_code == 200, (
        "generating a new version retracted the delivered one: " + still.text
    )
    assert still.json()["version"] == delivered_version
    assert still.json()["total_entries"] == delivered_total

    # And exporting v2 hands it over.
    ex = c.post(f"/risk/clients/{client_id}/register/export", headers=ah)
    assert ex.status_code in (200, 201), ex.text
    now = c.get(f"/clients/{client_id}/risk/dashboard", headers=ch)
    assert now.status_code == 200, now.text
    assert now.json()["version"] == delivered_version + 1


@pytest.mark.unit
def test_an_unfinalized_v2_does_not_leak_before_export(app_client) -> None:
    """The other direction, so the fix cannot overshoot.

    Serving the latest FINALIZED register must not become serving the latest
    register: an in-progress v2 has not been handed over and must not reach the
    client until export. The assertion is on the VERSION rather than on the
    status code -- a 200 alone would pass whichever version were served, which
    is exactly the confusion #123 is about.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]
    ah = {"Authorization": f"Bearer {bearer_admin}", "X-Client-Id": client_id}

    c.headers["X-Client-Id"] = client_id
    _generate_and_finalize(c, bearer_admin, client_id)
    assert c.post(f"/risk/clients/{client_id}/register/generate", headers=ah).status_code == 201

    r = c.get(
        f"/clients/{client_id}/risk/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200
    assert r.json()["version"] == 1, "an unexported v2 must not be served"


@pytest.mark.unit
def test_risk_dashboard_unfinalized_is_404(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    c.headers["X-Client-Id"] = client_id
    # Generate but do NOT export (so finalized_at stays null).
    _seed_attack_and_zt(c, bearer_admin, client_id)
    g = c.post(
        f"/risk/clients/{client_id}/register/generate",
        headers={"Authorization": f"Bearer {bearer_admin}", "X-Client-Id": client_id},
    )
    assert g.status_code == 201, g.text

    r = c.get(
        f"/clients/{client_id}/risk/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["reason"] == "dashboard_not_released"
