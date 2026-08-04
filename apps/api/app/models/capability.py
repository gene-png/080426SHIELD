"""Capability list + items - the Tech Debt service's editable inventory.

Master Spec §11:
  capability_list     id, service_id, version, status (draft/approved/
                      released), approved_at, approved_by, items
                      (separate table)
  capability_items    id, capability_list_id, name, vendor, category,
                      function, annual_cost_usd, license_count, notes,
                      confidence_pct (AI flag), source_artifact_id

Phase 3 stage 7 adds the consolidation-plan verdict columns:
  disposition (keep/consolidate/cut), disposition_rationale,
  consolidation_target_id (self-FK).

AI Prompt §6.2 / §6.4: the extraction surface is an editable table, NOT
a JSON textarea. confidence_pct is what the renderer reads to dim
low-confidence rows (or surface them as "review me" badges).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
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


class CapabilityListStatus(enum.StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    RELEASED = "released"
    # Admin soft-delete of an unapproved draft (Sprint 9, D-031). Stored in the
    # existing native_enum=False String(16) column - no migration (see 0009).
    DISCARDED = "discarded"


class CapabilityDisposition(enum.StrEnum):
    """Consolidation-plan verdict for each capability (Phase 3 stage 7)."""

    KEEP = "keep"
    CONSOLIDATE = "consolidate"
    CUT = "cut"


class CapabilityList(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "capability_lists"
    __table_args__ = (
        UniqueConstraint("service_id", "version", name="uq_capability_lists_service_id_version"),
    )

    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[CapabilityListStatus] = mapped_column(
        SAEnum(CapabilityListStatus, name="capability_list_status", native_enum=False, length=16),
        default=CapabilityListStatus.DRAFT,
        nullable=False,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class CapabilityItem(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "capability_items"

    capability_list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("capability_lists.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(128))
    function: Mapped[str | None] = mapped_column(String(255))

    annual_cost_usd: Mapped[float | None] = mapped_column(Numeric(14, 2))
    license_count: Mapped[int | None] = mapped_column(Integer)

    notes: Mapped[str | None] = mapped_column(Text)

    # 0-100. Set by the AI extractor; an admin edit clears it (the row is
    # now human-curated, no longer a low-confidence guess).
    confidence_pct: Mapped[int | None] = mapped_column(Integer)

    # Work Order C2: a locked row is never changed by a Run-AI rerun.
    locked: Mapped[bool] = mapped_column(default=False, nullable=False)
    source_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )

    # Consolidation-plan verdict (Phase 3 stage 7). None = undecided.
    disposition: Mapped[CapabilityDisposition | None] = mapped_column(
        SAEnum(
            CapabilityDisposition,
            name="capability_disposition",
            native_enum=False,
            length=16,
        )
    )
    disposition_rationale: Mapped[str | None] = mapped_column(Text)
    # When disposition=consolidate, optionally points at the item we'd
    # consolidate INTO. ondelete=SET NULL so deleting the target doesn't
    # nuke the dependent row's disposition.
    consolidation_target_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("capability_items.id", ondelete="SET NULL")
    )
