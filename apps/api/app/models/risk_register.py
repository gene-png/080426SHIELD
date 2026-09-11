"""Risk Register models (Work Order E).

A point-in-time synthesis deliverable, not a service. Each generate creates a
new versioned RiskRegister with one RiskEntry per finding. SHIELD keeps only
version history; the client owns governance after handoff (so decision-maker,
approval date, expiry, next review, status are NOT modeled here — they print as
blank columns in the export).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin

_JSON_LIST = JSON().with_variant(JSONB, "postgresql")


class RiskRegister(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "risk_registers"

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Newest current; older versions kept (superseded).
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("risk_registers.id", ondelete="SET NULL")
    )

    # What this register was synthesized FROM, captured at generate time (#240).
    #
    # Shape:
    #   {"inputs": [{"kind": "attack"|"csf"|"zt",
    #                "assessment_id": str, "version": int, "status": str}],
    #    "excluded": [str]}
    #
    # Written at GENERATE and never revised, because the guarantee is about what
    # the inputs WERE. Recomputing it at export would read today's statuses, so
    # an assessment approved after generation would certify a register that
    # never saw it -- D-053's snapshot-versus-live lesson, one table over.
    #
    # NULL means NOT RECORDED, not "nothing was excluded". Pre-0047 rows carry
    # it and the export route branches on the distinction rather than assuming
    # either answer: missing data defaults to UNCONFIRMED.
    provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Exported artifacts (XLSX + PDF + Word), set on export.
    xlsx_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )
    pdf_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )
    docx_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )


class RiskEntry(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "risk_entries"

    register_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("risk_registers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    axis: Mapped[str | None] = mapped_column(String(16))  # detection/prevention/response

    # Where this entry came from (traceability — required, no orphan risks).
    source: Mapped[str | None] = mapped_column(
        String(32)
    )  # coverage_finding | questionnaire_response
    source_id: Mapped[str | None] = mapped_column(String(64))

    # Links the AI may only draw from the client's assessments (validated).
    linked_techniques: Mapped[list | None] = mapped_column(_JSON_LIST)
    linked_controls: Mapped[list | None] = mapped_column(_JSON_LIST)

    # What the model proposed for those two fields, and for `source_id`, and
    # LOST (#132, migration 0048). Three states, and the third is the whole
    # reason the column exists:
    #
    #   None  -- pre-0048 row. Not recorded; infer nothing.
    #   {}    -- recorded, and nothing was dropped.
    #   {...} -- `field -> [values]`, deduped, that matched nothing in the
    #            client's own assessments.
    #
    # Without it, `linked_techniques = []` is byte-identical whether the model
    # proposed nothing or proposed five things that all failed to resolve, and
    # the consultant reads the first over the second.
    dropped_links: Mapped[dict | None] = mapped_column(JSON)

    likelihood: Mapped[str | None] = mapped_column(String(16))
    impact: Mapped[str | None] = mapped_column(String(16))
    tier: Mapped[str | None] = mapped_column(String(16))  # code-derived, never AI-set

    compensating_controls: Mapped[str | None] = mapped_column(Text)
    residual_risk: Mapped[str | None] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(String(16))
    rationale: Mapped[str | None] = mapped_column(Text)

    # Provenance (first-class + visible).
    origin: Mapped[str] = mapped_column(String(24), default="ai_generated", nullable=False)
    trust: Mapped[str | None] = mapped_column(String(32))
