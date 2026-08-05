"""Auth routes: register, login, me, refresh, logout.

Master Spec §2 + §4.5:
  - Email + password only for v1 (MFA + email verification deferred behind
    feature flags).
  - 15-minute access JWT, refresh JWT, 30-minute idle, daily forced re-auth.
  - Account lockout: 10 failed attempts in 15 minutes
    (`SHIELD_ACCOUNT_LOCKOUT_*`).

DECISIONS.md D-004 (Q2): self-registration allowed. First registrant on a
fresh deployment becomes the client's Primary POC and is granted the
`admin` role for that engagement (per spec - "a Kentro consultant verifies
and attaches" later; the bootstrap user is operating-on-behalf-of the
first consultant on this deployment).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.db.session import get_db
from app.dependencies import current_user
from app.email import (
    generate_token,
    hash_token,
    send_password_reset_email,
    send_verification_email,
)
from app.logging import get_logger
from app.models._common import utcnow
from app.models.client import Client
from app.models.client_domain import ClientDomain
from app.models.email_token import EmailToken, EmailTokenPurpose
from app.models.user import User, UserRole
from app.models.user_recovery_code import UserRecoveryCode
from app.schemas.auth import (
    EmailActionResponse,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResult,
    MfaEnrollResponse,
    MfaLoginRequest,
    MfaVerifyRequest,
    MfaVerifyResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenPairResponse,
    UserResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from app.security.email_domains import domain_of, is_generic_provider
from app.security.jwt import TokenError, issue_token, verify_token
from app.security.password import (
    PasswordPolicyError,
    hash_password,
    verify_password,
)
from app.security.rate_limit import RateLimiter, get_rate_limiter
from app.security.totp import (
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    generate_secret,
    hash_recovery_code,
    provisioning_uri,
    verify_recovery_code,
    verify_totp,
)

router = APIRouter(prefix="/auth", tags=["auth"])

log = get_logger("app.routes.auth")

# Precomputed Argon2 hash for the unknown-user code path. Keeps wrong-email
# response time comparable to wrong-password response time so an attacker
# can't enumerate accounts by timing (OWASP A07 hardening).
_DUMMY_HASH_FOR_TIMING = hash_password("dummy-password-for-timing-only-do-not-use")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _user_count(db: Session) -> int:
    return db.execute(select(User.id)).scalars().unique().all().__len__()


def _normalize_email(raw: str) -> str:
    return raw.strip().lower()


def _issue_pair(user: User, *, auth_time: datetime | None = None) -> TokenPairResponse:
    """Issue an access + refresh pair and record the refresh jti for rotation.

    On a fresh login/register pass `auth_time=None` (defaults to now). On
    refresh pass the original login time so the forced-reauth ceiling anchors
    to the login, not the refresh. The refresh token's jti is stored on the
    user as the single valid one; any previously issued refresh token is thereby
    rotated out (its jti no longer matches).
    """
    access_token, access_payload = issue_token(
        subject=user.id, role=user.role.value, typ="access", auth_time=auth_time
    )
    refresh_token, refresh_payload = issue_token(
        subject=user.id, role=user.role.value, typ="refresh", auth_time=auth_time
    )
    user.active_refresh_jti = str(refresh_payload.jti)
    log.info(
        "auth.tokens_issued",
        user_id=str(user.id),
        refresh_jti=str(refresh_payload.jti),
        auth_time=refresh_payload.auth_time.isoformat() if refresh_payload.auth_time else None,
    )
    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_at=access_payload.exp,
        refresh_expires_at=refresh_payload.exp,
    )


def _login_result_from_pair(pair: TokenPairResponse) -> LoginResult:
    """Wrap a completed token pair in the LoginResult shape (mfa_required=False)."""
    return LoginResult(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        access_expires_at=pair.access_expires_at,
        refresh_expires_at=pair.refresh_expires_at,
    )


def _as_aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; coerce to UTC-aware for comparison."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _is_locked(user: User) -> bool:
    locked = _as_aware(user.locked_until_at)
    return locked is not None and locked > utcnow()


def _register_failed_attempt(db: Session, user: User) -> None:
    settings = get_settings()
    now = utcnow()
    window = timedelta(seconds=settings.shield_account_lockout_window_seconds)
    last_failed = _as_aware(user.last_failed_login_at)
    if last_failed is None or now - last_failed > window:
        user.failed_login_count = 1
    else:
        user.failed_login_count += 1
    user.last_failed_login_at = now
    if user.failed_login_count >= settings.shield_account_lockout_max_attempts:
        user.locked_until_at = now + window
        audit(
            db,
            action="user.locked",
            target_type="user",
            target_id=user.id,
            actor_user_id=user.id,
            details={"reason": "max_failed_login_attempts"},
        )


def _register_successful_login(db: Session, user: User) -> None:
    user.failed_login_count = 0
    user.last_failed_login_at = None
    user.locked_until_at = None
    user.last_login_at = utcnow()
    audit(
        db,
        action="user.login",
        target_type="user",
        target_id=user.id,
        actor_user_id=user.id,
    )


# -----------------------------------------------------------------------------
# Email tokens (verification + password reset) — Sprint 6 T5, D-028
# -----------------------------------------------------------------------------

# One uniform message for every enumeration-safe endpoint (resend / forgot /
# reset). Returned whether or not the account existed, so a caller can never
# probe which emails are registered (OWASP A07 / A01).
_UNIFORM_EMAIL_ACTION_MSG = (
    "If an account matches that email, we've sent a message with next steps. "
    "Check your inbox (and spam)."
)


def _issue_email_token(
    db: Session, user: User, purpose: EmailTokenPurpose, ttl_seconds: int
) -> str:
    """Create a single-use token row (storing only its hash) and return the raw
    token for the email link. Callers commit as part of their own transaction."""
    raw = generate_token()
    db.add(
        EmailToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            purpose=purpose,
            expires_at=utcnow() + timedelta(seconds=ttl_seconds),
        )
    )
    return raw


def _consume_email_token(
    db: Session, raw_token: str, purpose: EmailTokenPurpose
) -> EmailToken | None:
    """Return the matching unused, unexpired token for ``purpose`` or None.

    Does NOT mark it used — the caller stamps ``used_at`` only after the action
    it authorizes succeeds, so a failed action leaves the token replayable.
    """
    token = db.execute(
        select(EmailToken).where(
            EmailToken.token_hash == hash_token(raw_token),
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
    ).scalar_one_or_none()
    if token is None:
        return None
    if _as_aware(token.expires_at) is None or _as_aware(token.expires_at) < utcnow():
        return None
    return token


# -----------------------------------------------------------------------------
# Self-service tenant provisioning (D-034)
# -----------------------------------------------------------------------------


def _provision_self_serve_client(db: Session, *, legal_name: str) -> Client:
    """Create a brand-new tenant for a self-registering user (D-034).

    Used when no approved domain matches: a personal-email signup gets its own
    private org (never grouped), and the first user of a new company domain
    creates that org. The caller stamps ``primary_poc_user_id`` and (for a
    company domain) the ``ClientDomain`` mapping once the user row exists. The
    ``legal_name`` is a placeholder the org refines through the intake wizard.
    """
    client = Client(legal_name=legal_name)
    db.add(client)
    db.flush()
    log.info("auth.self_serve_client_provisioned", client_id=str(client.id))
    return client


def _resolve_registration_tenant(
    db: Session, *, email: str, display_name: str, is_first_user: bool
) -> tuple[UserRole, Client | None, bool, str | None]:
    """Decide the role + tenant for a registration (D-004 bootstrap + D-034 open
    self-registration).

    Returns ``(role, client, is_primary_poc, domain_to_map)`` where
    ``domain_to_map`` is the email domain to insert as a NEW ``ClientDomain``
    row (only when a fresh company-domain org was created), else ``None``.

    Policy:
      - First registrant on a fresh deployment → platform ADMIN, no tenant.
      - Personal mailbox provider (gmail, ...) → CLIENT in its OWN new private
        org, and NO domain mapping (personal emails are never grouped).
      - Known approved company domain → CLIENT joining that existing org.
      - Unknown company domain → CLIENT in a new org, and map the domain so
        later coworkers auto-join.
    """
    if is_first_user:
        return UserRole.ADMIN, None, True, None

    role = UserRole.CLIENT
    domain = domain_of(email)
    if not domain:
        # EmailStr guarantees an '@'; fail loudly rather than silently proceed.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"reason": "email_invalid", "message": "Enter a valid email address."},
        )

    if is_generic_provider(domain):
        client = _provision_self_serve_client(db, legal_name=display_name)
        return role, client, True, None

    approved = db.execute(
        select(ClientDomain).where(ClientDomain.domain == domain)
    ).scalar_one_or_none()
    if approved is not None:
        client = db.get(Client, approved.client_id)
        if client is None:
            # An approved domain whose client vanished — ClientDomain.client_id
            # is ON DELETE CASCADE, so this should be unreachable. Fail loudly.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "reason": "email_domain_unavailable",
                    "message": "The organization for that domain is no longer available.",
                },
            )
        return role, client, False, None

    # Unknown company domain: stand up a new org and map the domain.
    client = _provision_self_serve_client(db, legal_name=domain)
    return role, client, True, domain


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Self-register (D-004)",
)
def register(
    body: RegisterRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> RegisterResponse:
    email = _normalize_email(body.email)

    # Throttle before any expensive work (Argon2 hashing, DB writes). Per-IP +
    # per-account fixed windows; typed 429 with Retry-After (D-016).
    limiter.enforce_auth(request, email)

    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        # Typed detail (reason + message): the web sign-up form maps `reason`
        # to the right field/copy. Duplicate-email disclosure is consistent
        # with the domain-rejection copy below, which already tells the caller
        # whether their domain is approved (see DECISIONS.md D-016).
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "email_exists",
                "message": "An account already exists for that email.",
            },
        )

    try:
        password_hash = hash_password(body.password)
    except PasswordPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"reason": "password_policy", "message": str(exc)},
        ) from exc

    is_first_user = _user_count(db) == 0

    # Onboarding (D-004 bootstrap + D-034 open self-registration):
    #   - The first registrant on a fresh deployment bootstraps the platform
    #     admin (D-004, client_id=None). Further admins are seeded out-of-band.
    #   - After that, self-registration is OPEN (any email, no admin
    #     pre-approval) and auto-provisions the tenant (D-034):
    #       * a personal mailbox (gmail, ...) gets its OWN private org, unmapped
    #         (personal emails are never grouped);
    #       * a known approved company domain joins that existing org;
    #       * an unknown company domain stands up a new org AND maps the domain
    #         so later coworkers auto-join.
    settings = get_settings()

    # Two attempts: if two users on the SAME brand-new company domain register
    # concurrently, the loser's ClientDomain insert violates
    # uq_client_domain_domain. We roll back and retry — on the retry the domain
    # now exists, so the user simply joins that org instead of 500-ing.
    for attempt in (1, 2):
        try:
            role, client_for_user, is_primary_poc, domain_to_map = _resolve_registration_tenant(
                db,
                email=email,
                display_name=body.display_name,
                is_first_user=is_first_user,
            )

            user = User(
                email=email,
                password_hash=password_hash,
                role=role,
                display_name=body.display_name,
                title=body.title,
                phone=body.phone,
                timezone=body.timezone,
                last_login_at=utcnow(),
                client_id=client_for_user.id if client_for_user is not None else None,
            )
            db.add(user)
            db.flush()

            if client_for_user is not None and is_primary_poc:
                # First user of a freshly provisioned org is its primary contact.
                client_for_user.primary_poc_user_id = user.id
                audit(
                    db,
                    action="client.created",
                    target_type="client",
                    target_id=client_for_user.id,
                    actor_user_id=user.id,
                    details={"legal_name": client_for_user.legal_name, "source": "self_serve"},
                )
            if domain_to_map is not None:
                db.add(
                    ClientDomain(
                        client_id=client_for_user.id,
                        domain=domain_to_map,
                        created_by=user.id,
                    )
                )

            audit(
                db,
                action="user.created",
                target_type="user",
                target_id=user.id,
                actor_user_id=user.id,
                details={
                    "role": role.value,
                    "is_first_user": is_first_user,
                    "client_id": str(client_for_user.id) if client_for_user else None,
                },
            )

            # Email verification (D-028): always mint a verification token so the
            # flow works even in dev with delivery off; the SEND is gated inside
            # the sender. Failure to send (delivery on but SMTP down) is loud.
            verify_raw = _issue_email_token(
                db,
                user,
                EmailTokenPurpose.EMAIL_VERIFY,
                settings.email_verify_token_ttl_seconds,
            )

            tokens = _issue_pair(user)
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            if attempt == 2:
                raise
            log.info("auth.register_domain_race_retry", email_domain=domain_of(email))

    db.refresh(user)

    send_verification_email(to=user.email, token=verify_raw)
    log.info("auth.verification_email_issued", user_id=str(user.id))

    return RegisterResponse(
        user=UserResponse.model_validate(user, from_attributes=True),
        tokens=tokens,
        is_primary_poc=is_primary_poc,
    )


@router.post(
    "/login",
    response_model=LoginResult,
    summary="Email + password login (MFA challenge when enrolled)",
)
def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> LoginResult:
    email = _normalize_email(body.email)

    # Throttle before the timing-safe Argon2 verify so a credential-stuffing
    # flood is cheap to reject; account lockout remains the second line.
    limiter.enforce_auth(request, email)

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    # Defer the "no such user" branch to the same response shape + timing
    # the wrong-password branch produces, to avoid an account-existence
    # oracle (OWASP A07).
    if user is None:
        # Run a dummy verify against a real hash so wrong-email timing is
        # comparable to wrong-password timing (OWASP A07).
        verify_password(body.password, _DUMMY_HASH_FOR_TIMING)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if _is_locked(user):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account is temporarily locked. Try again later.",
        )

    matched, needs_rehash = verify_password(body.password, user.password_hash)
    if not matched:
        _register_failed_attempt(db, user)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if needs_rehash:
        user.password_hash = hash_password(body.password)

    # Deactivated-account gate (issue 3). `User.is_active` was already honoured
    # by the refresh, MFA-verify, and password-reset flows, but NOT here — so an
    # admin deactivating a user did not actually stop them signing in. Checked
    # AFTER the password verify, deliberately: refusing earlier would turn the
    # endpoint into an oracle telling an unauthenticated caller which accounts
    # exist and are disabled (OWASP A07), the same reason the "no such user"
    # branch is deferred above.
    if not user.is_active:
        db.commit()
        log.info("auth.login_blocked_inactive", user_id=str(user.id))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "reason": "account_deactivated",
                "message": (
                    "This account has been deactivated. Contact your SHIELD "
                    "administrator if you think this is a mistake."
                ),
            },
        )

    # Email verification gate (Sprint 6 T5, D-028). When the flag is on, a user
    # whose address is not yet verified cannot complete login (nor start the MFA
    # step). Do NOT reset the lockout counters here: login is not complete, and
    # resetting on a correct password before the second gate is cleared would
    # let an attacker who has the password wipe accrued failures at will
    # (counters reset only on a fully successful login, T10). commit() persists
    # any password rehash above.
    if get_settings().shield_auth_require_email_verify and user.email_verified_at is None:
        db.commit()
        log.info("auth.login_blocked_unverified", user_id=str(user.id))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "reason": "email_not_verified",
                "message": (
                    "Please verify your email address before signing in. Check your "
                    "inbox for the confirmation link, or request a new one."
                ),
            },
        )

    # Second factor (Sprint 6 T4, D-027). If the user has TOTP MFA enrolled, the
    # password is only the FIRST factor: issue a short-lived mfa_pending token
    # (good for nothing but /auth/mfa/verify-login) INSTEAD of the real pair.
    # Login is NOT complete, so the lockout counters are NOT reset here — they
    # clear only once BOTH factors succeed (_register_successful_login). Resetting
    # at the challenge would let an attacker with the password evade second-factor
    # lockout by re-logging between guesses (T10). commit() persists any rehash.
    if user.mfa_enrolled:
        pending_token, _payload = issue_token(
            subject=user.id, role=user.role.value, typ="mfa_pending"
        )
        db.commit()
        log.info("auth.mfa_challenge_issued", user_id=str(user.id))
        return LoginResult(mfa_required=True, mfa_pending_token=pending_token)

    _register_successful_login(db, user)
    pair = _issue_pair(user)
    db.commit()

    # SHIELD_AUTH_REQUIRE_MFA gates enforcement (D-027): with the flag on, a user
    # who has NOT enrolled still gets a session (first enrollment needs one), but
    # the result flags that the UI must route them to enroll before proceeding.
    # The flag no longer refuses to boot (that was the old config.py behavior).
    result = _login_result_from_pair(pair)
    if get_settings().shield_auth_require_mfa and not user.mfa_enrolled:
        result.mfa_enrollment_required = True
        log.info("auth.mfa_enrollment_required", user_id=str(user.id))
    return result


@router.post(
    "/refresh",
    response_model=TokenPairResponse,
    summary="Refresh access + refresh tokens",
)
def refresh(
    body: RefreshRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenPairResponse:
    settings = get_settings()
    try:
        payload = verify_token(body.refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        ) from exc

    user = db.get(User, payload.sub)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is no longer active.",
        )

    # (a) Forced re-auth ceiling. Checked before rotation: once a session is
    # past the ceiling the user must sign in fresh regardless of rotation state.
    # A token with no auth_time claim predates this control and expires within
    # the short refresh TTL, so we cannot (and need not) enforce a ceiling on it.
    if payload.auth_time is not None:
        age = utcnow() - payload.auth_time
        if age.total_seconds() > settings.shield_forced_reauth_seconds:
            log.info(
                "auth.reauth_required",
                user_id=str(user.id),
                auth_time=payload.auth_time.isoformat(),
                age_seconds=int(age.total_seconds()),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "reason": "reauth_required",
                    "message": "Your session has reached its daily limit. Please sign in again.",
                },
            )

    # (b) Rotation. Only the single most recently issued refresh token is valid;
    # a replayed (already-rotated) token no longer matches and is rejected loudly.
    if user.active_refresh_jti != str(payload.jti):
        log.warning(
            "auth.refresh_reused",
            user_id=str(user.id),
            presented_jti=str(payload.jti),
            active_jti=user.active_refresh_jti,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "reason": "refresh_reused",
                "message": "This session has been superseded. Please sign in again.",
            },
        )

    tokens = _issue_pair(user, auth_time=payload.auth_time)
    db.commit()
    return tokens


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout (audited; token revocation list lands in v1.x)",
)
def logout(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    audit(
        db,
        action="user.logout",
        target_type="user",
        target_id=user.id,
        actor_user_id=user.id,
    )
    db.commit()


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Current authenticated user",
)
def me(user: Annotated[User, Depends(current_user)]) -> UserResponse:
    return UserResponse.model_validate(user, from_attributes=True)


# -----------------------------------------------------------------------------
# MFA (TOTP) — enroll, confirm, and the login second factor (Sprint 6 T4, D-027)
# -----------------------------------------------------------------------------


@router.post(
    "/mfa/enroll",
    response_model=MfaEnrollResponse,
    summary="Begin TOTP MFA enrollment (returns provisioning URI + secret)",
)
def mfa_enroll(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MfaEnrollResponse:
    """Generate a fresh TOTP secret and return its otpauth:// provisioning URI.

    The secret is stored encrypted immediately but enrollment is NOT active
    until /auth/mfa/verify confirms a code (that is what flips mfa_enrolled and
    mints recovery codes). Re-enrolling before confirmation simply rotates the
    pending secret. An ALREADY-enrolled user is refused (409): overwriting a
    confirmed secret would silently break their working authenticator
    (``mfa_enrolled`` stays True while the stored secret changes) until they
    re-confirmed a new QR. Rotating an active factor needs an explicit
    disable-with-current-factor flow (Sprint 7), not a bare re-enroll. The web UI
    already hides the button when enrolled; this guards the raw endpoint against
    a direct/scripted call.
    """
    if user.mfa_enrolled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "mfa_already_enrolled",
                "message": "Two-factor authentication is already enabled on this account.",
            },
        )
    secret = generate_secret()
    user.mfa_totp_secret = encrypt_secret(secret)
    audit(
        db,
        action="user.mfa_enroll_started",
        target_type="user",
        target_id=user.id,
        actor_user_id=user.id,
    )
    db.commit()
    log.info("auth.mfa_enroll_started", user_id=str(user.id))
    return MfaEnrollResponse(
        secret=secret,
        otpauth_uri=provisioning_uri(secret, user.email),
    )


@router.post(
    "/mfa/verify",
    response_model=MfaVerifyResponse,
    summary="Confirm TOTP enrollment; returns one-time recovery codes",
)
def mfa_verify(
    body: MfaVerifyRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> MfaVerifyResponse:
    """Confirm a code against the pending secret, flip mfa_enrolled, and issue a
    fresh set of one-time recovery codes (returned in plaintext exactly once)."""
    limiter.enforce_auth(request, user.email)

    # A locked account cannot brute-force the enrollment-confirm code either
    # (T10): the second-factor guesses feed the same lockout counter as password
    # failures, so once locked we refuse until the window elapses.
    if _is_locked(user):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account is temporarily locked. Try again later.",
        )

    if not user.mfa_totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "reason": "mfa_not_started",
                "message": "Start MFA enrollment before verifying a code.",
            },
        )

    if not verify_totp(decrypt_secret(user.mfa_totp_secret), body.code):
        # A wrong confirmation code counts toward account lockout (T10).
        _register_failed_attempt(db, user)
        db.commit()
        log.info("auth.mfa_verify_rejected", user_id=str(user.id))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "reason": "mfa_invalid_code",
                "message": "That code is incorrect or has expired. Try again.",
            },
        )

    user.mfa_enrolled = True
    # Replace any prior recovery codes (re-verify resets the set).
    for old in db.execute(
        select(UserRecoveryCode).where(UserRecoveryCode.user_id == user.id)
    ).scalars():
        db.delete(old)

    plaintext_codes = generate_recovery_codes()
    for code in plaintext_codes:
        db.add(UserRecoveryCode(user_id=user.id, code_hash=hash_recovery_code(code)))

    audit(
        db,
        action="user.mfa_enrolled",
        target_type="user",
        target_id=user.id,
        actor_user_id=user.id,
    )
    db.commit()
    log.info("auth.mfa_enrolled", user_id=str(user.id))
    return MfaVerifyResponse(recovery_codes=plaintext_codes)


@router.post(
    "/mfa/verify-login",
    response_model=TokenPairResponse,
    summary="Complete an MFA login challenge (TOTP or recovery code)",
)
def mfa_verify_login(
    body: MfaLoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> TokenPairResponse:
    """Exchange a valid mfa_pending token + second factor for the full pair.

    The second factor is either a current TOTP code or an unused recovery code
    (recovery codes are single-use — a match is consumed by stamping used_at).
    """
    try:
        payload = verify_token(body.mfa_pending_token, expected_type="mfa_pending")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired MFA challenge. Please sign in again.",
        ) from exc

    user = db.get(User, payload.sub)
    if user is None or not user.is_active or not user.mfa_enrolled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired MFA challenge. Please sign in again.",
        )

    # Throttle the second-factor guess rate per account (the pending token is
    # short-lived, but rate-limiting still blunts online code guessing).
    limiter.enforce_auth(request, user.email)

    # A locked account cannot complete the challenge (T10): once the shared
    # lockout counter is tripped — by password OR second-factor failures — even
    # a correct code is refused until the window elapses.
    if _is_locked(user):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account is temporarily locked. Try again later.",
        )

    verified = user.mfa_totp_secret is not None and verify_totp(
        decrypt_secret(user.mfa_totp_secret), body.code
    )
    used_recovery = False
    if not verified:
        # Fall back to a single-use recovery code.
        for candidate in db.execute(
            select(UserRecoveryCode).where(
                UserRecoveryCode.user_id == user.id,
                UserRecoveryCode.used_at.is_(None),
            )
        ).scalars():
            if verify_recovery_code(body.code, candidate.code_hash):
                candidate.used_at = utcnow()
                verified = True
                used_recovery = True
                break

    if not verified:
        # A wrong second factor counts toward account lockout (T10), so an
        # attacker holding a valid mfa_pending token cannot grind codes forever.
        _register_failed_attempt(db, user)
        db.commit()
        log.info("auth.mfa_login_rejected", user_id=str(user.id))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "reason": "mfa_invalid_code",
                "message": "That code is incorrect or has expired. Try again.",
            },
        )

    _register_successful_login(db, user)
    audit(
        db,
        action="user.mfa_login_verified",
        target_type="user",
        target_id=user.id,
        actor_user_id=user.id,
        details={"via": "recovery_code" if used_recovery else "totp"},
    )
    pair = _issue_pair(user)
    db.commit()
    log.info("auth.mfa_login_verified", user_id=str(user.id), via_recovery=used_recovery)
    return pair


# -----------------------------------------------------------------------------
# Email verification + password reset (Sprint 6 T5, D-028)
# -----------------------------------------------------------------------------


@router.post(
    "/verify-email",
    response_model=VerifyEmailResponse,
    summary="Confirm an email address from a verification token",
)
def verify_email(
    body: VerifyEmailRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> VerifyEmailResponse:
    """Consume an email-verification token and stamp ``email_verified_at``.

    The token is the secret, so there is no account-enumeration concern here: an
    invalid/expired/spent token is rejected with a typed 400. Single-use — a
    valid token is marked spent on success.
    """
    limiter.enforce_auth(request, "verify-email")

    token = _consume_email_token(db, body.token, EmailTokenPurpose.EMAIL_VERIFY)
    if token is None:
        log.info("auth.verify_email_rejected")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "reason": "invalid_token",
                "message": "That verification link is invalid or has expired. "
                "Request a new one.",
            },
        )

    user = db.get(User, token.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "reason": "invalid_token",
                "message": "That verification link is invalid or has expired. "
                "Request a new one.",
            },
        )

    token.used_at = utcnow()
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    audit(
        db,
        action="user.email_verified",
        target_type="user",
        target_id=user.id,
        actor_user_id=user.id,
    )
    db.commit()
    log.info("auth.email_verified", user_id=str(user.id))
    return VerifyEmailResponse(email_verified=True)


@router.post(
    "/resend-verification",
    response_model=EmailActionResponse,
    summary="Resend the email-verification link (enumeration-safe)",
)
def resend_verification(
    body: ResendVerificationRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> EmailActionResponse:
    """Issue a fresh verification token when the account exists and is unverified.

    Always returns the same uniform message so a caller cannot learn whether an
    email is registered (OWASP A07).
    """
    email = _normalize_email(body.email)
    limiter.enforce_auth(request, email)

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None and user.email_verified_at is None:
        settings = get_settings()
        raw = _issue_email_token(
            db, user, EmailTokenPurpose.EMAIL_VERIFY, settings.email_verify_token_ttl_seconds
        )
        db.commit()
        send_verification_email(to=user.email, token=raw)
        log.info("auth.verification_email_resent", user_id=str(user.id))
    else:
        log.info("auth.resend_verification_noop")

    return EmailActionResponse(message=_UNIFORM_EMAIL_ACTION_MSG)


@router.post(
    "/forgot-password",
    response_model=EmailActionResponse,
    summary="Request a password-reset link (enumeration-safe)",
)
def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> EmailActionResponse:
    """Issue a password-reset token when the account exists.

    Uniform response regardless of existence (no enumeration). The reset token
    is short-lived (``password_reset_token_ttl_seconds``).
    """
    email = _normalize_email(body.email)
    limiter.enforce_auth(request, email)

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None and user.is_active:
        settings = get_settings()
        raw = _issue_email_token(
            db, user, EmailTokenPurpose.PASSWORD_RESET, settings.password_reset_token_ttl_seconds
        )
        audit(
            db,
            action="user.password_reset_requested",
            target_type="user",
            target_id=user.id,
            actor_user_id=user.id,
        )
        db.commit()
        send_password_reset_email(to=user.email, token=raw)
        log.info("auth.password_reset_requested", user_id=str(user.id))
    else:
        log.info("auth.forgot_password_noop")

    return EmailActionResponse(message=_UNIFORM_EMAIL_ACTION_MSG)


@router.post(
    "/reset-password",
    response_model=EmailActionResponse,
    summary="Set a new password from a reset token",
)
def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> EmailActionResponse:
    """Consume a password-reset token and set the new password.

    Single-use token; on success we also rotate out the current refresh token
    (``active_refresh_jti`` cleared) so any live session must re-authenticate,
    and clear any lockout so the user can immediately sign in.
    """
    limiter.enforce_auth(request, "reset-password")

    token = _consume_email_token(db, body.token, EmailTokenPurpose.PASSWORD_RESET)
    if token is None:
        log.info("auth.reset_password_rejected")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "reason": "invalid_token",
                "message": "That reset link is invalid or has expired. Request a new one.",
            },
        )

    user = db.get(User, token.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "reason": "invalid_token",
                "message": "That reset link is invalid or has expired. Request a new one.",
            },
        )

    try:
        new_hash = hash_password(body.password)
    except PasswordPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"reason": "password_policy", "message": str(exc)},
        ) from exc

    user.password_hash = new_hash
    token.used_at = utcnow()
    # Invalidate any other outstanding reset tokens for this user (a completed
    # reset should void every earlier request).
    for other in db.execute(
        select(EmailToken).where(
            EmailToken.user_id == user.id,
            EmailToken.purpose == EmailTokenPurpose.PASSWORD_RESET,
            EmailToken.used_at.is_(None),
        )
    ).scalars():
        other.used_at = utcnow()
    # Force re-auth on all sessions + clear lockout.
    user.active_refresh_jti = None
    user.failed_login_count = 0
    user.last_failed_login_at = None
    user.locked_until_at = None
    audit(
        db,
        action="user.password_reset",
        target_type="user",
        target_id=user.id,
        actor_user_id=user.id,
    )
    db.commit()
    log.info("auth.password_reset_completed", user_id=str(user.id))
    return EmailActionResponse(
        message="Your password has been reset. You can now sign in with your new password."
    )
