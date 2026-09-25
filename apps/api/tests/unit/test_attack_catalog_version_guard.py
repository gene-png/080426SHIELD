"""An assessment scored against another ATT&CK catalog is refused, never silently computed (#556).

Before the catalog was generated from MITRE's STIX, the heatmap, finalize and the
client dashboard kept only rows whose code was in the catalog
(`if r.technique_code in valid`). After a catalog change that silently turns an
old assessment into a percentage over a mixed, undisclosed set. Every test here
goes through the HTTP surface a caller reaches, because the guard is SELECTED at
the route, and a helper-level test would stay green with the call deleted
(CLAUDE.md, on guards).

Three states: current, a different recorded version, and unrecorded (NULL, every
row that predates migration 0052). The last two are refused, with messages that
say which.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session, sessionmaker

from app.attack.catalog import SOURCE_VERSION
from app.models.attack_assessment import AttackAssessment
from app.storage.local import LocalFilesystemStorage

pytestmark = pytest.mark.unit

REASON = "attack_catalog_mismatch"


@pytest.fixture()
def env(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    url = f"sqlite:///{tmp_path / 'shield-attack-version.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    Sess = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    storage = LocalFilesystemStorage(tmp_path / "storage")

    from app.db.session import get_db
    from app.main import create_app
    from app.models.client import Client
    from app.models.client_domain import ClientDomain
    from app.routes.artifacts import _storage_dep

    def override_get_db() -> Iterator[Session]:
        db = Sess()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_storage_dep] = lambda: storage
    s = Sess()
    tenant = Client(legal_name="Test Tenant")
    s.add(tenant)
    s.flush()
    s.add(ClientDomain(client_id=tenant.id, domain="example.com"))
    s.commit()
    cid = str(tenant.id)
    s.close()
    with TestClient(app, headers={"X-Client-Id": cid}) as c:
        yield c, Sess


def _register(c: TestClient, email: str) -> dict:
    r = c.post(
        "/auth/register",
        json={"email": email, "password": "correct horse battery staple!", "display_name": "x"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _auth(bearer: str) -> dict:
    return {"Authorization": f"Bearer {bearer}"}


def _service_and_assessment(c: TestClient, bearer: str) -> tuple[str, dict]:
    svc = c.post(
        "/attack/services",
        headers=_auth(bearer),
        json={"kind": "attack_coverage", "title": "ATT&CK Coverage"},
    ).json()["id"]
    r = c.post(f"/attack/services/{svc}/assessments", headers=_auth(bearer))
    assert r.status_code == 201, r.text
    return svc, r.json()


def _set_version(Sess: sessionmaker, assessment_id: str, value: str | None) -> None:
    with Sess() as s:
        s.execute(
            update(AttackAssessment)
            .where(AttackAssessment.id == uuid.UUID(assessment_id))
            .values(catalog_version=value)
        )
        s.commit()


def _refused(r) -> str:
    assert r.status_code == 409, r.text
    detail = r.json()
    body = detail.get("error", detail)
    assert body.get("reason") == REASON, detail
    return body["message"]


def test_a_new_assessment_records_the_current_catalog(env) -> None:
    c, _ = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    assert a["catalog_version"] == SOURCE_VERSION
    assert a["catalog_current"] is True
    assert c.get(f"/attack/services/{svc}/heatmap", headers=_auth(bearer)).status_code == 200


def test_an_unrecorded_catalog_refuses_heatmap_patch_and_run_ai(env) -> None:
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    _set_version(Sess, a["id"], None)

    latest = c.get(f"/attack/services/{svc}/assessments/latest", headers=_auth(bearer)).json()
    assert (latest["catalog_version"], latest["catalog_current"]) == (None, False)

    heat = _refused(c.get(f"/attack/services/{svc}/heatmap", headers=_auth(bearer)))
    assert "never recorded" in heat and f"v{SOURCE_VERSION}" in heat
    # A DRAFT names the two controls that exist for it, and only those.
    assert "Discard the draft and start a new assessment" in heat

    row = a["coverage"][0]["id"]
    _refused(c.patch(f"/attack/coverage/{row}", headers=_auth(bearer), json={"status": "covered"}))
    _refused(c.post(f"/attack/services/{svc}/run-ai", headers=_auth(bearer)))
    # Checked BEFORE the route's own `nothing_to_confirm`, so the reason says which.
    _refused(c.post(f"/attack/coverage/{row}/confirm-citations", headers=_auth(bearer)))


def test_a_different_recorded_version_is_named(env) -> None:
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    _set_version(Sess, a["id"], "15")
    msg = _refused(c.get(f"/attack/services/{svc}/heatmap", headers=_auth(bearer)))
    assert "scored against ATT&CK v15," in msg


def test_finalize_refuses_a_stale_approved_assessment_and_names_no_discard(env) -> None:
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    assert (
        c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer)).status_code == 200
    )
    _set_version(Sess, a["id"], None)
    msg = _refused(c.post(f"/attack/services/{svc}/deliverables/finalize", headers=_auth(bearer)))
    # No control starts a new version after approval (#558), so none is named.
    assert "Discard" not in msg and "rescored in a new assessment version" in msg


def test_the_client_dashboard_refuses_a_stale_release_in_client_words(env) -> None:
    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    assert (
        c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer)).status_code == 200
    )
    deliv = c.post(f"/attack/services/{svc}/deliverables/finalize", headers=_auth(bearer))
    assert deliv.status_code in (200, 201), deliv.text
    rel = c.post(f"/attack/deliverables/{deliv.json()['id']}/release", headers=_auth(bearer))
    assert rel.status_code == 200, rel.text

    client_id = client["user"]["client_id"]
    c.headers["X-Client-Id"] = client_id
    url = f"/clients/{client_id}/attack/{svc}/dashboard"
    client_bearer = client["tokens"]["access_token"]
    assert c.get(url, headers=_auth(client_bearer)).status_code == 200

    _set_version(Sess, a["id"], None)
    msg = _refused(c.get(url, headers=_auth(client_bearer)))
    assert "withheld until it is rescored" in msg
    assert "Discard" not in msg and "assessment" not in msg.lower()
