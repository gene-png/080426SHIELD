"""JWT issue + verify."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

import pytest

from app.security.jwt import (
    TokenError,
    issue_token,
    verify_token,
)


@pytest.mark.unit
def test_issue_then_verify_roundtrip() -> None:
    uid = uuid.uuid4()
    token, payload = issue_token(subject=uid, role="admin")
    decoded = verify_token(token)
    assert decoded.sub == uid
    assert decoded.role == "admin"
    assert decoded.typ == "access"
    assert decoded.jti == payload.jti
    assert decoded.exp.tzinfo == UTC
    assert decoded.exp > datetime.now(UTC)


@pytest.mark.unit
def test_refresh_token_has_different_typ() -> None:
    uid = uuid.uuid4()
    token, _ = issue_token(subject=uid, role="client", typ="refresh")
    decoded = verify_token(token, expected_type="refresh")
    assert decoded.typ == "refresh"


@pytest.mark.unit
def test_type_mismatch_rejected() -> None:
    uid = uuid.uuid4()
    token, _ = issue_token(subject=uid, role="client", typ="refresh")
    with pytest.raises(TokenError, match="type mismatch"):
        verify_token(token, expected_type="access")


@pytest.mark.unit
def test_tampered_token_rejected() -> None:
    uid = uuid.uuid4()
    token, _ = issue_token(subject=uid, role="admin")
    tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    with pytest.raises(TokenError):
        verify_token(tampered)


@pytest.mark.unit
def test_expired_token_rejected() -> None:
    """Synthesize an already-expired token directly via jose, then verify."""
    import uuid as _uuid

    from jose import jwt

    from app.config import get_settings
    from app.security.jwt import ALGORITHM, ISSUER

    s = get_settings()
    past = int(time.time()) - 60
    claims = {
        "iss": ISSUER,
        "aud": s.keycloak_audience,
        "sub": str(uuid.uuid4()),
        "role": "admin",
        "typ": "access",
        "jti": str(_uuid.uuid4()),
        "iat": past - 60,
        "nbf": past - 60,
        "exp": past,
    }
    token = jwt.encode(claims, s.jwt_signing_secret, algorithm=ALGORITHM)
    with pytest.raises(TokenError):
        verify_token(token)


@pytest.mark.unit
def test_wrong_audience_rejected(monkeypatch) -> None:
    from app.config import get_settings

    uid = uuid.uuid4()
    token, _ = issue_token(subject=uid, role="admin")
    real = get_settings()
    monkeypatch.setattr(
        "app.security.jwt.get_settings",
        lambda: real.model_copy(update={"keycloak_audience": "some-other-aud"}),
    )
    with pytest.raises(TokenError):
        verify_token(token)
