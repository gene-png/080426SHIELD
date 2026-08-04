"""ClientDomain - an approved email domain that auto-joins a Client.

Work Order B1: a user who self-registers with an email whose domain matches
an approved `client_domain` row is attached to that client as role `client`.
One client may have several approved domains. Generic providers (gmail.com,
outlook.com, ...) are never valid here — see app.security.email_domains.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin


class ClientDomain(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "client_domain"
    __table_args__ = (UniqueConstraint("domain", name="uq_client_domain_domain"),)

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Stored lowercased; the unique constraint enforces one client per domain.
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
