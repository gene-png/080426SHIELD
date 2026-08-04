"""Hybrid OIDC exchange route (Sprint 9 T4, D-032).

``POST /auth/oidc/exchange`` is the ONE door through which a Keycloak identity
enters SHIELD. Keycloak owns the browser login and MFA; the web app hands us the
resulting Keycloak ACCESS token, we verify it once (``app.security.oidc``), match
it to an EXISTING local user by verified email (no JIT provisioning), TOFU-bind
the Keycloak subject, and mint a plain D-020 HS256 pair in its place. A Keycloak
token is never accepted as an API bearer.

The local DB stays authoritative: the pair's role comes from ``user.role`` (the
Keycloak ``roles`` claim is ignored for authz), the exchange bypasses local TOTP
MFA (Keycloak owns MFA on this path), does NOT consult the local password
lockout (Keycloak's bruteForceProtected owns SSO lockout — honoring the local
lock would let a password-endpoint attacker DoS SSO users), and does NOT stamp
local ``email_verified_at``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.logging import get_logger
from app.models.user import User
from app.routes.auth import _issue_pair, _normalize_email, _register_successful_login
from app.schemas.auth import OidcExchangeRequest, OidcExchangeResponse, UserResponse
from app.security.oidc import OidcError, verify_access_token
from app.security.rate_limit import RateLimiter, get_rate_limiter

router = APIRouter(prefix="/auth/oidc", tags=["auth"])

log = get_logger("app.routes.oidc")


@router.post(
    "/exchange",
    response_model=OidcExchangeResponse,
    summary="Exchange a verified Keycloak access token for a SHIELD pair (D-032)",
)
def exchange(
    body: OidcExchangeRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> OidcExchangeResponse:
    settings = get_settings()

    # Flag off: refuse loudly. The route is always registered (unlike the web
    # provider), so the flag is the single gate.
    if not settings.shield_auth_oidc_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "reason": "oidc_disabled",
                "message": "Single sign-on is not enabled on this deployment.",
            },
        )

    # 1) Verify the token's signature + registered claims (iss/aud/exp/iat/sub,
    #    RS256-only). A JWKS outage surfaces as a typed 503 here.
    try:
        claims = verify_access_token(body.keycloak_access_token)
    except OidcError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"reason": exc.reason, "message": exc.message},
        ) from exc

    # 2) Rate-limit AFTER signature verification (an unverified token is cheap to
    #    reject above; keying on the verified sub throttles a real identity).
    limiter.enforce_auth(request, f"oidc:{claims['sub']}")

    # 3) azp names the requesting client; it must be OUR web client. aud names
    #    the resource server (shield-api), so a correctly signed token minted to a
    #    DIFFERENT client would still pass aud — reject it here (Codex finding).
    if claims.get("azp") != settings.keycloak_client_id:
        log.info("oidc.rejected_azp", azp=claims.get("azp"))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "reason": "oidc_token_invalid",
                "message": "The token was not issued to this application.",
            },
        )

    # 4) Required identity claims.
    email_raw = claims.get("email")
    if not email_raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "reason": "oidc_claims_missing",
                "message": "The Keycloak token does not carry an email claim.",
            },
        )
    if claims.get("email_verified") is not True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "reason": "oidc_email_unverified",
                "message": "Your email address is not verified in the identity provider.",
            },
        )

    # 5) Match an EXISTING local account by normalized email. No JIT provisioning
    #    (D-032): an unknown identity is refused, never created.
    email = _normalize_email(email_raw)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        log.info("oidc.rejected_no_local_account")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "reason": "oidc_no_local_account",
                "message": "No SHIELD account exists for that identity. Contact your "
                "administrator to be added.",
            },
        )
    if not user.is_active:
        log.info("oidc.rejected_inactive", user_id=str(user.id))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "reason": "oidc_user_inactive",
                "message": "This account is deactivated.",
            },
        )

    # 6) TOFU sub binding: stamp on first exchange, reject a changed subject.
    sub = str(claims["sub"])
    if user.keycloak_sub is None:
        user.keycloak_sub = sub
        log.info("oidc.sub_bound", user_id=str(user.id))
    elif user.keycloak_sub != sub:
        log.warning("oidc.rejected_sub_mismatch", user_id=str(user.id))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "reason": "oidc_sub_mismatch",
                "message": "This account is already linked to a different identity-provider "
                "subject.",
            },
        )

    # 7) Success: reuse the shared credentials bookkeeping (clears lockout
    #    counters, stamps last_login_at, audits user.login) and mint the pair.
    #    The role rides from the DB, so a token claiming elevated roles for a
    #    client-role user still mints CLIENT tokens.
    _register_successful_login(db, user)
    pair = _issue_pair(user)
    db.commit()
    db.refresh(user)
    log.info("oidc.exchange_success", user_id=str(user.id), role=user.role.value)

    return OidcExchangeResponse(
        user=UserResponse.model_validate(user, from_attributes=True),
        tokens=pair,
    )
