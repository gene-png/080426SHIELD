"""User model.

Two roles: admin (Kentro consultant, cross-client) and client (external
company user, tied to one client by email domain). An earlier read-only
second-consultant role was folded into admin (Work Order A3; see the
DECISIONS.md D-005/D-006 supersession erratum): multiple admins all see
and do the work, no separate approval gate. MFA enrollment column is
present in v1 but the flag default-false until SHIELD_AUTH_REQUIRE_MFA
flips on (spec §2 locked decisions).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    CLIENT = "client"


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("keycloak_sub", name="uq_users_keycloak_sub"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", native_enum=False, length=16),
        nullable=False,
    )

    display_name: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)

    client_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("client.id", ondelete="RESTRICT")
    )

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    mfa_enrolled: Mapped[bool] = mapped_column(default=False, nullable=False)
    # TOTP shared secret, Fernet-encrypted at rest (Sprint 6 T4, D-027). Set at
    # enroll, confirmed at verify (flips mfa_enrolled). Nullable/additive (C0):
    # pre-migration rows and users who never enroll simply carry no secret.
    mfa_totp_secret: Mapped[str | None] = mapped_column(String(512))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Lockout bookkeeping (Master Spec §4.5: 10 failed attempts in 15 min).
    failed_login_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_failed_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Refresh-token rotation (Sprint 3 T2): the jti of the single currently
    # valid refresh token. Each /auth/refresh mints a new refresh token and
    # overwrites this, so a replayed (already-rotated) refresh token no longer
    # matches and is rejected. Nullable/additive (C0): pre-migration rows and
    # any user who has not yet logged in simply have no active refresh token.
    active_refresh_jti: Mapped[str | None] = mapped_column(String(36))

    # Keycloak subject (TOFU-bound) for the hybrid OIDC exchange (Sprint 9 T4,
    # D-032). NULL until this user first completes POST /auth/oidc/exchange, at
    # which point the token's `sub` is stamped here; a later exchange whose sub
    # differs is rejected 403. Nullable + UNIQUE (multiple NULLs are legal in PG
    # and SQLite); additive (C0): pre-migration rows and pure-credentials users
    # simply carry no subject.
    keycloak_sub: Mapped[str | None] = mapped_column(String(64))
