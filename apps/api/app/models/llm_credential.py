"""Provider API key stored at runtime (issue 2).

Before this, the only way to give SHIELD a provider key was an environment
variable read once at boot. An admin who noticed AI was offline had no way to
fix it without a redeploy. This table holds the key an admin pastes into the
Management UI so it survives restarts.

The key is stored ENCRYPTED (``app/ai/keystore.py`` owns the ciphering) and is
never returned by any endpoint — the column exists so the provider adapter can
decrypt it at call time, not so anyone can read it back.

One row per provider: ``provider`` is unique, so setting a key twice replaces
it rather than accumulating stale credentials.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin


class LlmCredential(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "llm_credential"
    __table_args__ = (UniqueConstraint("provider", name="uq_llm_credential_provider"),)

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    # Fernet ciphertext, not the key. Sized for the token's base64 expansion.
    encrypted_key: Mapped[str] = mapped_column(String(2048), nullable=False)
    # Who last set it, and when the provider last confirmed it works. Both are
    # metadata for the admin UI and the audit trail — neither reveals the key.
    set_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
