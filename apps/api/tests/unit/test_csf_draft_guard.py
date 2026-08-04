"""Draft-exists guard on POST /csf/services/{id}/assessments (SPRINT_2 T7).

Historically the route minted a fresh draft version on EVERY call, so a client
hammering "start assessment" produced unbounded v2, v3, v4… drafts. The guard
now returns the open draft idempotently (HTTP 200) instead of minting, and only
cuts a new version once the prior draft has moved on (submitted/approved).
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


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "shield-csf-draft-guard.db"
    url = f"sqlite:///{db_path}"
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

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

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


def _open_service(c: TestClient, bearer: str) -> str:
    r = c.post(
        "/csf/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"kind": "nist_csf", "title": "NIST CSF"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _post_assessment(c: TestClient, bearer: str, svc_id: str):
    return c.post(
        f"/csf/services/{svc_id}/assessments",
        headers={"Authorization": f"Bearer {bearer}"},
    )


@pytest.mark.unit
def test_first_post_mints_v1_draft(app_client) -> None:
    """Not-exists path: with no prior assessment, POST mints v1 (201)."""
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc_id = _open_service(c, bearer)

    r = _post_assessment(c, bearer, svc_id)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 1
    assert body["status"] == "draft"


@pytest.mark.unit
def test_second_post_returns_open_draft_without_minting(app_client) -> None:
    """Exists path: an open draft is returned idempotently (200), NOT re-minted."""
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc_id = _open_service(c, bearer)

    first = _post_assessment(c, bearer, svc_id)
    assert first.status_code == 201, first.text
    v1 = first.json()

    second = _post_assessment(c, bearer, svc_id)
    # The guard returns the existing draft with a 200 (idempotent), same row.
    assert second.status_code == 200, second.text
    v2 = second.json()
    assert v2["id"] == v1["id"]
    assert v2["version"] == 1
    assert v2["status"] == "draft"

    # Hammering it a third time is still idempotent — no unbounded versions.
    third = _post_assessment(c, bearer, svc_id)
    assert third.status_code == 200, third.text
    assert third.json()["version"] == 1


@pytest.mark.unit
def test_new_version_minted_after_prior_draft_closed(app_client) -> None:
    """The guard is scoped to DRAFT: once the prior draft is approved (no longer
    an open draft), the next POST cuts a fresh v2 (201)."""
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc_id = _open_service(c, bearer)

    first = _post_assessment(c, bearer, svc_id)
    assert first.status_code == 201, first.text
    assessment_id = first.json()["id"]

    approved = c.post(
        f"/csf/assessments/{assessment_id}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    # Prior draft is closed, so a new cycle mints v2.
    nxt = _post_assessment(c, bearer, svc_id)
    assert nxt.status_code == 201, nxt.text
    body = nxt.json()
    assert body["version"] == 2
    assert body["status"] == "draft"
    assert body["id"] != assessment_id
