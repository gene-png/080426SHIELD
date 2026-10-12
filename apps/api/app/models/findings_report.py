"""Findings report: output A of the design note rev 4, section 5 (migration 0067).

One row per generated client findings report, pinned to the deliverable it
explains. The report regenerates with that deliverable and never on its own
(section 3), so staleness is derived: `deliverable_id` differs from the
service's latest finalized deliverable.

`status` follows the `ai_runs` enum convention (`native_enum=False`, no
`values_callable`), so the STORED value is the member NAME: `DRAFT`, not
`draft`.

Nothing reads or writes this table yet (N4 is schema only); the generation run
(N7) and the admin routes (`routes/reports.py`) come later.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin

_JSON = JSON().with_variant(JSONB, "postgresql")


class FindingsReportStatus(enum.StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


class FindingsReport(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "findings_reports"

    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deliverable_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deliverables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Per `finding_id`: {text, origin ("ai" | "edited"), refused_numbers,
    # accepted_by, accepted_at}. NULL is "not recorded" (the run has not
    # written the code fact lines yet); {} is "no findings".
    sections: Mapped[dict | None] = mapped_column(_JSON)
    # The code-computed cross-service facts used (section 12.5), each with its
    # `integration_run_id`. NULL is "not recorded"; [] is "none used".
    cross_facts: Mapped[list | None] = mapped_column(_JSON)
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="SET NULL")
    )
    status: Mapped[FindingsReportStatus] = mapped_column(
        SAEnum(FindingsReportStatus, name="findings_report_status", native_enum=False, length=16),
        nullable=False,
        default=FindingsReportStatus.DRAFT,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pdf_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )
    docx_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )
