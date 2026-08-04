"""Artifact - any file uploaded into a deployment.

Master Spec §11: artifacts(id, title, file_storage_key, mime_type,
size_bytes, sha256, lineage (jsonb), origin
(client_upload/automated_draft/consultant_approved), stage, uploaded_by,
uploaded_at, archived_at, archived_by, purged_at, purged_by).

Phase 2 only writes `client_upload` rows (the intake document drop). The
other origins ship with their respective phases (automated_draft +
consultant_approved are Phase 3+ AI workflows).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin, utcnow


class ArtifactOrigin(enum.StrEnum):
    CLIENT_UPLOAD = "client_upload"
    AUTOMATED_DRAFT = "automated_draft"
    CONSULTANT_APPROVED = "consultant_approved"


class Artifact(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"

    # Multi-tenant scope. Set at upload time (intake docs use the uploading
    # user's client_id; consultant-generated artifacts use the active client).
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    lineage: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSONB, "postgresql"))
    origin: Mapped[ArtifactOrigin] = mapped_column(
        SAEnum(ArtifactOrigin, name="artifact_origin", native_enum=False, length=32),
        nullable=False,
    )
    stage: Mapped[str | None] = mapped_column(String(64))

    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by: Mapped[uuid.UUID | None] = mapped_column()
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purged_by: Mapped[uuid.UUID | None] = mapped_column()

    notes: Mapped[str | None] = mapped_column(Text)
