"""Hybrid OIDC exchange contract: POST /auth/oidc/exchange (SPRINT_9 T4, D-032).

Keycloak owns the browser login; SHIELD verifies the resulting Keycloak ACCESS
token once, at this single door, and mints its own plain D-020 HS256 pair in its
place. A Keycloak token is NEVER accepted as an API bearer — the exchange is the
only place it is honored, and only when SHIELD_AUTH_OIDC_ENABLED is on.

TDD-first: every contract below is authored before the route/verifier exist and
must fail loudly until T4 lands. An in-test RSA keypair signs Keycloak-shaped
tokens; the module-level ``_fetch_jwks`` is monkeypatched to return the matching
JWKS so no network is touched. iss/aud/azp are signed to the config defaults
(``http://localhost:8080/realms/shield`` / ``shield-api`` / ``shield-web``) so the
happy path matches without overriding settings. The issuer is the ONE canonical
value the dual-horizon Keycloak pins for browser and containers alike (Sprint 9
T5, ``KC_HOSTNAME`` + backchannel-dynamic), which is what a real Keycloak token
carries regardless of the interface that served it.
"""

from __future__ import annotations

import os
import time
import uuid as _uuid
from collections.abc import Iterator
from contextlib import contextmanager
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
from app.models.user import User, UserRole
from app.security.jwt import verify_token

# --- Config defaults the tokens are signed against -----------------------------
_ISS = "http://localhost:8080/realms/shield"
_AUD = "shield-api"
_AZP = "shield-web"
_KID = "test-key-1"
_ROTATED_KID = "rotated-key-2"


def _make_keypair() -> tuple[str, dict]:
    """Return (private PEM, public JWK dict) for an RS256 signing key."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    jwk_dict = jose_jwk.construct(pub_pem, "RS256").to_dict()
    return priv_pem, jwk_dict


# One primary keypair for the whole module + a second "rotated" key that is
# deliberately NEVER published in the JWKS (used by the unknown-kid test).
_PRIV_PEM, _PUB_JWK = _make_keypair()
_PUB_JWK = {**_PUB_JWK, "kid": _KID, "alg": "RS256", "use": "sig"}
_ROTATED_PRIV_PEM, _ROTATED_PUB_JWK = _make_keypair()

_JWKS = {"keys": [_PUB_JWK]}


def _base_claims(**overrides: object) -> dict:
    now = int(time.time())
    claims: dict = {
        "iss": _ISS,
        "aud": _AUD,
        "azp": _AZP,
        "sub": "kc-sub-default",
        "email": "consultant@example.com",
        "email_verified": True,
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return claims


def _sign(claims: dict, *, priv_pem: str = _PRIV_PEM, kid: str = _KID) -> str:
    return jwt.encode(claims, priv_pem, algorithm="RS256", headers={"kid": kid})


def _drop(claims: dict, *keys: str) -> dict:
    return {k: v for k, v in claims.items() if k not in keys}


@contextmanager
def _make_app_client(tmp_path, *, oidc_enabled: bool) -> Iterator[tuple[TestClient, sessionmaker]]:
    db_path = tmp_path / "shield-oidc.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url
    os.environ["SHIELD_AUTH_OIDC_ENABLED"] = "true" if oidc_enabled else "false"
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

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    from app.models.client import Client as _Client

    _seed = TestSession()
    _tenant = _Client(legal_name="Test Tenant")
    _seed.add(_tenant)
    _seed.commit()
    cid = str(_tenant.id)
    _seed.close()

    try:
        with TestClient(app, headers={"X-Client-Id": cid}) as c:
            yield c, TestSession
    finally:
        os.environ.pop("SHIELD_AUTH_OIDC_ENABLED", None)
        get_settings.cache_clear()


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    with _make_app_client(tmp_path, oidc_enabled=True) as ctx:
        yield ctx


@pytest.fixture()
def app_client_disabled(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    with _make_app_client(tmp_path, oidc_enabled=False) as ctx:
        yield ctx


@pytest.fixture(autouse=True)
def _cold_jwks_cache() -> Iterator[None]:
    """The JWKS cache is process-global; start every test cold and monkeypatch
    the raw fetch to the in-test JWKS by default (individual tests override)."""
    from app.security import oidc

    oidc._jwks_by_kid = {}
    oidc._jwks_fetched_at = None
    yield


def _seed_user(
    TestSession: sessionmaker,
    *,
    email: str,
    role: UserRole = UserRole.CLIENT,
    is_active: bool = True,
    keycloak_sub: str | None = None,
    locked_until_at=None,
) -> _uuid.UUID:
    with TestSession() as db:
        user = User(
            email=email,
            password_hash="x" * 32,
            role=role,
            display_name=email.split("@")[0],
            is_active=is_active,
            keycloak_sub=keycloak_sub,
            locked_until_at=locked_until_at,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def _exchange(c: TestClient, token: str):
    return c.post("/auth/oidc/exchange", json={"keycloak_access_token": token})


# ---------------------------------------------------------------------------
# Happy path + token shape
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_exchange_mints_verifiable_local_pair(app_client, monkeypatch) -> None:
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)

    uid = _seed_user(TestSession, email="consultant@example.com", role=UserRole.ADMIN)
    token = _sign(_base_claims(sub="kc-admin-1", email="consultant@example.com"))

    r = _exchange(c, token)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == "consultant@example.com"
    assert body["user"]["role"] == "admin"

    # The minted access token is a plain SHIELD HS256 token (iss=shield-api).
    access = body["tokens"]["access_token"]
    payload = verify_token(access, expected_type="access")
    assert payload.sub == uid
    assert payload.role == "admin"


@pytest.mark.unit
def test_role_comes_from_db_not_the_keycloak_claim(app_client, monkeypatch) -> None:
    """A Keycloak token claiming admin for a local CLIENT user mints CLIENT
    tokens — the local DB role is authoritative, the roles claim is ignored."""
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)

    _seed_user(TestSession, email="client@example.com", role=UserRole.CLIENT)
    token = _sign(
        _base_claims(
            sub="kc-client-1",
            email="client@example.com",
            realm_access={"roles": ["admin", "superuser"]},
        )
    )

    r = _exchange(c, token)
    assert r.status_code == 200, r.text
    payload = verify_token(r.json()["tokens"]["access_token"], expected_type="access")
    assert payload.role == "client"


@pytest.mark.unit
def test_minted_refresh_token_rotates(app_client, monkeypatch) -> None:
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)

    _seed_user(TestSession, email="consultant@example.com", role=UserRole.ADMIN)
    token = _sign(_base_claims(sub="kc-admin-1"))
    r = _exchange(c, token)
    assert r.status_code == 200, r.text

    refresh = r.json()["tokens"]["refresh_token"]
    rot = c.post("/auth/refresh", json={"refresh_token": refresh})
    assert rot.status_code == 200, rot.text
    assert rot.json()["access_token"]


# ---------------------------------------------------------------------------
# Signature / claim rejection matrix (all typed dict-detail, FAIL LOUDLY)
# ---------------------------------------------------------------------------


def _reason(r) -> str:
    return r.json()["error"]["reason"]


@pytest.mark.unit
def test_wrong_issuer_rejected(app_client, monkeypatch) -> None:
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)
    _seed_user(TestSession, email="consultant@example.com", role=UserRole.ADMIN)

    token = _sign(_base_claims(iss="http://evil:8080/realms/shield"))
    r = _exchange(c, token)
    assert r.status_code == 401, r.text
    assert _reason(r) == "oidc_token_invalid"


@pytest.mark.unit
def test_wrong_audience_rejected(app_client, monkeypatch) -> None:
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)
    _seed_user(TestSession, email="consultant@example.com", role=UserRole.ADMIN)

    token = _sign(_base_claims(aud="some-other-api"))
    r = _exchange(c, token)
    assert r.status_code == 401, r.text
    assert _reason(r) == "oidc_token_invalid"


@pytest.mark.unit
def test_expired_token_rejected(app_client, monkeypatch) -> None:
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)
    _seed_user(TestSession, email="consultant@example.com", role=UserRole.ADMIN)

    now = int(time.time())
    token = _sign(_base_claims(iat=now - 600, exp=now - 300))
    r = _exchange(c, token)
    assert r.status_code == 401, r.text
    assert _reason(r) == "oidc_token_invalid"


@pytest.mark.unit
def test_hs256_signed_token_rejected(app_client, monkeypatch) -> None:
    """Alg-confusion guard: an HS256-signed token (signed with the app's own
    signing secret) must be rejected by the RS256-only algorithms list."""
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)
    _seed_user(TestSession, email="consultant@example.com", role=UserRole.ADMIN)

    secret = get_settings().jwt_signing_secret
    token = jwt.encode(_base_claims(), secret, algorithm="HS256", headers={"kid": _KID})
    r = _exchange(c, token)
    assert r.status_code == 401, r.text
    assert _reason(r) == "oidc_token_invalid"


@pytest.mark.unit
def test_token_minted_to_a_different_client_rejected(app_client, monkeypatch) -> None:
    """Codex finding: aud names the resource server (shield-api), not the
    requesting client. A correctly signed token whose azp is a DIFFERENT client
    must be rejected even though aud/iss/signature are all valid."""
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)
    _seed_user(TestSession, email="consultant@example.com", role=UserRole.ADMIN)

    token = _sign(_base_claims(azp="a-different-client"))
    r = _exchange(c, token)
    assert r.status_code == 401, r.text
    assert _reason(r) == "oidc_token_invalid"


@pytest.mark.unit
def test_unknown_kid_forces_exactly_one_refetch(app_client, monkeypatch) -> None:
    """A token bearing an unknown kid triggers EXACTLY ONE forced JWKS refetch
    (Keycloak key rotation), then rejects if still unknown — never loops."""
    c, TestSession = app_client
    from app.security import oidc

    calls = {"n": 0}

    def counting_fetch() -> dict:
        calls["n"] += 1
        return _JWKS  # the rotated kid is never published here

    monkeypatch.setattr(oidc, "_fetch_jwks", counting_fetch)

    _seed_user(TestSession, email="consultant@example.com", role=UserRole.ADMIN)

    # Warm the cache with a successful exchange (fetch #1), then reset the count.
    ok = _exchange(c, _sign(_base_claims(sub="kc-admin-1")))
    assert ok.status_code == 200, ok.text
    calls["n"] = 0

    # Present a token signed by the unpublished "rotated" key. Cache is fresh, so
    # the only fetch is the single forced refetch on the unknown kid.
    token = _sign(_base_claims(), priv_pem=_ROTATED_PRIV_PEM, kid=_ROTATED_KID)
    r = _exchange(c, token)
    assert r.status_code == 401, r.text
    assert _reason(r) == "oidc_token_invalid"
    assert calls["n"] == 1, f"expected exactly one forced refetch, got {calls['n']}"


@pytest.mark.unit
def test_missing_email_claim_rejected(app_client, monkeypatch) -> None:
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)

    token = _sign(_drop(_base_claims(), "email"))
    r = _exchange(c, token)
    assert r.status_code == 401, r.text
    assert _reason(r) == "oidc_claims_missing"


@pytest.mark.unit
def test_unverified_email_rejected(app_client, monkeypatch) -> None:
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)
    _seed_user(TestSession, email="consultant@example.com", role=UserRole.ADMIN)

    token = _sign(_base_claims(email_verified=False))
    r = _exchange(c, token)
    assert r.status_code == 403, r.text
    assert _reason(r) == "oidc_email_unverified"


@pytest.mark.unit
def test_no_local_account_rejected(app_client, monkeypatch) -> None:
    """No JIT provisioning: a verified Keycloak identity with no matching local
    user is refused, not created."""
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)

    token = _sign(_base_claims(email="stranger@example.com"))
    r = _exchange(c, token)
    assert r.status_code == 403, r.text
    assert _reason(r) == "oidc_no_local_account"


@pytest.mark.unit
def test_inactive_user_rejected(app_client, monkeypatch) -> None:
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)
    _seed_user(TestSession, email="consultant@example.com", role=UserRole.ADMIN, is_active=False)

    token = _sign(_base_claims())
    r = _exchange(c, token)
    assert r.status_code == 403, r.text
    assert _reason(r) == "oidc_user_inactive"


@pytest.mark.unit
def test_email_match_is_case_insensitive(app_client, monkeypatch) -> None:
    """The token email is normalized before lookup, matching a lowercased local
    account (registration normalizes on the way in)."""
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)
    _seed_user(TestSession, email="consultant@example.com", role=UserRole.ADMIN)

    token = _sign(_base_claims(email="Consultant@Example.COM"))
    r = _exchange(c, token)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# TOFU sub binding
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sub_stamped_on_first_exchange(app_client, monkeypatch) -> None:
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)
    uid = _seed_user(TestSession, email="consultant@example.com", role=UserRole.ADMIN)

    token = _sign(_base_claims(sub="kc-unique-777"))
    r = _exchange(c, token)
    assert r.status_code == 200, r.text

    with TestSession() as db:
        user = db.get(User, uid)
        assert user.keycloak_sub == "kc-unique-777"


@pytest.mark.unit
def test_sub_mismatch_rejected(app_client, monkeypatch) -> None:
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)
    _seed_user(
        TestSession,
        email="consultant@example.com",
        role=UserRole.ADMIN,
        keycloak_sub="the-original-sub",
    )

    token = _sign(_base_claims(sub="a-different-sub"))
    r = _exchange(c, token)
    assert r.status_code == 403, r.text
    assert _reason(r) == "oidc_sub_mismatch"


@pytest.mark.unit
def test_matching_bound_sub_succeeds(app_client, monkeypatch) -> None:
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)
    _seed_user(
        TestSession,
        email="consultant@example.com",
        role=UserRole.ADMIN,
        keycloak_sub="stable-sub-1",
    )

    token = _sign(_base_claims(sub="stable-sub-1"))
    r = _exchange(c, token)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Flag off + JWKS outage
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_flag_off_returns_disabled(app_client_disabled, monkeypatch) -> None:
    """With SHIELD_AUTH_OIDC_ENABLED off the route exists but refuses loudly —
    even a perfectly valid token is rejected 403 oidc_disabled."""
    c, TestSession = app_client_disabled
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)
    _seed_user(TestSession, email="consultant@example.com", role=UserRole.ADMIN)

    token = _sign(_base_claims())
    r = _exchange(c, token)
    assert r.status_code == 403, r.text
    assert _reason(r) == "oidc_disabled"


@pytest.mark.unit
def test_jwks_unavailable_returns_503(app_client, monkeypatch) -> None:
    c, TestSession = app_client
    import httpx

    from app.security import oidc

    def boom() -> dict:
        raise httpx.ConnectError("keycloak unreachable")

    monkeypatch.setattr(oidc, "_fetch_jwks", boom)
    _seed_user(TestSession, email="consultant@example.com", role=UserRole.ADMIN)

    token = _sign(_base_claims())
    r = _exchange(c, token)
    assert r.status_code == 503, r.text
    assert _reason(r) == "oidc_jwks_unavailable"


# ---------------------------------------------------------------------------
# Local-account bookkeeping the exchange must NOT touch
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_local_lockout_is_not_consulted(app_client, monkeypatch) -> None:
    """Keycloak's bruteForceProtected owns SSO lockout — honoring the LOCAL
    password lockout would let a password-endpoint attacker DoS SSO users. A
    locally locked account still exchanges successfully."""
    from datetime import UTC, datetime, timedelta

    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)
    locked_until = datetime.now(UTC) + timedelta(minutes=15)
    _seed_user(
        TestSession,
        email="consultant@example.com",
        role=UserRole.ADMIN,
        locked_until_at=locked_until,
    )

    token = _sign(_base_claims())
    r = _exchange(c, token)
    assert r.status_code == 200, r.text


@pytest.mark.unit
def test_exchange_does_not_stamp_local_email_verified(app_client, monkeypatch) -> None:
    """OIDC email trust lives in Keycloak; the exchange does not backfill the
    local email_verified_at column."""
    c, TestSession = app_client
    from app.security import oidc

    monkeypatch.setattr(oidc, "_fetch_jwks", lambda: _JWKS)
    uid = _seed_user(TestSession, email="consultant@example.com", role=UserRole.ADMIN)

    token = _sign(_base_claims())
    r = _exchange(c, token)
    assert r.status_code == 200, r.text

    with TestSession() as db:
        user = db.get(User, uid)
        assert user.email_verified_at is None
        # A successful exchange still stamps last_login_at (shared bookkeeping).
        assert user.last_login_at is not None
