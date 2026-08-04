"""Email verification + password reset routes (Sprint 6 T5, D-028).

Runs against an ephemeral SQLite + FastAPI TestClient, mirroring
test_mfa_routes.py. Email delivery is OFF by default in tests, so the raw
token (which only ever lives in the email link) is captured by monkeypatching
the sender helpers the route calls — this exercises the real token flow without
needing MailHog.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def db_url(tmp_path) -> str:
    url = f"sqlite:///{tmp_path / 'shield-email.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    return url


@pytest.fixture()
def sessionmaker_for(db_url: str):
    engine = create_engine(db_url, future=True)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture()
def sent(monkeypatch) -> list[dict]:
    """Capture the raw tokens the routes would email (delivery stays off)."""
    box: list[dict] = []

    def _capture_verify(*, to: str, token: str) -> None:
        box.append({"kind": "verify", "to": to, "token": token})

    def _capture_reset(*, to: str, token: str) -> None:
        box.append({"kind": "reset", "to": to, "token": token})

    monkeypatch.setattr("app.routes.auth.send_verification_email", _capture_verify)
    monkeypatch.setattr("app.routes.auth.send_password_reset_email", _capture_reset)
    return box


@pytest.fixture()
def app_client(sessionmaker_for) -> Iterator[TestClient]:
    from app.db.session import get_db
    from app.main import create_app

    def override_get_db() -> Iterator[Session]:
        db = sessionmaker_for()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c


_PASSWORD = "correct horse battery staple!"
_NEW_PASSWORD = "brand new battery staple 99!"


def _register(client: TestClient, email: str = "first@example.com") -> dict:
    r = client.post(
        "/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "Test User"},
    )
    assert r.status_code == 201, r.text
    return r.json()


# -----------------------------------------------------------------------------
# Verification
# -----------------------------------------------------------------------------


@pytest.mark.unit
def test_register_issues_verification_token(app_client, sent) -> None:
    _register(app_client)
    assert len(sent) == 1
    assert sent[0]["kind"] == "verify"
    assert sent[0]["to"] == "first@example.com"
    assert sent[0]["token"]


@pytest.mark.unit
def test_verify_email_sets_verified(app_client, sent, sessionmaker_for) -> None:
    _register(app_client)
    token = sent[0]["token"]
    r = app_client.post("/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    assert r.json()["email_verified"] is True

    from app.models.user import User

    with sessionmaker_for() as db:
        user = db.execute(select(User).where(User.email == "first@example.com")).scalar_one()
        assert user.email_verified_at is not None


@pytest.mark.unit
def test_verify_email_rejects_bad_token(app_client, sent) -> None:
    _register(app_client)
    r = app_client.post("/auth/verify-email", json={"token": "not-a-real-token"})
    assert r.status_code == 400
    assert r.json()["error"]["reason"] == "invalid_token"


@pytest.mark.unit
def test_verify_email_token_is_single_use(app_client, sent) -> None:
    _register(app_client)
    token = sent[0]["token"]
    assert app_client.post("/auth/verify-email", json={"token": token}).status_code == 200
    # Reusing the same token is rejected.
    assert app_client.post("/auth/verify-email", json={"token": token}).status_code == 400


@pytest.mark.unit
def test_verify_email_rejects_expired_token(app_client, sent, sessionmaker_for) -> None:
    _register(app_client)
    token = sent[0]["token"]

    from app.email.tokens import hash_token
    from app.models._common import utcnow
    from app.models.email_token import EmailToken

    # Age the token past its expiry.
    with sessionmaker_for() as db:
        row = db.execute(
            select(EmailToken).where(EmailToken.token_hash == hash_token(token))
        ).scalar_one()
        row.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()

    r = app_client.post("/auth/verify-email", json={"token": token})
    assert r.status_code == 400
    assert r.json()["error"]["reason"] == "invalid_token"


@pytest.mark.unit
def test_resend_verification_is_uniform_and_reissues(app_client, sent) -> None:
    _register(app_client)
    sent.clear()

    # Existing, unverified account -> a fresh token is issued.
    r1 = app_client.post("/auth/resend-verification", json={"email": "first@example.com"})
    assert r1.status_code == 200
    assert len(sent) == 1

    # Nonexistent account -> identical response, no token issued.
    r2 = app_client.post("/auth/resend-verification", json={"email": "nobody@example.com"})
    assert r2.status_code == 200
    assert r1.json()["message"] == r2.json()["message"]
    assert len(sent) == 1  # unchanged


# -----------------------------------------------------------------------------
# Password reset
# -----------------------------------------------------------------------------


@pytest.mark.unit
def test_forgot_password_is_enumeration_safe(app_client, sent) -> None:
    _register(app_client)
    sent.clear()

    exists = app_client.post("/auth/forgot-password", json={"email": "first@example.com"})
    missing = app_client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert exists.status_code == missing.status_code == 200
    assert exists.json()["message"] == missing.json()["message"]
    # Only the real account produced a reset token.
    assert [m["kind"] for m in sent] == ["reset"]


@pytest.mark.unit
def test_reset_password_changes_password(app_client, sent) -> None:
    _register(app_client)
    app_client.post("/auth/forgot-password", json={"email": "first@example.com"})
    token = [m for m in sent if m["kind"] == "reset"][-1]["token"]

    r = app_client.post("/auth/reset-password", json={"token": token, "password": _NEW_PASSWORD})
    assert r.status_code == 200, r.text

    # Old password no longer works; new one does.
    old = app_client.post("/auth/login", json={"email": "first@example.com", "password": _PASSWORD})
    assert old.status_code == 401
    new = app_client.post(
        "/auth/login", json={"email": "first@example.com", "password": _NEW_PASSWORD}
    )
    assert new.status_code == 200, new.text


@pytest.mark.unit
def test_reset_password_token_single_use(app_client, sent) -> None:
    _register(app_client)
    app_client.post("/auth/forgot-password", json={"email": "first@example.com"})
    token = [m for m in sent if m["kind"] == "reset"][-1]["token"]

    assert (
        app_client.post(
            "/auth/reset-password", json={"token": token, "password": _NEW_PASSWORD}
        ).status_code
        == 200
    )
    # A spent reset token cannot be replayed.
    assert (
        app_client.post(
            "/auth/reset-password", json={"token": token, "password": "yet another one 12!"}
        ).status_code
        == 400
    )


@pytest.mark.unit
def test_reset_password_rejects_bad_token(app_client, sent) -> None:
    _register(app_client)
    r = app_client.post("/auth/reset-password", json={"token": "nope", "password": _NEW_PASSWORD})
    assert r.status_code == 400
    assert r.json()["error"]["reason"] == "invalid_token"


@pytest.mark.unit
def test_reset_password_enforces_policy(app_client, sent) -> None:
    _register(app_client)
    app_client.post("/auth/forgot-password", json={"email": "first@example.com"})
    token = [m for m in sent if m["kind"] == "reset"][-1]["token"]
    r = app_client.post("/auth/reset-password", json={"token": token, "password": "short"})
    assert r.status_code == 422


# -----------------------------------------------------------------------------
# Login enforcement gate
# -----------------------------------------------------------------------------


@pytest.mark.unit
def test_login_blocked_when_require_email_verify_and_unverified(
    app_client, sent, monkeypatch
) -> None:
    _register(app_client)

    from app.config import Settings

    monkeypatch.setattr(
        "app.routes.auth.get_settings",
        lambda: Settings(shield_auth_require_email_verify=True),
    )

    blocked = app_client.post(
        "/auth/login", json={"email": "first@example.com", "password": _PASSWORD}
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["reason"] == "email_not_verified"

    # After verifying, login succeeds even with the flag on.
    app_client.post("/auth/verify-email", json={"token": sent[0]["token"]})
    ok = app_client.post("/auth/login", json={"email": "first@example.com", "password": _PASSWORD})
    assert ok.status_code == 200, ok.text
