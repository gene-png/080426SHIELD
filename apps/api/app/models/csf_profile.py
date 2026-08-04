"""CSF full-Playbook tiered Working Profile scores (Work Order D4).

One row per (assessment, FIPS tier, subcategory): the five dimension scores plus
in-scope / rationale / narrative / evidence / per-subcategory target. Added
alongside the simplified `CsfAnswer` (which still backs the client
self-assessment); the admin's full-Playbook scoring lives here. The deterministic
math (total/level/evidence-cap/weighted-floor roll-up) is `app/csf/playbook.py`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin


class CsfDimensionScore(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "csf_dimension_scores"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "tier",
            "subcategory_code",
            name="uq_csf_dimension_scores_assessment_tier_subcat",
        ),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("csf_assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tier: Mapped[str] = mapped_column(String(16), nullable=False)  # high/moderate/low
    subcategory_code: Mapped[str] = mapped_column(String(16), nullable=False)

    # Five dimensions, each 0..2.
    governance: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    policy: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    implementation: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    monitoring: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    improvement: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)

    in_scope: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    what_we_found: Mapped[str | None] = mapped_column(Text)
    evidence_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )
    has_evidence: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    target_level: Mapped[int | None] = mapped_column(SmallInteger)

    # Work Order C2: locked rows are untouched by a Run-AI rerun.
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CsfGapAction(UUIDPKMixin, TimestampMixin, Base):
    """POA&M / action-plan annotation for one enterprise gap (Sprint 5 T5).

    One row per (assessment, subcategory): the admin's remediation plan for a
    gap surfaced by the Enterprise roll-up — Characterize (accept/mitigate/
    transfer/avoid), an optional Priority override (the default is code-computed
    by `gap_priority()`), and free-text Action-item fields (owner, deadline,
    resources, success criteria, POA&M reference). Every field is nullable so an
    older assessment parses with zero actions (C0 additive pattern). The scoring
    engine (`app/csf/playbook.py`) is never modified by these annotations — it is
    only read for the default priority.
    """

    __tablename__ = "csf_gap_actions"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "subcategory_code",
            name="uq_csf_gap_actions_assessment_subcat",
        ),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("csf_assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    subcategory_code: Mapped[str] = mapped_column(String(16), nullable=False)

    # Step 10 fields — all nullable (POA&M annotations are optional per gap).
    # characterization: accept/mitigate/transfer/avoid.
    characterization: Mapped[str | None] = mapped_column(String(16))
    # priority_override: P1/P2/P3, overrides the code-computed default.
    priority_override: Mapped[str | None] = mapped_column(String(2))
    owner: Mapped[str | None] = mapped_column(String(255))
    deadline: Mapped[str | None] = mapped_column(String(64))
    resources: Mapped[str | None] = mapped_column(Text)
    success_criteria: Mapped[str | None] = mapped_column(Text)
    poam_ref: Mapped[str | None] = mapped_column(String(255))
