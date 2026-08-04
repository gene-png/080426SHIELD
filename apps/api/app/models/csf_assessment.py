"""NIST CSF 2.0 assessment models (Phase 4 stage 1).

Master Spec §15.4: CSF 2.0 Assessment service. The 4-tier NIST maturity
model (Partial / Risk Informed / Repeatable / Adaptive) is scored
per-subcategory; the catalog itself is code-only reference data living
in `app.csf.catalog`.

Tables:

  csf_assessments
    one row per Service (`service.kind = nist_csf`); carries assessment-
    level metadata (status, approved_at, approved_by) and a version
    counter so re-runs of the questionnaire produce a new audit row
    rather than mutating prior data.

  csf_answers
    one row per (assessment, subcategory_code). Holds the assessor's
    maturity tier, free-form notes, and an optional `evidence_artifact_id`
    pointer for traceable answers.

Per Master Spec §11.1 `client_id` is denormalized on every business
row so multi-tenant ambitions don't require a schema migration.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin


class CsfAssessmentStatus(enum.StrEnum):
    DRAFT = "draft"
    # Client finished their self-assessment; awaiting admin review. Admins can
    # still edit in this state; clients cannot.
    SUBMITTED = "submitted"
    APPROVED = "approved"
    RELEASED = "released"
    # Admin soft-delete of an unapproved draft (Sprint 9, D-031). No migration:
    # native_enum=False String(16), no CHECK constraint (see migration 0009).
    DISCARDED = "discarded"


class CsfAssessment(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "csf_assessments"
    __table_args__ = (
        UniqueConstraint("service_id", "version", name="uq_csf_assessments_service_version"),
    )

    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Work Order C3: an AI run sets this true; finalize/export clears it.
    documents_stale: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[CsfAssessmentStatus] = mapped_column(
        SAEnum(
            CsfAssessmentStatus,
            name="csf_assessment_status",
            native_enum=False,
            length=16,
        ),
        default=CsfAssessmentStatus.DRAFT,
        nullable=False,
    )

    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class CsfAnswer(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "csf_answers"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "subcategory_code",
            name="uq_csf_answers_assessment_subcategory",
        ),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("csf_assessments.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # NIST subcategory code (e.g. "GV.OC-01"). Plain string, validated at
    # the API edge against app.csf.catalog.all_codes() so a typo in
    # tests or imports doesn't smuggle a bogus row in.
    subcategory_code: Mapped[str] = mapped_column(String(16), nullable=False)

    # 1..4 inclusive (MaturityTier). NULL = unscored.
    maturity_tier: Mapped[int | None] = mapped_column(SmallInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    evidence_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )

    # Work Order C2: a locked row is never changed by a Run-AI rerun.
    locked: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Bookkeeping: who last touched the row.
    answered_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
