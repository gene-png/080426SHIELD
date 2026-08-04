"""Tech Debt route schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.capability import CapabilityDisposition, CapabilityListStatus
from app.models.service import ServiceKind, ServiceStatus


class ServiceCreateRequest(BaseModel):
    kind: ServiceKind = ServiceKind.TECH_DEBT
    title: str = Field(min_length=1, max_length=255)
    source_request_id: uuid.UUID | None = None


class ServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ServiceKind
    status: ServiceStatus
    title: str
    source_request_id: uuid.UUID | None
    opened_by: uuid.UUID
    released_at: datetime | None
    created_at: datetime


class ExtractRequest(BaseModel):
    artifact_id: uuid.UUID


class CapabilityItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    capability_list_id: uuid.UUID
    name: str
    vendor: str | None
    category: str | None
    function: str | None
    annual_cost_usd: float | None
    license_count: int | None
    notes: str | None
    confidence_pct: int | None
    source_artifact_id: uuid.UUID | None
    disposition: CapabilityDisposition | None
    disposition_rationale: str | None
    consolidation_target_id: uuid.UUID | None
    locked: bool = False


class CapabilityListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    version: int
    status: CapabilityListStatus
    items: list[CapabilityItemResponse]
    approved_at: datetime | None
    approved_by: uuid.UUID | None


class CapabilityItemPatch(BaseModel):
    """Partial-update body for inline edits in the admin table.

    Every field is optional so the editable table can PATCH on every blur
    without re-sending the rest of the row. Sending any field marks the row
    human-curated (clears `confidence_pct`).
    """

    name: str | None = Field(default=None, max_length=255)
    vendor: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=128)
    function: str | None = Field(default=None, max_length=255)
    annual_cost_usd: float | None = None
    license_count: int | None = None
    notes: str | None = None
    disposition: CapabilityDisposition | None = None
    disposition_rationale: str | None = Field(default=None, max_length=4000)
    consolidation_target_id: uuid.UUID | None = None
    # Work Order C2: lock/unlock this row against AI reruns.
    locked: bool | None = None


class ConsolidationPlanSummary(BaseModel):
    capability_list_id: uuid.UUID
    capability_list_version: int
    total_items: int
    keep_count: int
    consolidate_count: int
    cut_count: int
    undecided_count: int
    estimated_annual_savings: float
    savings_cost_known: bool


class OverlapBucketResponse(BaseModel):
    key: str
    item_count: int
    total_cost: float
    cost_known: bool
    item_ids: list[uuid.UUID]
    item_names: list[str]


class TopCostItemResponse(BaseModel):
    id: uuid.UUID
    name: str
    vendor: str | None
    category: str | None
    annual_cost_usd: float


class OverlapAnalysisResponse(BaseModel):
    capability_list_id: uuid.UUID
    capability_list_version: int
    by_category: list[OverlapBucketResponse]
    by_vendor: list[OverlapBucketResponse]
    top_cost_items: list[TopCostItemResponse]
    total_cost: float
    total_items: int
    uncategorized_count: int
    no_vendor_count: int
    no_cost_count: int


class DeliverableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    title: str
    summary: str | None
    version: int
    pdf_artifact_id: uuid.UUID | None
    xlsx_artifact_id: uuid.UUID | None
    docx_artifact_id: uuid.UUID | None = None
    pdf_filename: str | None
    xlsx_filename: str | None
    docx_filename: str | None = None
    finalized_at: datetime | None
    finalized_by: uuid.UUID | None
    superseded_by: uuid.UUID | None
    released_at: datetime | None = None
    released_by: uuid.UUID | None = None
