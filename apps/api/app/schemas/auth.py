"""Auth-route request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth 2.0 token_type field, not a credential
    access_expires_at: datetime
    refresh_expires_at: datetime


class LoginResult(BaseModel):
    """Outcome of POST /auth/login (Sprint 6 T4, D-027).

    Two shapes on one model:
      - No MFA (back-compat): the full access+refresh pair is populated and
        ``mfa_required`` is False — identical field names to the old
        TokenPairResponse, so existing clients keep working unchanged.
      - MFA enrolled: the pair fields stay null, ``mfa_required`` is True, and
        ``mfa_pending_token`` carries the short-lived token that
        ``/auth/mfa/verify-login`` exchanges for the real pair.
    """

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"  # noqa: S105 - OAuth 2.0 token_type field, not a credential
    access_expires_at: datetime | None = None
    refresh_expires_at: datetime | None = None
    mfa_required: bool = False
    mfa_pending_token: str | None = None  # noqa: S105 - short-lived JWT, not a static credential
    # Set when SHIELD_AUTH_REQUIRE_MFA is on and the user has NOT yet enrolled.
    # The pair is still issued (first enrollment needs an authenticated
    # session), but the UI must route the user to enroll before proceeding.
    mfa_enrollment_required: bool = False


class MfaEnrollResponse(BaseModel):
    """The provisioning material an authenticator app needs, shown once."""

    secret: str
    otpauth_uri: str


class MfaVerifyRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class MfaVerifyResponse(BaseModel):
    """Recovery codes are returned exactly once, at successful enrollment."""

    mfa_enrolled: bool = True
    recovery_codes: list[str]


class MfaLoginRequest(BaseModel):
    mfa_pending_token: str
    # A TOTP (6 digits) OR a recovery code (XXXX-XXXX); disambiguated server-side.
    code: str = Field(min_length=1, max_length=64)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)


class VerifyEmailResponse(BaseModel):
    email_verified: bool = True


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    password: str = Field(min_length=12, max_length=256)


class EmailActionResponse(BaseModel):
    """Uniform response for the enumeration-safe endpoints (resend, forgot,
    reset). The same message is returned whether or not the account existed."""

    message: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    display_name: str | None
    title: str | None
    phone: str | None
    timezone: str
    is_active: bool
    mfa_enrolled: bool
    email_verified_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    # Nullable for platform admin; set for client-role users.
    client_id: uuid.UUID | None = None


class RegisterResponse(BaseModel):
    user: UserResponse
    tokens: TokenPairResponse
    is_primary_poc: bool


class OidcExchangeRequest(BaseModel):
    """The Keycloak ACCESS token (it carries aud=shield-api via the realm's
    audience mapper). Exchanged for a plain SHIELD pair (Sprint 9 T4, D-032)."""

    keycloak_access_token: str = Field(min_length=1)


class OidcExchangeResponse(BaseModel):
    """Result of a successful hybrid OIDC exchange: the matched local user plus a
    freshly minted SHIELD D-020 pair. Mirrors RegisterResponse minus the
    registration-only is_primary_poc flag (no /auth/me follow-up needed)."""

    user: UserResponse
    tokens: TokenPairResponse
