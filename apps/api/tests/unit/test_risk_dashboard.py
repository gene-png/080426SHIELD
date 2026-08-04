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
