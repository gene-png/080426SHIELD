"""JWT issue + verify.

Master Spec §4.5: short-lived access tokens (15 min) and a refresh token.
Tokens are signed with HS256 from `Settings.jwt_signing_secret`; in
production the secret comes from a secrets manager rather than an env var.

Claims:
  iss: "shield-api"
  aud: KEYCLOAK_AUDIENCE (default "shield-api") - keeps shape stable when
       v1.x federates auth through Keycloak; the same `aud` already matches.
  sub: user id (UUID, string form)
  role: UserRole enum value ("admin"/"client")
  typ: "access" | "refresh"
  jti: UUID per token; the refresh jti is the rotation key (see routes/auth.py)
  auth_time: original login time (epoch s); rides forward across refreshes so
       the forced-reauth ceiling anchors to the login, not the last refresh
  iat, nbf, exp: standard
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from jose import JWTError, jwt

from app.config import get_settings

ISSUER = "shield-api"
ALGORITHM = "HS256"
# "mfa_pending" is a short-lived token issued after the password factor when a
# user has MFA enrolled; it authorizes ONLY POST /auth/mfa/verify-login, which
# exchanges it for the full access+refresh pair (Sprint 6 T4, D-027).
TokenType = Literal["access", "refresh", "mfa_pending"]
_VALID_TOKEN_TYPES = ("access", "refresh", "mfa_pending")


class TokenError(ValueError):
    """Raised when a token is missing, malformed, expired, or doesn't verify."""


@dataclass(frozen=True)
class TokenPayload:
    sub: uuid.UUID
    role: str
    typ: TokenType
    jti: uuid.UUID
    exp: datetime
    # Original login time (Sprint 3 T2). Rides forward unchanged across
    # refreshes so /auth/refresh can enforce the daily forced-reauth ceiling
    # against the original login, not the last refresh. Optional so tokens
    # minted before this claim existed still parse (C0).
    auth_time: datetime | None = None


def _ttl_for(typ: TokenType) -> timedelta:
    s = get_settings()
    if typ == "access":
        seconds = s.jwt_access_ttl_seconds
    elif typ == "mfa_pending":
        seconds = s.jwt_mfa_pending_ttl_seconds
    else:
        seconds = s.jwt_refresh_ttl_seconds
    return timedelta(seconds=seconds)


def _now() -> datetime:
    return datetime.now(UTC)


def issue_token(
    *,
    subject: uuid.UUID,
    role: str,
    typ: TokenType = "access",
    auth_time: datetime | None = None,
    additional_claims: dict | None = None,
) -> tuple[str, TokenPayload]:
    """Sign and return a token plus its decoded payload.

    `auth_time` is the original login time. Pass it forward on refresh so the
    forced-reauth ceiling anchors to the original login; omit it on a fresh
    login/register and it defaults to now.
    """
    settings = get_settings()
    now = _now()
    exp = now + _ttl_for(typ)
    jti = uuid.uuid4()
    effective_auth_time = auth_time or now

    claims: dict = {
        "iss": ISSUER,
        "aud": settings.keycloak_audience,
        "sub": str(subject),
        "role": role,
        "typ": typ,
        "jti": str(jti),
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "auth_time": int(effective_auth_time.timestamp()),
    }
    if additional_claims:
        claims.update(additional_claims)

    token = jwt.encode(claims, settings.jwt_signing_secret, algorithm=ALGORITHM)
    payload = TokenPayload(
        sub=subject, role=role, typ=typ, jti=jti, exp=exp, auth_time=effective_auth_time
    )
    return token, payload


def verify_token(token: str, *, expected_type: TokenType | None = None) -> TokenPayload:
    """Verify a token's signature, audience, expiry, and type.

    Raises TokenError on any failure. Does NOT consult a revocation list -
    that lands in Phase 1 stage 3b alongside logout.
    """
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_signing_secret,
            algorithms=[ALGORITHM],
            audience=settings.keycloak_audience,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "typ", "jti", "role"]},
        )
    except JWTError as exc:
        raise TokenError(f"Token verification failed: {exc}") from exc

    typ = claims.get("typ")
    if expected_type is not None and typ != expected_type:
        raise TokenError(f"Token type mismatch: expected {expected_type}, got {typ}")
    if typ not in _VALID_TOKEN_TYPES:
        raise TokenError(f"Unknown token type: {typ!r}")

    try:
        sub = uuid.UUID(claims["sub"])
        jti = uuid.UUID(claims["jti"])
    except (KeyError, ValueError) as exc:
        raise TokenError(f"Malformed token claims: {exc}") from exc

    raw_auth_time = claims.get("auth_time")
    auth_time = (
        datetime.fromtimestamp(int(raw_auth_time), UTC) if raw_auth_time is not None else None
    )

    return TokenPayload(
        sub=sub,
        role=str(claims["role"]),
        typ=typ,  # type: ignore[arg-type]
        jti=jti,
        exp=datetime.fromtimestamp(int(claims["exp"]), UTC),
        auth_time=auth_time,
    )
