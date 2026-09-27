"""A user of an archived client cannot start or keep a session (#727, D-104).

Gene's decision, 2026-09-26 (#736): sign-in is refused for users of an
ARCHIVED client (`Client.archived_at IS NOT NULL`) at every session-issuing
path, with a typed `client_archived` refusal, the way an inactive user is
refused. #726 ended the sessions an archive finds; before this, the same user
simply signed in again -- by password, by finishing an MFA step, or by the
OIDC exchange -- and `current_client` served the archived tenant.

Every test goes through an ENDPOINT, because the wiring is what selects the
guard. Each refusal has its own test so each can be shown red on its own
revert; the controls show another client's users and a Kentro admin (no
client) are untouched.

Two tests archive by a direct row write instead of `DELETE /admin/clients`:
the refresh and `current_client` guards. Through the endpoint, #726 has already
ended every session the archive finds, so those guards would never be the one
that refuses. The state they build is real: a client archived BEFORE #726
reached a deployment kept its users' refresh families and access tokens, and
nothing ended them afterwards.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jose import jwk as jose_jwk
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.security import totp

_PASSWORD = "correct horse battery staple!"
_ARCHIVED = "client_archived"

# Keycloak-shaped token signing, as in test_oidc_exchange.py: iss/aud/azp are
# the config defaults, and `_fetch_jwks` is monkeypatched to this key's JWKS.
_KID = "archived-client-test-key"


def _keypair() -> tuple[str, dict]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return priv, jose_jwk.construct(pub, "RS256").to_dict()


_PRIV, _PUB = _keypair()
_JWKS = {"keys": [{**_PUB, "kid": _KID, "alg": "RS256", "use": "sig"}]}


def _keycloak_token(email: str, sub: str) -> str:
    now = int(time.time())
    claims = {
        "iss": "http://localhost:8080/realms/shield",
        "aud": "shield-api",
        "azp": "shield-web",
        "sub": sub,
        "email": email,
        "email_verified": True,
        "iat": now,
        "exp": now + 300,
    }
    return jwt.encode(claims, _PRIV, algorithm="RS256", headers={"kid": _KID})


@pytest.fixture()
def app_client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    url = f"sqlite:///{tmp_path / 'shield-archived-sign-in.db'}"
    os.environ["DATABASE_URL"] = url
    os.environ["SHIELD_AUTH_OIDC_ENABLED"] = "true"
    get_settings.cache_clear()

    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app
    from app.security import oidc

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    oidc._jwks_by_kid = {}
    oidc._jwks_fetched_at = None
    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        os.environ.pop("SHIELD_AUTH_OIDC_ENABLED", None)
        get_settings.cache_clear()


def _register(client: TestClient, email: str) -> dict:
    r = client.post(
        "/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": email.split("@")[0]},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _login(client: TestClient, email: str, password: str = _PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def _auth(access: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access}"}


def _engagements(client: TestClient, access: str, client_id: str | None = None):
    headers = _auth(access)
    if client_id is not None:
        headers["X-Client-Id"] = client_id
    return client.get("/intake/engagements", headers=headers)


def _db() -> Session:
    return sessionmaker(bind=create_engine(os.environ["DATABASE_URL"], future=True), future=True)()


def _client_id_of(email: str) -> str:
    from app.models.user import User

    with _db() as s:
        cid = s.query(User).filter_by(email=email).one().client_id
    assert cid is not None, f"setup: {email} has no client"
    return str(cid)


def _archive(client: TestClient, admin_access: str, email: str) -> None:
    """Archive through the real endpoint, which also ends sessions (#726)."""
    r = client.delete(f"/admin/clients/{_client_id_of(email)}", headers=_auth(admin_access))
    assert r.status_code == 204, r.text


def _archive_row_only(email: str) -> None:
    """Set `archived_at` and nothing else: a client archived before #726."""
    import uuid

    from app.models.client import Client

    with _db() as s:
        row = s.get(Client, uuid.UUID(_client_id_of(email)))
        row.archived_at = datetime.now(UTC)
        s.commit()


def _assert_archived_refusal(r, status: int = 403) -> None:
    assert r.status_code == status, r.text
    error = r.json()["error"]
    assert error["reason"] == _ARCHIVED, r.text
    # D-076: the copy names no remedy the user cannot act on, and it must not
    # read as a credentials problem.
    assert "archived" in error["message"], error["message"]
    assert "password" not in error["message"].lower(), error["message"]


def _world(client: TestClient) -> str:
    """A Kentro admin, two users of the client to archive, one of another."""
    admin = _register(client, "admin@kentro.example")["tokens"]["access_token"]
    _register(client, "first@atlas.example")
    _register(client, "other@beta.example")
    return admin


# --- password login -----------------------------------------------------------


@pytest.mark.unit
def test_password_login_refuses_a_user_of_an_archived_client(app_client: TestClient) -> None:
    admin = _world(app_client)
    assert _login(app_client, "first@atlas.example").status_code == 200, "setup"

    _archive(app_client, admin, "first@atlas.example")

    _assert_archived_refusal(_login(app_client, "first@atlas.example"))


@pytest.mark.unit
def test_a_wrong_password_for_an_archived_clients_user_stays_the_generic_401(
    app_client: TestClient,
) -> None:
    """The archive check sits after the password verify, as the inactive check
    does, so the endpoint does not tell an unauthenticated caller which accounts
    belong to an archived client (OWASP A07)."""
    admin = _world(app_client)
    _archive(app_client, admin, "first@atlas.example")

    r = _login(app_client, "first@atlas.example", password="not the password at all")

    assert r.status_code == 401, r.text
    assert _ARCHIVED not in r.text, r.text


@pytest.mark.unit
def test_archiving_one_client_leaves_other_tenants_and_the_admin_able_to_sign_in(
    app_client: TestClient,
) -> None:
    admin = _world(app_client)
    _archive(app_client, admin, "first@atlas.example")

    other = _login(app_client, "other@beta.example")
    assert other.status_code == 200, other.text
    assert _engagements(app_client, other.json()["access_token"]).status_code == 200

    kentro = _login(app_client, "admin@kentro.example")
    assert kentro.status_code == 200, kentro.text


# --- MFA ----------------------------------------------------------------------


def _enroll_mfa(client: TestClient, email: str) -> str:
    access = _login(client, email).json()["access_token"]
    enroll = client.post("/auth/mfa/enroll", headers=_auth(access))
    assert enroll.status_code == 200, enroll.text
    secret = enroll.json()["secret"]
    verify = client.post(
        "/auth/mfa/verify", headers=_auth(access), json={"code": totp.totp_now(secret)}
    )
    assert verify.status_code == 200, verify.text
    return secret


@pytest.mark.unit
def test_finishing_an_mfa_step_begun_before_the_archive_is_refused(
    app_client: TestClient,
) -> None:
    admin = _world(app_client)
    secret = _enroll_mfa(app_client, "first@atlas.example")
    challenge = _login(app_client, "first@atlas.example")
    assert challenge.status_code == 200, challenge.text
    assert challenge.json()["mfa_required"] is True, "setup: the login must be an MFA challenge"
    pending = challenge.json()["mfa_pending_token"]

    _archive(app_client, admin, "first@atlas.example")

    r = app_client.post(
        "/auth/mfa/verify-login",
        json={"mfa_pending_token": pending, "code": totp.totp_now(secret)},
    )
    _assert_archived_refusal(r)


@pytest.mark.unit
def test_an_mfa_user_of_an_archived_client_gets_no_challenge(app_client: TestClient) -> None:
    """Refused at the password step, before a pending token is minted."""
    admin = _world(app_client)
    _enroll_mfa(app_client, "first@atlas.example")
    _archive(app_client, admin, "first@atlas.example")

    r = _login(app_client, "first@atlas.example")

    _assert_archived_refusal(r)
    assert "mfa_pending_token" not in r.text, r.text


# --- OIDC exchange ------------------------------------------------------------


@pytest.mark.unit
def test_the_oidc_exchange_refuses_a_user_of_an_archived_client(app_client: TestClient) -> None:
    admin = _world(app_client)
    token = _keycloak_token("first@atlas.example", "kc-first")
    ok = app_client.post("/auth/oidc/exchange", json={"keycloak_access_token": token})
    assert ok.status_code == 200, f"setup: the exchange must work first: {ok.text}"

    _archive(app_client, admin, "first@atlas.example")

    r = app_client.post("/auth/oidc/exchange", json={"keycloak_access_token": token})
    _assert_archived_refusal(r)


@pytest.mark.unit
def test_the_oidc_exchange_still_serves_another_clients_user(app_client: TestClient) -> None:
    admin = _world(app_client)
    _archive(app_client, admin, "first@atlas.example")

    token = _keycloak_token("other@beta.example", "kc-other")
    r = app_client.post("/auth/oidc/exchange", json={"keycloak_access_token": token})

    assert r.status_code == 200, r.text


# --- refresh ------------------------------------------------------------------


@pytest.mark.unit
def test_refresh_refuses_a_user_of_a_client_archived_before_sessions_were_ended(
    app_client: TestClient,
) -> None:
    _world(app_client)
    refresh = _login(app_client, "first@atlas.example").json()["refresh_token"]

    _archive_row_only("first@atlas.example")

    r = app_client.post("/auth/refresh", json={"refresh_token": refresh})
    _assert_archived_refusal(r)


@pytest.mark.unit
def test_refresh_still_rotates_for_another_clients_user(app_client: TestClient) -> None:
    _world(app_client)
    refresh = _login(app_client, "other@beta.example").json()["refresh_token"]
    _archive_row_only("first@atlas.example")

    r = app_client.post("/auth/refresh", json={"refresh_token": refresh})

    assert r.status_code == 200, r.text


# --- current_client -----------------------------------------------------------


@pytest.mark.unit
def test_current_client_refuses_a_client_user_whose_client_is_archived(
    app_client: TestClient,
) -> None:
    _world(app_client)
    access = _login(app_client, "first@atlas.example").json()["access_token"]
    assert _engagements(app_client, access).status_code == 200, "setup: the token must work first"

    _archive_row_only("first@atlas.example")

    _assert_archived_refusal(_engagements(app_client, access))


@pytest.mark.unit
def test_a_kentro_admin_can_still_open_an_archived_client(app_client: TestClient) -> None:
    """The refusal is for the archived client's OWN users. A Kentro admin picks
    the tenant with X-Client-Id and keeps access to an archived one: archiving
    retains the tenant's data rather than deleting it, and the admin is who
    reads it."""
    admin = _world(app_client)
    cid = _client_id_of("first@atlas.example")
    _archive(app_client, admin, "first@atlas.example")

    r = _engagements(app_client, admin, client_id=cid)

    assert r.status_code == 200, r.text


# --- registration -------------------------------------------------------------


@pytest.mark.unit
def test_registering_into_an_archived_clients_domain_is_refused_and_creates_no_user(
    app_client: TestClient,
) -> None:
    """A new registrant on the archived client's mapped domain would join it and
    be handed a session. 409, not 403: the refusal is about where the email's
    domain leads, the class `email_domain_unavailable` already answers with a
    409, and the sign-up form renders a typed 409's message."""
    from app.models.user import User

    admin = _world(app_client)
    _archive(app_client, admin, "first@atlas.example")

    r = app_client.post(
        "/auth/register",
        json={"email": "coworker@atlas.example", "password": _PASSWORD, "display_name": "cw"},
    )

    _assert_archived_refusal(r, status=409)
    with _db() as s:
        assert s.query(User).filter_by(email="coworker@atlas.example").count() == 0
