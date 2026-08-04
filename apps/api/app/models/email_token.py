"""Single-use email tokens for verification + password reset (Sprint 6 T5, D-028).

Each row is one opaque token issued to a user for a specific ``purpose`` (email
verification or password reset). Only the SHA-256 hash of the token is stored —
the raw token lives only in the email link, so a database read never yields a
usable token. ``used_at`` marks a token spent (single-use); ``expires_at`` bounds
its lifetime. Tokens cascade-delete with the user.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin


class EmailTokenPurpose(enum.StrEnum):
    EMAIL_VERIFY = "email_verify"
    PASSWORD_RESET = "password_reset"  # noqa: S105 - not a credential  # nosec B105


class EmailToken(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "email_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SHA-256 hex digest of the raw token (64 chars). Never the raw token.
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    purpose: Mapped[EmailTokenPurpose] = mapped_column(
        SAEnum(EmailTokenPurpose, name="email_token_purpose", native_enum=False, length=32),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
