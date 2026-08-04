"""End-to-end MFA route tests (enroll -> verify -> login challenge -> complete).

Sprint 6 T4 / D-027. Runs against an ephemeral SQLite + FastAPI TestClient,
mirroring test_auth_routes.py. The TOTP code is derived from the real secret
the enroll endpoint hands back, so the flow exercises the actual crypto.
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

from app.security import totp


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "shield-mfa.db"
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


_PASSWORD = "correct horse battery staple!"


def _register(client: TestClient, email: str = "first@example.com") -> dict:
    r = client.post(
        "/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "Test User"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _enroll_and_verify(client: TestClient, access: str) -> tuple[str, list[str]]:
    """Run the full enroll->verify handshake; return (secret, recovery_codes)."""
    enroll = client.post("/auth/mfa/enroll", headers={"Authorization": f"Bearer {access}"})
    assert enroll.status_code == 200, enroll.text
    secret = enroll.json()["secret"]
    assert enroll.json()["otpauth_uri"].startswith("otpauth://totp/")

    verify = client.post(
        "/auth/mfa/verify",
        headers={"Authorization": f"Bearer {access}"},
        json={"code": totp.totp_now(secret)},
    )
    assert verify.status_code == 200, verify.text
    codes = verify.json()["recovery_codes"]
    assert len(codes) == 10
    return secret, codes


@pytest.mark.unit
def test_login_without_mfa_returns_pair_no_challenge(app_client: TestClient) -> None:
    _register(app_client)
    r = app_client.post("/auth/login", json={"email": "first@example.com", "password": _PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["mfa_required"] is False
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["mfa_pending_token"] is None


@pytest.mark.unit
def test_enroll_requires_authentication(app_client: TestClient) -> None:
    r = app_client.post("/auth/mfa/enroll")
    assert r.status_code == 401


@pytest.mark.unit
def test_verify_rejects_wrong_code(app_client: TestClient) -> None:
    body = _register(app_client)
    access = body["tokens"]["access_token"]
    app_client.post("/auth/mfa/enroll", headers={"Authorization": f"Bearer {access}"})
    r = app_client.post(
        "/auth/mfa/verify",
        headers={"Authorization": f"Bearer {access}"},
        json={"code": "000000"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["reason"] == "mfa_invalid_code"


@pytest.mark.unit
def test_enroll_rejected_when_already_enrolled(app_client: TestClient) -> None:
    """A second /auth/mfa/enroll on an already-enrolled account must be refused
    (Sprint 6 audit): re-enrolling would overwrite the live TOTP secret while
    ``mfa_enrolled`` stayed True, silently locking the user out of their working
    authenticator until they re-confirmed the new QR. The web UI already hides
    the button when enrolled; this guards the raw endpoint against a direct call.
    """
    body = _register(app_client)
    access = body["tokens"]["access_token"]
    secret, _codes = _enroll_and_verify(app_client, access)

    r = app_client.post("/auth/mfa/enroll", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "mfa_already_enrolled"

    # The working secret is untouched: a login challenge still completes with it.
    login = app_client.post(
        "/auth/login", json={"email": "first@example.com", "password": _PASSWORD}
    )
    pending = login.json()["mfa_pending_token"]
    done = app_client.post(
        "/auth/mfa/verify-login",
        json={"mfa_pending_token": pending, "code": totp.totp_now(secret)},
    )
    assert done.status_code == 200, done.text


@pytest.mark.unit
def test_verify_before_enroll_is_rejected(app_client: TestClient) -> None:
    body = _register(app_client)
    access = body["tokens"]["access_token"]
    r = app_client.post(
        "/auth/mfa/verify",
        headers={"Authorization": f"Bearer {access}"},
        json={"code": "123456"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["reason"] == "mfa_not_started"


@pytest.mark.unit
def test_full_enroll_then_login_with_totp(app_client: TestClient) -> None:
    body = _register(app_client)
    access = body["tokens"]["access_token"]
    secret, _codes = _enroll_and_verify(app_client, access)

    # Now login: password alone yields a challenge, not the pair.
    login = app_client.post(
        "/auth/login", json={"email": "first@example.com", "password": _PASSWORD}
    )
    assert login.status_code == 200
    assert login.json()["mfa_required"] is True
    assert login.json()["access_token"] is None
    pending = login.json()["mfa_pending_token"]
    assert pending

    # The pending token is NOT a usable access token.
    assert (
        app_client.get("/auth/me", headers={"Authorization": f"Bearer {pending}"}).status_code
        == 401
    )

    # Complete the challenge with a valid TOTP.
    done = app_client.post(
        "/auth/mfa/verify-login",
        json={"mfa_pending_token": pending, "code": totp.totp_now(secret)},
    )
    assert done.status_code == 200, done.text
    assert done.json()["access_token"]
    assert done.json()["refresh_token"]


@pytest.mark.unit
def test_verify_login_rejects_wrong_code(app_client: TestClient) -> None:
    body = _register(app_client)
    access = body["tokens"]["access_token"]
    _enroll_and_verify(app_client, access)
    login = app_client.post(
        "/auth/login", json={"email": "first@example.com", "password": _PASSWORD}
    )
    pending = login.json()["mfa_pending_token"]
    r = app_client.post(
        "/auth/mfa/verify-login",
        json={"mfa_pending_token": pending, "code": "000000"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["reason"] == "mfa_invalid_code"


@pytest.mark.unit
def test_verify_login_rejects_access_token_as_pending(app_client: TestClient) -> None:
    body = _register(app_client)
    access = body["tokens"]["access_token"]
    secret, _codes = _enroll_and_verify(app_client, access)
    # An access token must not be accepted where an mfa_pending token is required.
    r = app_client.post(
        "/auth/mfa/verify-login",
        json={"mfa_pending_token": access, "code": totp.totp_now(secret)},
    )
    assert r.status_code == 401


@pytest.mark.unit
def test_recovery_code_login_is_single_use(app_client: TestClient) -> None:
    body = _register(app_client)
    access = body["tokens"]["access_token"]
    _secret, codes = _enroll_and_verify(app_client, access)
    recovery = codes[0]

    def _challenge() -> str:
        login = app_client.post(
            "/auth/login", json={"email": "first@example.com", "password": _PASSWORD}
        )
        return login.json()["mfa_pending_token"]

    # First use of the recovery code succeeds.
    first = app_client.post(
        "/auth/mfa/verify-login",
        json={"mfa_pending_token": _challenge(), "code": recovery},
    )
    assert first.status_code == 200, first.text

    # Second use of the SAME code is rejected (single-use).
    second = app_client.post(
        "/auth/mfa/verify-login",
        json={"mfa_pending_token": _challenge(), "code": recovery},
    )
    assert second.status_code == 401


@pytest.mark.unit
def test_verify_login_failures_feed_account_lockout(app_client: TestClient) -> None:
    """Second-factor guesses at /auth/mfa/verify-login must count toward the
    same account-lockout budget as password failures (Sprint 6 T10). A single
    reusable mfa_pending token models an attacker hammering the code — once the
    budget is exhausted, even a CORRECT TOTP is refused (423) and password
    login is locked too (one shared counter)."""
    from app.config import get_settings

    body = _register(app_client)
    access = body["tokens"]["access_token"]
    secret, _codes = _enroll_and_verify(app_client, access)

    login = app_client.post(
        "/auth/login", json={"email": "first@example.com", "password": _PASSWORD}
    )
    pending = login.json()["mfa_pending_token"]

    max_attempts = get_settings().shield_account_lockout_max_attempts
    for _ in range(max_attempts):
        r = app_client.post(
            "/auth/mfa/verify-login",
            json={"mfa_pending_token": pending, "code": "000000"},
        )
        assert r.status_code == 401, r.text

    # Budget exhausted → account locked: a correct TOTP now yields 423, not 200.
    locked = app_client.post(
        "/auth/mfa/verify-login",
        json={"mfa_pending_token": pending, "code": totp.totp_now(secret)},
    )
    assert locked.status_code == 423, locked.text

    # The lockout is shared: password login is locked too.
    pw = app_client.post("/auth/login", json={"email": "first@example.com", "password": _PASSWORD})
    assert pw.status_code == 423


@pytest.mark.unit
def test_enroll_verify_failures_feed_account_lockout(app_client: TestClient) -> None:
    """Wrong codes at /auth/mfa/verify (enrollment confirmation) must also feed
    the account-lockout counter (Sprint 6 T10), so the enrollment-confirm code
    cannot be brute-forced without tripping lockout."""
    from app.config import get_settings

    body = _register(app_client)
    access = body["tokens"]["access_token"]
    app_client.post("/auth/mfa/enroll", headers={"Authorization": f"Bearer {access}"})

    max_attempts = get_settings().shield_account_lockout_max_attempts
    for _ in range(max_attempts):
        r = app_client.post(
            "/auth/mfa/verify",
            headers={"Authorization": f"Bearer {access}"},
            json={"code": "000000"},
        )
        assert r.status_code == 400, r.text

    # Budget exhausted → account locked. A further verify is refused with 423.
    locked = app_client.post(
        "/auth/mfa/verify",
        headers={"Authorization": f"Bearer {access}"},
        json={"code": "000000"},
    )
    assert locked.status_code == 423, locked.text

    # And password login is locked too (shared counter).
    pw = app_client.post("/auth/login", json={"email": "first@example.com", "password": _PASSWORD})
    assert pw.status_code == 423
