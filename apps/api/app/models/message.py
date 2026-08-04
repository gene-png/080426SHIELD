"""Message - a per-service thread entry between admins and the client.

Work Order C7: after submitting, the client sees status + a message thread.
Admins can message the client (e.g. a request for a missing document) and the
client replies. Tenant-scoped: every row carries `client_id` and belongs to one
`service_id`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin


class Message(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Stamped when the counterparty reads the thread (coarse per-message flag).
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
