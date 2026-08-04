"""End-to-end auth-route tests against an ephemeral SQLite + FastAPI TestClient."""

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
    db_path = tmp_path / "shield-auth.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url

    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    test_engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)

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

    with TestClient(app) as c:
        yield c


def _register(
    client: TestClient,
    email: str = "first@example.com",
    password: str = "correct horse battery staple!",
) -> dict:
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "display_name": "Test User",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.unit
def test_first_registrant_becomes_admin_primary_poc(app_client: TestClient) -> None:
    body = _register(app_client)
    assert body["is_primary_poc"] is True
    assert body["user"]["role"] == "admin"
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]
    assert body["tokens"]["access_expires_at"]


@pytest.mark.unit
def test_second_registrant_joins_by_approved_domain(app_client: TestClient) -> None:
    # First user is the bootstrap admin; they create the org + approve a domain.
    admin = _register(app_client, email="first@acme.com")
    admin_bearer = admin["tokens"]["access_token"]
    created = app_client.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {admin_bearer}"},
        json={"legal_name": "Acme Corp"},
    )
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    dom = app_client.post(
        f"/admin/clients/{cid}/domains",
        headers={"Authorization": f"Bearer {admin_bearer}"},
        json={"domain": "acme.com"},
    )
    assert dom.status_code == 201, dom.text
    # A second user at the approved domain auto-joins that client.
    body = _register(app_client, email="second@acme.com")
    assert body["is_primary_poc"] is False
    assert body["user"]["role"] == "client"
    assert body["user"]["client_id"] == cid


@pytest.mark.unit
def test_register_generic_provider_gets_own_client(app_client: TestClient) -> None:
    # D-034: personal-email signups are ALLOWED and get their own private org
    # (never grouped by the generic domain).
    _register(app_client, email="first@acme.com")  # bootstrap admin
    body = _register(app_client, email="someone@gmail.com")
    assert body["is_primary_poc"] is True
    assert body["user"]["role"] == "client"
    assert body["user"]["client_id"] is not None


@pytest.mark.unit
def test_two_generic_users_get_separate_clients(app_client: TestClient) -> None:
    # Two personal-email signups must NOT share a workspace (no gmail.com
    # grouping) — each gets an isolated org.
    _register(app_client, email="admin@example.com")  # bootstrap admin
    a = _register(app_client, email="a@gmail.com")
    b = _register(app_client, email="b@gmail.com")
    assert a["user"]["client_id"] is not None
    assert b["user"]["client_id"] is not None
    assert a["user"]["client_id"] != b["user"]["client_id"]


@pytest.mark.unit
def test_register_new_company_domain_provisions_client(app_client: TestClient) -> None:
    # D-034: an unknown COMPANY domain auto-provisions a new org (no admin
    # pre-approval needed); the registrant is its primary contact.
    _register(app_client, email="admin@example.com")  # bootstrap admin
    body = _register(app_client, email="newhire@unregistered-co.com")
    assert body["is_primary_poc"] is True
    assert body["user"]["role"] == "client"
    assert body["user"]["client_id"] is not None


@pytest.mark.unit
def test_second_user_same_new_domain_joins_same_client(app_client: TestClient) -> None:
    # Coworkers on the same company domain group into ONE org: the first creates
    # it (and maps the domain), later users auto-join as non-primary members.
    _register(app_client, email="admin@example.com")  # bootstrap admin
    a = _register(app_client, email="a@acme-newco.com")
    b = _register(app_client, email="b@acme-newco.com")
    assert a["is_primary_poc"] is True
    assert b["is_primary_poc"] is False
    assert a["user"]["client_id"] == b["user"]["client_id"]


@pytest.mark.unit
def test_duplicate_registration_rejected(app_client: TestClient) -> None:
    _register(app_client)
    r = app_client.post(
        "/auth/register",
        json={
            "email": "first@example.com",
            "password": "correct horse battery staple!",
            "display_name": "Test User",
        },
    )
    assert r.status_code == 409


@pytest.mark.unit
def test_password_policy_enforced_on_register(app_client: TestClient) -> None:
    r = app_client.post(
        "/auth/register",
        json={
            "email": "first@example.com",
            "password": "short",
            "display_name": "Test User",
        },
    )
    assert r.status_code == 422


@pytest.mark.unit
def test_login_with_correct_password(app_client: TestClient) -> None:
    _register(app_client)
    r = app_client.post(
        "/auth/login",
        json={"email": "first@example.com", "password": "correct horse battery staple!"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"]


@pytest.mark.unit
def test_login_wrong_password_returns_401(app_client: TestClient) -> None:
    _register(app_client)
    r = app_client.post(
        "/auth/login",
        json={"email": "first@example.com", "password": "wrong horse battery staple!"},
    )
    assert r.status_code == 401


@pytest.mark.unit
def test_login_unknown_user_returns_401_not_404(app_client: TestClient) -> None:
    # Account-existence oracle defense (OWASP A07).
    r = app_client.post(
        "/auth/login",
        json={"email": "ghost@example.com", "password": "correct horse battery staple!"},
    )
    assert r.status_code == 401


@pytest.mark.unit
def test_lockout_after_max_failed_attempts(app_client: TestClient) -> None:
    _register(app_client)
    # 10 wrong attempts → next attempt should hit 423 LOCKED, even if password
    # is correct.
    for _ in range(10):
        app_client.post(
            "/auth/login",
            json={"email": "first@example.com", "password": "wrong horse battery staple!"},
        )
    r = app_client.post(
        "/auth/login",
        json={"email": "first@example.com", "password": "correct horse battery staple!"},
    )
    assert r.status_code == 423


@pytest.mark.unit
def test_me_returns_current_user(app_client: TestClient) -> None:
    body = _register(app_client)
    access = body["tokens"]["access_token"]
    r = app_client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == "first@example.com"
    assert me["role"] == "admin"


@pytest.mark.unit
def test_me_rejects_missing_token(app_client: TestClient) -> None:
    r = app_client.get("/auth/me")
    assert r.status_code == 401


@pytest.mark.unit
def test_me_rejects_refresh_token(app_client: TestClient) -> None:
    body = _register(app_client)
    refresh = body["tokens"]["refresh_token"]
    r = app_client.get("/auth/me", headers={"Authorization": f"Bearer {refresh}"})
    assert r.status_code == 401


@pytest.mark.unit
def test_refresh_issues_new_pair(app_client: TestClient) -> None:
    body = _register(app_client)
    refresh = body["tokens"]["refresh_token"]
    r = app_client.post("/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    new = r.json()
    assert new["access_token"]
    assert new["refresh_token"]


@pytest.mark.unit
def test_refresh_rejects_access_token(app_client: TestClient) -> None:
    body = _register(app_client)
    access = body["tokens"]["access_token"]
    r = app_client.post("/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 401


@pytest.mark.unit
def test_logout_audits_and_returns_204(app_client: TestClient) -> None:
    body = _register(app_client)
    access = body["tokens"]["access_token"]
    r = app_client.post("/auth/logout", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 204
