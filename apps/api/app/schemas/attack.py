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


# ---------------------------------------------------------------------------
# "What feeds this mapping" (2026-08-08)
#
# The workspace reported only a count — `23 tools available` — and only AFTER
# the run. An admin could not answer "what is being reviewed, and where did it
# come from?", which is how a run with ZERO capabilities produced 607 fabricated
# gaps that read like a real assessment (N-033).
#
# Every list field is defaulted so an older client parses a newer response and
# vice versa (the C0 pattern).
# ---------------------------------------------------------------------------


class AttackAiInputDocument(BaseModel):
    """A client-uploaded file that at least one contributing capability came from."""

    id: uuid.UUID
    title: str  # the sanitised original filename
    mime_type: str
    size_bytes: int
    uploaded_at: datetime
    item_count: int = 0


class AttackAiInputList(BaseModel):
    """A capability list contributing tools to this mapping."""

    capability_list_id: uuid.UUID
    tech_debt_service_id: uuid.UUID
    tech_debt_service_title: str
    version: int
    status: str
    # False => a LATER version of the same list exists and this one still
    # counts. Surfaced because it routinely surprises people: every
    # non-discarded version feeds the mapping, not just the newest.
    is_latest_for_service: bool = True
    item_count: int = 0


class AttackAiInputItem(BaseModel):
    """One capability being offered to the model."""

    name: str
    vendor: str | None = None
    category: str | None = None
    security_functions: list[str] = []
    # The model's non-security call that nobody has agreed with yet. Still in
    # scope deliberately (see tech_debt/security_scope.py) — shown so a
    # consultant can spot a misclassification before it becomes a false gap.
    awaiting_signoff: bool = False
    source_document_id: uuid.UUID | None = None
    capability_list_id: uuid.UUID
    list_label: str
    list_is_superseded: bool = False


class AttackAiInputsResponse(BaseModel):
    service_id: uuid.UUID
    # Equal to run-ai's `tools_available`, by construction: both count the
    # distinct names in `AttackAiRequest.tools`.
    tools_sent: int
    items_in_scope: int = 0
    duplicate_names: int = 0
    awaiting_signoff_count: int = 0
    items_without_source_document: int = 0
    documents: list[AttackAiInputDocument] = []
    lists: list[AttackAiInputList] = []
    items: list[AttackAiInputItem] = []
