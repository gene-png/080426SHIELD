"""Service - the actual engagement workspace once a consultant accepts a
service_request and starts work.

Distinction (Master Spec §11):
  - service_request : "I want this service" - written at intake time.
  - service         : the workspace where the engagement actually runs.
A service_request graduates to a service when an admin opens it; the
service_request's fulfilled_service_id field then points at the new
service row.

Phase 3 only writes `tech_debt` services. Other types (zero_trust_cisa,
zero_trust_dod, nist_csf, attack_coverage) land in their respective
phases; the enum already includes them so no schema change is needed.
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


class ServiceKind(enum.StrEnum):
    """Same values as ServiceType so a request slug maps 1:1 to a service kind."""

    TECH_DEBT = "tech_debt"
    ZERO_TRUST_CISA = "zero_trust_cisa"
    ZERO_TRUST_DOD = "zero_trust_dod"
    NIST_CSF = "nist_csf"
    ATTACK_COVERAGE = "attack_coverage"


class ServiceStatus(enum.StrEnum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    RELEASED = "released"
    ARCHIVED = "archived"


class Service(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "services"

    kind: Mapped[ServiceKind] = mapped_column(
        SAEnum(ServiceKind, name="service_kind", native_enum=False, length=32),
        nullable=False,
    )
    status: Mapped[ServiceStatus] = mapped_column(
        SAEnum(ServiceStatus, name="service_status", native_enum=False, length=32),
        default=ServiceStatus.DRAFT,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # Multi-tenant scope. Every service belongs to exactly one client; routes
    # filter by this to keep one client's workspaces invisible to another.
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # When opened from a service_request, this points back at it so the
    # admin queue can correlate "request" ↔ "live engagement".
    source_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_requests.id", ondelete="SET NULL")
    )

    opened_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
