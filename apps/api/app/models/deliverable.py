"""Deliverable - the finalized PDF / XLSX pair for a service.

  deliverables    id, service_id, title, summary, version,
                  pdf_artifact_id, xlsx_artifact_id, finalized_at,
                  finalized_by, superseded_by

Deliverables are generated and versioned by admins. Sprint 5 (D-025)
reintroduced an explicit release-to-client step (Master Spec §12): until a
consultant sets `released_at`, the client sees nothing — no draft, no AI
output, no download. This is a NEW single-role release action, not a revival
of the removed D-005/D-006 reviewer gate (D-023). `version`/`superseded_by`
keep internal history.

Filenames follow Master Spec §15.5: `{Company}_{Service}{MMDDYY}.{ext}`.
The slugifier lives in app.deliverables.filename (Phase 3 stage 8).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin


class Deliverable(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "deliverables"

    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    pdf_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )
    xlsx_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )
    # Word (.docx) deliverable (Work Order C4), alongside PDF + XLSX.
    docx_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )

    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # The PARENT version this deliverable was built from — the assessment or
    # capability-list version, not `version` above, which is the deliverable's
    # own independent counter (W4, migration 0041).
    #
    # Stamped at finalize, which is where the content freezes against a specific
    # parent and where the parent is already required to be APPROVED. Release
    # reads it to flip exactly that row to RELEASED. Without it the only
    # available rule is "latest APPROVED", which flips the wrong row after
    # approve v1 -> finalize -> cut v2 -> approve v2 -> release.
    #
    # Not a ForeignKey: the four parents live in four different tables, so there
    # is no single referent. `(service_id, parent_version)` is unique because
    # every parent table constrains `(service_id, version)`.
    #
    # NULL = finalized before 0041. Release leaves those parents alone and logs
    # it rather than guessing (C0: older rows parse unchanged).
    parent_version: Mapped[int | None] = mapped_column(Integer)

    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deliverables.id", ondelete="SET NULL")
    )

    # Release-to-client (D-025, Master Spec §12): null = unreleased (client sees
    # nothing). Set once by an admin via the release route; SET NULL on the
    # releasing user's deletion so the deliverable outlives them.
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
