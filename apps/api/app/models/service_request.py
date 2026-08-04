"""Service request - records the four "yes I want this service" picks made
during intake, plus the fifth "I'm not sure" consultation request (D-003
landing CTA → consultation flow).

Master Spec §11:
  service_requests    id, service_type, requested_by, notes, deadline,
                      requested_at, fulfilled_service_id, declined_at,
                      declined_reason

Service types per §15.5 filename convention slugs and §17 Q5 (full ATT&CK
matrix per D-007). The values use snake_case ASCII so they round-trip
through URLs and filenames without escaping.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin, utcnow


class ServiceType(enum.StrEnum):
    """The four locked v1 services + the "I'm not sure" consultation path."""

    TECH_DEBT = "tech_debt"
    ZERO_TRUST_CISA = "zero_trust_cisa"
    ZERO_TRUST_DOD = "zero_trust_dod"
    NIST_CSF = "nist_csf"
    ATTACK_COVERAGE = "attack_coverage"
    CONSULTATION = "consultation"


class CsfProfile(enum.StrEnum):
    """NIST CSF implementation profile the client is targeting.

    Mirrors the FIPS-199 impact bands consultants reason in. Captured at
    intake so the consultant validates rather than guesses the target.
    """

    LOW = "LOW"
    MOD = "MOD"
    HIGH = "HIGH"


class ServiceRequest(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "service_requests"

    service_type: Mapped[ServiceType] = mapped_column(
        SAEnum(ServiceType, name="service_type", native_enum=False, length=32),
        nullable=False,
    )
    # Multi-tenant scope. Set at intake submit; copied onto the Service when
    # an admin opens the engagement.
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    notes: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Client-supplied assessment targets, captured at intake so the consultant
    # validates rather than scores the target from scratch (Master Spec §6.4:
    # "the client should do as much of the work as possible"). Only the columns
    # relevant to the request's service_type are populated:
    #   - nist_csf            -> csf_target_tier (2-4) + csf_profile
    #   - zero_trust_cisa/dod -> zt_target_stage (2-4)
    csf_target_tier: Mapped[int | None] = mapped_column(SmallInteger)
    csf_profile: Mapped[str | None] = mapped_column(String(8))
    zt_target_stage: Mapped[int | None] = mapped_column(SmallInteger)

    # Set when an admin opens a real Service row from this request.
    fulfilled_service_id: Mapped[uuid.UUID | None] = mapped_column()

    # Set when an admin declines the request (e.g. out of scope, duplicate).
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declined_reason: Mapped[str | None] = mapped_column(Text)
