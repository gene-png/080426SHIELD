"""One-time MFA recovery codes (Sprint 6 T4, D-027).

Each row is a single Argon2-hashed recovery code (never the plaintext — the
plaintext is shown to the user exactly once at enrollment). ``used_at`` marks a
code as spent so it cannot be replayed. Codes are issued as a set at MFA verify
time and cascade-deleted with the user.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin


class UserRecoveryCode(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "user_recovery_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
