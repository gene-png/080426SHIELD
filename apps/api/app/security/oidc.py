"""Keycloak access-token verification for the hybrid OIDC exchange (D-032).

This is the ONLY place a Keycloak token is ever honored — ``routes/oidc.py``
verifies one here and mints a plain D-020 HS256 pair in its place; Keycloak
tokens are never accepted as API bearers anywhere else.

The verifier is a config-shape-only crypto boundary: it checks the RS256
signature (alg-confusion guarded by an RS256-only algorithms list), the pinned
``iss``/``aud``, and the required ``exp``/``iat``/``sub`` claims. Everything
downstream (``azp``, ``email``, ``email_verified``, the local-account lookup and
TOFU sub binding) is SHIELD business policy and lives in the route.

JWKS keys are cached process-wide with a 300s TTL behind a ``threading.Lock``. A
token bearing an unknown ``kid`` forces EXACTLY ONE refetch (Keycloak key
rotation) before it is rejected — never an unbounded refetch loop. The raw fetch
is isolated in the module-level ``_fetch_jwks`` so unit tests monkeypatch it and
touch no network.
"""

from __future__ import annotations

import threading
import time

import httpx
from jose import jwt
from jose.exceptions import JWTError

from app.config import get_settings
from app.logging import get_logger

log = get_logger("app.security.oidc")

_JWKS_TTL_SECONDS = 300
_HTTP_TIMEOUT_SECONDS = 5.0

# Process-wide JWKS cache. Rebound wholesale on refresh (never mutated in place),
# guarded by the lock. `_jwks_fetched_at` uses a monotonic clock so a wall-clock
# adjustment cannot wedge the TTL.
_lock = threading.Lock()
_jwks_by_kid: dict[str, dict] = {}
_jwks_fetched_at: float | None = None


class OidcError(Exception):
    """A Keycloak token failed verification.

    Carries the typed ``reason`` + friendly ``message`` + HTTP ``status_code`` so
    the route maps it straight onto the D-016 dict-detail HTTPException without a
    translation table.
    """

    def __init__(self, *, status_code: int, reason: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason
        self.message = message


def _fetch_jwks() -> dict:
    """Raw JWKS GET against ``keycloak_jwks_url``. Isolated for monkeypatching.

    Raises the underlying ``httpx`` error on any transport/status failure; the
    caller translates that into a typed 503.
    """
    url = get_settings().keycloak_jwks_url
    log.info("oidc.jwks_fetch", url=url)
    resp = httpx.get(url, timeout=_HTTP_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json()


def _index_jwks(raw: dict) -> dict[str, dict]:
    return {key["kid"]: key for key in raw.get("keys", []) if "kid" in key}


def _refresh_jwks() -> None:
    """Fetch + index the JWKS into the cache. Must be called under ``_lock``.

    Translates any ``httpx`` failure into a typed 503 naming the URL and the flag
    so an operator sees exactly what to fix.
    """
    global _jwks_by_kid, _jwks_fetched_at
    try:
        raw = _fetch_jwks()
    except httpx.HTTPError as exc:
        url = get_settings().keycloak_jwks_url
        raise OidcError(
            status_code=503,
            reason="oidc_jwks_unavailable",
            message=(
                f"Could not reach the Keycloak JWKS endpoint at {url} while "
                "SHIELD_AUTH_OIDC_ENABLED is on. Keycloak may be down or the URL "
                "may be misconfigured."
            ),
        ) from exc
    _jwks_by_kid = _index_jwks(raw)
    _jwks_fetched_at = time.monotonic()


def _cache_fresh() -> bool:
    if _jwks_fetched_at is None:
        return False
    return (time.monotonic() - _jwks_fetched_at) < _JWKS_TTL_SECONDS


def _signing_key_for(kid: str) -> dict:
    """Return the JWK for ``kid``, refetching the JWKS at most once on a miss.

    - Cold/stale cache -> refresh once (initial population / TTL expiry).
    - ``kid`` still unknown afterward -> EXACTLY ONE forced refetch (Keycloak may
      have rotated its keys). Still unknown -> reject 401.
    """
    with _lock:
        if not _cache_fresh():
            _refresh_jwks()  # may raise OidcError(503)
        key = _jwks_by_kid.get(kid)
        if key is not None:
            return key
        # Unknown kid: force exactly one refetch to pick up a rotation.
        _refresh_jwks()  # may raise OidcError(503)
        key = _jwks_by_kid.get(kid)
    if key is None:
        raise OidcError(
            status_code=401,
            reason="oidc_token_invalid",
            message="The token was signed by a key not present in the Keycloak JWKS.",
        )
    return key


def verify_access_token(token: str) -> dict:
    """Verify a Keycloak access token and return its decoded claims.

    RS256 only (HS256/none rejected — alg-confusion guard); ``iss`` pinned to
    ``keycloak_issuer``, ``aud`` to ``keycloak_audience``; ``exp``/``iat``/``sub``
    required. Raises :class:`OidcError` (401/503) on any failure. Business claims
    (azp/email/…) are the route's job.
    """
    settings = get_settings()
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise OidcError(
            status_code=401,
            reason="oidc_token_invalid",
            message="The Keycloak token header is malformed.",
        ) from exc

    kid = header.get("kid")
    if not kid:
        raise OidcError(
            status_code=401,
            reason="oidc_token_invalid",
            message="The Keycloak token header is missing a key id (kid).",
        )

    jwk = _signing_key_for(kid)  # may raise OidcError(401/503)

    try:
        claims = jwt.decode(
            token,
            jwk,
            algorithms=["RS256"],
            audience=settings.keycloak_audience,
            issuer=settings.keycloak_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except JWTError as exc:
        raise OidcError(
            status_code=401,
            reason="oidc_token_invalid",
            message="The Keycloak token failed verification (signature, issuer, "
            "audience, or expiry).",
        ) from exc
    return claims
