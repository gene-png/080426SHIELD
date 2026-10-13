"""CSF full-Playbook tiered Working Profile scores (Work Order D4).

One row per (assessment, FIPS tier, subcategory): the five dimension scores plus
in-scope / rationale / narrative / evidence / per-subcategory target. Added
alongside the simplified `CsfAnswer` (which still backs the client
self-assessment); the admin's full-Playbook scoring lives here. The deterministic
math (total/level/evidence-cap/weighted-floor roll-up) is `app/csf/playbook.py`.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin

#: The deferred group holding `CsfDimensionScore.evidence_basis` (migration
#: 0068); a query that renders it undefers it.
EVIDENCE_BASIS_GROUP = "evidence_basis"


class CsfEvidenceBasis(enum.StrEnum):
    """Where a Working Profile row's evidence comes from (design note rev 4,
    section 5, the Q9 grace; migration 0068). Stored as the member NAME."""

    #: The manual `has_evidence` tick, frozen as it stood before linking: set
    #: by migration 0068 on ticked rows of APPROVED and RELEASED assessments
    #: (Gene's Q9 option A, #736 6126886407). Will be disclosed as "evidence
    #: confirmed before linking existed" once a reader renders it (for #1127);
    #: nothing renders it yet.
    MANUAL_TICK_FROZEN = "manual_tick_frozen"
    #: Confirmed `evidence_links` rows.
    LINKED = "linked"


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

    # Provenance (migration 0042): 'ai' | 'consultant', NULL when unknown.
    #
    # `locked` is a consultant's deliberate "never touch this again"; this is the
    # different fact of who wrote the value, and an offline run keys on it to
    # avoid replacing hand-typed work with canned demo output (#67).
    #
    # NULL means nobody has explicitly written the row, which is the state every
    # seeded profile starts in — deliberately NOT protected, so a fixture run can
    # still populate an empty Playbook. "Has a value" cannot serve here: every
    # dimension is NOT NULL DEFAULT 0, and 0 is a legitimate score.
    answer_source: Mapped[str | None] = mapped_column(String(16))

    # Migration 0068 (Gene's Q9 grace, option A, #736 6126886407). The
    # migration sets `MANUAL_TICK_FROZEN` on rows whose manual tick is on and
    # whose assessment is APPROVED or RELEASED, so released numbers never move
    # under a client. The freeze runs ONCE, at upgrade: an assessment approved
    # or released after 0068 is not frozen by it, and that window is for
    # #1126. Every other row is NULL: a DRAFT (or SUBMITTED) row's
    # tick switches to the EV-1 rule at launch, and an unticked row has no
    # tick to freeze. NOTHING READS IT FOR SCORING YET: `score_tier`'s
    # evidence cap still reads `has_evidence` alone.
    #
    # DEFERRED (group `EVIDENCE_BASIS_GROUP`) and `evaluates_none()`, for
    # `Artifact`'s evidence-intake columns' reason: a select or an ORM insert
    # against a pre-0068 schema must not name it.
    evidence_basis: Mapped[CsfEvidenceBasis | None] = mapped_column(
        SAEnum(
            CsfEvidenceBasis, name="csf_evidence_basis", native_enum=False, length=32
        ).evaluates_none(),
        deferred=True,
        deferred_group=EVIDENCE_BASIS_GROUP,
    )


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
