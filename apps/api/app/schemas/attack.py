"""ATT&CK Coverage route schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.attack.coverage import CoverageStatus
from app.models.attack_assessment import AttackAssessmentStatus
from app.models.service import ServiceKind, ServiceStatus

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class CatalogTactic(BaseModel):
    id: str
    shortname: str
    name: str
    description: str


class CatalogTechnique(BaseModel):
    id: str
    name: str
    tactics: list[str]
    parent_id: str | None
    is_sub_technique: bool


class CatalogCoverageDefinition(BaseModel):
    status: CoverageStatus
    short_label: str
    description: str


class CatalogResponse(BaseModel):
    tactics: list[CatalogTactic]
    techniques: list[CatalogTechnique]
    coverage_definitions: list[CatalogCoverageDefinition]
    total_techniques: int  # parent only
    total_sub_techniques: int


# ---------------------------------------------------------------------------
# Service + assessment
# ---------------------------------------------------------------------------


class AttackServiceCreateRequest(BaseModel):
    kind: ServiceKind = ServiceKind.ATTACK_COVERAGE
    title: str = Field(min_length=1, max_length=255)
    source_request_id: uuid.UUID | None = None


class AttackServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ServiceKind
    status: ServiceStatus
    title: str
    source_request_id: uuid.UUID | None
    opened_by: uuid.UUID
    released_at: datetime | None
    created_at: datetime


class AttackCoverageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assessment_id: uuid.UUID
    technique_code: str
    status: CoverageStatus | None
    notes: str | None
    evidence_artifact_id: uuid.UUID | None
    locked: bool = False
    # Work Order D2: tools providing detection / prevention / response.
    detection_tools: list[str] | None = None
    prevention_tools: list[str] | None = None
    response_tools: list[str] | None = None
    rationale: str | None = None
    answered_by: uuid.UUID | None
    answered_at: datetime | None


class AttackAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    version: int
    status: AttackAssessmentStatus
    approved_at: datetime | None
    approved_by: uuid.UUID | None
    documents_stale: bool = False
    coverage: list[AttackCoverageResponse]


class CoverageChange(BaseModel):
    """One field the mitre_map AI run changed on a technique (Work Order D2/C2)."""

    technique_code: str
    field: str
    old: Any = None
    new: Any = None


class AttackRunAiResponse(BaseModel):
    """Result of a mitre_map Run-AI: what changed + the refreshed coverage."""

    tools_available: int
    changed: list[CoverageChange]
    coverage: list[AttackCoverageResponse]
    # mitre_map runs as concurrent batches (one llm_calls row each). Additive +
    # defaulted so older clients and stored payloads parse unchanged (C0).
    # A partial run APPLIES what succeeded rather than discarding it, so the
    # consultant must be told the draft is incomplete and which slice is missing.
    batches_total: int = 0
    batches_failed: int = 0
    # W2 citation accounting. Additive + defaulted (C0). Every usable cited
    # string lands in exactly one of these three, so a reader can check the
    # numbers add up rather than trusting them.
    #
    # `citations_confirmed` matched with no inference — case and whitespace
    # only. `citations_needs_review` was RESOLVED and APPLIED, but the resolver
    # had to change or assume something, and inference is not confirmation.
    # `citations_rejected` had no unique candidate and is gone.
    citations_confirmed: int = 0
    citations_needs_review: int = 0
    citations_rejected: int = 0
    # Verbatim and bounded: "Tenable io" tells a consultant the list holds
    # "Tenable.io". A bare count tells them nothing they can act on.
    citations_rejected_examples: list[str] = Field(default_factory=list)
    citations_needs_review_tools: list[str] = Field(default_factory=list)
    # Keyed by WHY. A vendor guess made against a list with MISSING vendors is
    # not the same risk as a punctuation rescue, and reporting them identically
    # made the nullable-vendor guard inert — it computed a reason nothing read.
    citations_needs_review_by_reason: dict[str, list[str]] = Field(default_factory=dict)
    # Entries that were not usable strings at all (a bare string where a list
    # belongs, a null). Deliberately NOT folded into `rejected`, which means
    # "the model named a tool we could not place" — but counted, because the
    # row's tools are overwritten either way and a silent discard is the defect
    # this whole change exists to end.
    citations_unusable: int = 0


class AttackCoveragePatch(BaseModel):
    status: CoverageStatus | None = None
    notes: str | None = Field(default=None, max_length=8000)
    evidence_artifact_id: uuid.UUID | None = None
    # Work Order C2: lock/unlock this row against AI reruns.
    locked: bool | None = None
    # Work Order D2: D/P/R tool mappings + rationale.
    detection_tools: list[str] | None = None
    prevention_tools: list[str] | None = None
    response_tools: list[str] | None = None
    rationale: str | None = Field(default=None, max_length=8000)


# ---------------------------------------------------------------------------
# Heatmap analytics
# ---------------------------------------------------------------------------


class TacticHeatmapEntry(BaseModel):
    tactic_id: str
    tactic_name: str
    technique_count: int
    sub_technique_count: int
    covered: int
    partial: int
    gap: int
    not_applicable: int
    unscored: int
    coverage_pct: float


class AttackHeatmap(BaseModel):
    assessment_id: uuid.UUID
    version: int
    total_techniques: int
    total_sub_techniques: int
    scored_count: int
    unscored_count: int
    covered: int
    partial: int
    gap: int
    not_applicable: int
    coverage_pct: float
    by_tactic: list[TacticHeatmapEntry]
