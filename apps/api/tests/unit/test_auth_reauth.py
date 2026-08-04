"""Auth compensating-controls tests (Sprint 3 T2).

Covers the honest versions of the controls README/BUILD_REPORT claimed:
  (a) daily forced re-auth ceiling honored at /auth/refresh (typed 401
      reason=reauth_required past shield_forced_reauth_seconds);
  (b) refresh-token rotation — a reused (already-rotated) refresh token is
      rejected;
  (c) dead feature flags fail loudly at startup rather than silently doing
      nothing (the MFA / email-verify flows don't exist yet).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "shield-reauth.db"
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


def _register(client: TestClient, email: str = "first@example.com") -> dict:
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple!",
            "display_name": "Test User",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# -----------------------------------------------------------------------------
# (a) Forced re-auth ceiling
# -----------------------------------------------------------------------------


@pytest.mark.unit
def test_refresh_past_forced_reauth_returns_typed_401(app_client: TestClient) -> None:
    from app.config import get_settings
    from app.security.jwt import issue_token

    body = _register(app_client)
    user_id = body["user"]["id"]
    settings = get_settings()

    # Mint a refresh token whose original auth time is older than the forced
    # re-auth ceiling. The ceiling is checked before rotation, so the jti need
    # not match the stored one.
    stale_auth_time = datetime.now(UTC) - timedelta(
        seconds=settings.shield_forced_reauth_seconds + 3600
    )
    import uuid as _uuid

    stale_token, _ = issue_token(
        subject=_uuid.UUID(user_id),
        role="admin",
        typ="refresh",
        auth_time=stale_auth_time,
    )

    r = app_client.post("/auth/refresh", json={"refresh_token": stale_token})
    assert r.status_code == 401, r.text
    assert r.json()["error"]["reason"] == "reauth_required"


@pytest.mark.unit
def test_refresh_within_window_carries_auth_time_forward(app_client: TestClient) -> None:
    from app.security.jwt import verify_token

    body = _register(app_client)
    original = verify_token(body["tokens"]["refresh_token"], expected_type="refresh")

    r = app_client.post("/auth/refresh", json={"refresh_token": body["tokens"]["refresh_token"]})
    assert r.status_code == 200, r.text
    rotated = verify_token(r.json()["refresh_token"], expected_type="refresh")

    # The original auth-time claim rides forward unchanged so the forced-reauth
    # ceiling is anchored to the original login, not reset on every refresh.
    assert rotated.auth_time is not None
    assert original.auth_time is not None
    assert rotated.auth_time == original.auth_time


# -----------------------------------------------------------------------------
# (b) Refresh-token rotation
# -----------------------------------------------------------------------------


@pytest.mark.unit
def test_reused_old_refresh_token_rejected(app_client: TestClient) -> None:
    body = _register(app_client)
    original_refresh = body["tokens"]["refresh_token"]

    first = app_client.post("/auth/refresh", json={"refresh_token": original_refresh})
    assert first.status_code == 200, first.text
    new_refresh = first.json()["refresh_token"]

    # Reusing the now-rotated-out original refresh token is rejected loudly.
    reused = app_client.post("/auth/refresh", json={"refresh_token": original_refresh})
    assert reused.status_code == 401, reused.text
    assert reused.json()["error"]["reason"] == "refresh_reused"

    # The freshly rotated token still works.
    ok = app_client.post("/auth/refresh", json={"refresh_token": new_refresh})
    assert ok.status_code == 200, ok.text


# -----------------------------------------------------------------------------
# (c) Dead feature flags fail loudly at startup
# -----------------------------------------------------------------------------


@pytest.mark.unit
def test_startup_no_longer_refuses_when_require_mfa_true() -> None:
    # Sprint 6 T4 / D-027: the TOTP enroll/verify/login-challenge flow now
    # exists, so SHIELD_AUTH_REQUIRE_MFA GATES enforcement in routes/auth.py
    # rather than refusing to boot. Booting with the flag on must NOT raise.
    from app.config import Settings

    settings = Settings(shield_auth_require_mfa=True)
    settings.assert_safe_for_runtime()  # does not raise


@pytest.mark.unit
def test_startup_no_longer_refuses_when_require_email_verify_true() -> None:
    # Sprint 6 T5 / D-028: the email-verification flow now exists, so
    # SHIELD_AUTH_REQUIRE_EMAIL_VERIFY GATES login enforcement in routes/auth.py
    # rather than refusing to boot. Booting with the flag on must NOT raise.
    from app.config import Settings

    settings = Settings(shield_auth_require_email_verify=True)
    settings.assert_safe_for_runtime()  # does not raise


@pytest.mark.unit
def test_startup_raises_when_email_delivery_enabled_without_host() -> None:
    # D-028: enabling delivery without an SMTP host would silently drop every
    # verification / reset email — refuse to boot rather than swallow it.
    from app.config import Settings

    settings = Settings(shield_email_delivery_enabled=True, smtp_host="")
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        settings.assert_safe_for_runtime()
