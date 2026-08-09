"""Zero Trust route schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.service import ServiceKind, ServiceStatus
from app.models.zt_assessment import ZtAssessmentStatus, ZtFramework

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class CatalogCapability(BaseModel):
    code: str
    pillar_code: str
    name: str
    outcome: str


class CatalogPillar(BaseModel):
    code: str
    name: str
    purpose: str
    capabilities: list[CatalogCapability]


class CatalogStage(BaseModel):
    stage: int
    label: str
    description: str


class CatalogResponse(BaseModel):
    framework: ZtFramework
    pillars: list[CatalogPillar]
    stages: list[CatalogStage]
    total_capabilities: int


# ---------------------------------------------------------------------------
# Service + assessment
# ---------------------------------------------------------------------------


class ZtServiceCreateRequest(BaseModel):
    kind: ServiceKind = Field(description="One of zero_trust_cisa | zero_trust_dod.")
    title: str = Field(min_length=1, max_length=255)
    source_request_id: uuid.UUID | None = None


class ZtServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ServiceKind
    status: ServiceStatus
    title: str
    source_request_id: uuid.UUID | None
    opened_by: uuid.UUID
    released_at: datetime | None
    created_at: datetime


class ZtAnswerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assessment_id: uuid.UUID
    capability_code: str
    maturity_stage: int | None
    target_stage: int | None = None
    notes: str | None
    evidence_artifact_id: uuid.UUID | None
    locked: bool = False
    answered_by: uuid.UUID | None
    answered_at: datetime | None


class ZtAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    framework: ZtFramework
    version: int
    status: ZtAssessmentStatus
    approved_at: datetime | None
    approved_by: uuid.UUID | None
    documents_stale: bool = False
    answers: list[ZtAnswerResponse]
    # Target stage the client picked at intake (2-4), or null if not set.
    client_target_stage: int | None = None


class ZtAnswerPatch(BaseModel):
    # Lower bound is 0 to admit the DoD "Pre Zero Trust" baseline; the route
    # gates stage 0 to DoD assessments (CISA stays 1-4).
    maturity_stage: int | None = Field(default=None, ge=0, le=4)
    # Work Order D3: per-capability target stage.
    target_stage: int | None = Field(default=None, ge=1, le=4)
    notes: str | None = Field(default=None, max_length=8000)
    evidence_artifact_id: uuid.UUID | None = None
    # Work Order C2: lock/unlock this row against AI reruns.
    locked: bool | None = None


class ZtSelfAssessmentSubmit(BaseModel):
    """Client submits their self-assessment for admin review.

    `target_stage` lets the client confirm/adjust the maturity goal the gap
    engine measures against; persisted on the source request.
    """

    target_stage: int | None = Field(default=None, ge=1, le=4)


# ---------------------------------------------------------------------------
# Scoring + gap
# ---------------------------------------------------------------------------


class PillarScore(BaseModel):
    pillar_code: str
    pillar_name: str
    capability_count: int
    answered_count: int
    average_stage: float | None
    maturity_pct: float | None = None
    coverage_pct: float
    weakest_capability_codes: list[str]


class ZtScoreSummary(BaseModel):
    assessment_id: uuid.UUID
    version: int
    framework: ZtFramework
    total_capabilities: int
    answered_capabilities: int
    coverage_pct: float
    average_stage: float | None
    maturity_pct: float | None = None
    overall_stage_label: str
    by_pillar: list[PillarScore]


class ZtCapabilityChange(BaseModel):
    """One field the zt_score AI run changed on a capability (Work Order D3/C2)."""

    capability_code: str
    field: str
    old: Any = None
    new: Any = None


class ZtRunAiResponse(BaseModel):
    """Result of a zt_score Run-AI: what changed + the refreshed answers."""

    changed: list[ZtCapabilityChange]
    answers: list[ZtAnswerResponse]
    pillar_narratives: dict[str, str] = {}
    executive_summary: str | None = None
    roadmap_summary: str | None = None
    # How many answers an offline run deliberately left alone (migration 0035).
    # Always 0 for a live run. Surfaced so the skip is visible rather than
    # silent.
    #
    # NOT only client-submitted ones. `protected_keys` protects every answered
    # row whose source is not AI, and `answer_source` is written in exactly two
    # places — `submit_self_assessment` and the AI run. So this also covers a
    # self-assessment still in progress AND any row a consultant typed through
    # `update_answer`, which never writes the field. The name is kept for
    # compatibility; the population is "answers the AI did not write".
    preserved_client_answers: int = 0
    # How many individual stage VALUES the model supplied that could not be
    # parsed or fell outside 1..max_stage, so they were not applied (issue #38).
    # Counted per value, not per suggestion, so `{"current": 9, "target": 3}`
    # reports the one bad value instead of hiding it behind the good one.
    #
    # The limit is stated rather than implied: this counts REJECTED VALUES only.
    # It does NOT count a locked row or a preserved answer — those are separate
    # reasons with their own surfaces, and one number cannot carry them
    # honestly. The per-reason breakdown is W1 (PR #35).
    rejected_stage_values: int = 0
    # Entries in the response that could not be read as a capability at all: a
    # non-object entry, an unusable `code`, or a `capabilities` value that was
    # not a list. Separate from `rejected_stage_values` because the failure is
    # different — there the model named a real capability and gave a bad number,
    # here there is nothing to apply to. Without this, a wholly malformed
    # response renders as a clean zero-change run.
    unusable_suggestions: int = 0


class ZtInterviewQuestion(BaseModel):
    """One verbatim ZT interview prompt (Work Order C8)."""

    external_id: str
    section_name: str
    order_index: int
    stem: str
    cues: list[str]
    # ZT capability/activity hints the prompt informs (catalog-code mapping is
    # imported with the ZT cross-references in the service phase).
    capabilities: list[str]


class ZtQuestionnaireResponse(BaseModel):
    """Framework-specific interview prompts for a ZT service (read-only)."""

    framework_key: str
    framework: ZtFramework
    questions: list[ZtInterviewQuestion]


class GapItem(BaseModel):
    code: str
    pillar_code: str
    pillar_name: str
    name: str
    outcome: str
    current_stage: int
    target_stage: int
    gap_size: int
    priority_score: float
    notes: str | None


class RoadmapEntry(BaseModel):
    """One gap placed in a month of the 12-month roadmap (Work Order D3)."""

    month: int
    code: str
    pillar_code: str
    pillar_name: str
    name: str
    current_stage: int
    target_stage: int
    priority_score: float


class GapAnalysisResponse(BaseModel):
    assessment_id: uuid.UUID
    version: int
    framework: ZtFramework
    target_stage: int
    target_label: str
    total_gap_count: int
    unscored_count: int
    gap_count_by_pillar: dict[str, int]
    gaps: list[GapItem]
    roadmap: list[RoadmapEntry] = []
