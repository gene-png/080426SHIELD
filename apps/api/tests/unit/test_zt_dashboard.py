"""Client-facing Zero Trust maturity dashboard endpoint (D-035).

GET /clients/{client_id}/zt/{service_id}/dashboard returns the current-vs-target
per-pillar maturity rollup to the CLIENT, gated on the service having a released
deliverable. Reuses the same admin approve -> finalize -> release preamble the
other ZT tests use.
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
    db_path = tmp_path / "shield-zt-dash.db"
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


def _seed_release(c: TestClient, bearer: str, *, release: bool) -> str:
    """Open a CISA ZT service, set every answer to current=2/target=4, approve,
    finalize, optionally release. Returns the service id."""
    svc_id = c.post(
        "/zt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"kind": "zero_trust_cisa", "title": "Atlas - Zero Trust"},
    ).json()["id"]
    assessment = c.post(
        f"/zt/services/{svc_id}/assessments",
        headers={"Authorization": f"Bearer {bearer}"},
    ).json()
    for ans in assessment["answers"]:
        c.patch(
            f"/zt/answers/{ans['id']}",
            headers={"Authorization": f"Bearer {bearer}"},
            json={"maturity_stage": 2, "target_stage": 4},
        )
    c.post(
        f"/zt/assessments/{assessment['id']}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    deliv_id = c.post(
        f"/zt/services/{svc_id}/deliverables/finalize",
        headers={"Authorization": f"Bearer {bearer}"},
    ).json()["id"]
    if release:
        rel = c.post(
            f"/zt/deliverables/{deliv_id}/release",
            headers={"Authorization": f"Bearer {bearer}"},
        )
        assert rel.status_code == 200, rel.text
    return svc_id


@pytest.mark.unit
def test_zt_dashboard_released_returns_pillars(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, bearer_admin, release=True)

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["framework"] == "cisa_ztmm_2_0"
    # current stage 2 of 4 -> 50%, "Initial"; target stage 4 -> 100%, "Optimal".
    assert body["current_pct"] == 50.0
    assert body["target_pct"] == 100.0
    assert body["current_label"] == "Initial"
    assert body["target_label"] == "Optimal"
    assert len(body["pillars"]) >= 5  # CISA has 5 pillars + cross-cutting
    p0 = body["pillars"][0]
    assert p0["current_pct"] == 50.0
    assert p0["target_pct"] == 100.0
    assert p0["gap_pct"] == 50.0
    assert body["largest_gap_pct"] == 50.0


@pytest.mark.unit
def test_zt_dashboard_unreleased_is_404_typed(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, bearer_admin, release=False)

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["reason"] == "dashboard_not_released"


# --- Issue 4: admin preview before release -----------------------------------
#
# Finalize previously produced a PDF and an XLSX and nothing else, so an analyst
# released a dashboard to the client having never seen it. The admin now sees
# the SAME dashboard as soon as the deliverable is finalized; the client's gate
# is unchanged (still release-only, covered by the test above).


@pytest.mark.unit
def test_admin_sees_the_dashboard_once_finalized_before_release(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, bearer_admin, release=False)

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["released"] is False, "an unreleased dashboard must be labelled a preview"
    # The figures are real, not placeholders — same engine output as post-release.
    assert body["current_pct"] == 50.0
    assert body["target_pct"] == 100.0


@pytest.mark.unit
def test_admin_preview_matches_the_released_client_view_exactly(app_client) -> None:
    """Parity: preview and client view run the same builder, so the only field
    that may differ is the `released` flag (and its timestamp)."""
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, bearer_admin, release=False)
    c.headers["X-Client-Id"] = client_id

    preview = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    ).json()

    deliv_id = c.get(
        f"/zt/services/{svc_id}/deliverables/latest",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    ).json()["id"]
    rel = c.post(
        f"/zt/deliverables/{deliv_id}/release",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    )
    assert rel.status_code == 200, rel.text

    released = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    ).json()

    assert released["released"] is True
    volatile = {"released", "released_at"}
    assert {k: v for k, v in preview.items() if k not in volatile} == {
        k: v for k, v in released.items() if k not in volatile
    }, "admin preview and client view must not diverge"


@pytest.mark.unit
def test_client_still_cannot_see_a_finalized_but_unreleased_dashboard(app_client) -> None:
    """The consultant-in-the-loop gate is unchanged for clients."""
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, bearer_admin, release=False)
    c.headers["X-Client-Id"] = client_id

    assert (
        c.get(
            f"/clients/{client_id}/zt/{svc_id}/dashboard",
            headers={"Authorization": f"Bearer {bearer_admin}"},
        ).status_code
        == 200
    ), "precondition: the admin can preview it"

    r = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["reason"] == "dashboard_not_released"
