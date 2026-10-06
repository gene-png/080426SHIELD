"""Tech Debt route schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.models.capability import (
    CapabilityDisposition,
    CapabilityListStatus,
    SecurityFunction,
)
from app.models.service import ServiceKind, ServiceStatus
from app.schemas._numeric import IntNotBool
from app.schemas.ai_runs import AiSource
from app.tech_debt.security_scope import signoff_kind


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
    # #645 / #504: the AI status the consultant acknowledged. `str | None` so a
    # missing or unknown value is refused with the typed `serves_required`
    # 422 (see `app/schemas/ai_runs.py::RunAiRequest`).
    serves: str | None = None


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
    # Set on a component named inside a bundled licence (migration 0037).
    parent_item_id: uuid.UUID | None = None
    # Security classification (migration 0038). `security_related` is tri-state:
    # None means nobody has classified this row, which is NOT the same as False.
    security_related: bool | None = None
    security_functions: list[SecurityFunction] = []
    security_class_confirmed: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def signoff_kind(self) -> Literal["not_in_use", "not_security"] | None:
        """#845: how the sign-off queue words this row (`security_scope`)."""
        return signoff_kind(self)  # type: ignore[return-value]

    @field_validator("security_functions", mode="before")
    @classmethod
    def _functions_default(cls, v: object) -> object:
        """A NULL JSON column reads as no functions, not as a validation error."""
        return v or []


class ExcludedRowResponse(BaseModel):
    """One uploaded row that produced no capability."""

    model_config = ConfigDict(from_attributes=True)

    index: int
    summary: str
    # A consultant has reviewed this exclusion and agrees with it. The row stays
    # listed either way — the reconciliation must remain honest — but the
    # workspace can stop flagging it as needing attention.
    confirmed: bool = False


class IncludeExcludedRowRequest(BaseModel):
    """Pull a wrongly-excluded row back in as a real capability.

    The consultant supplies the values; nothing is inferred from the raw row,
    which is free text the extractor already declined to interpret.
    """

    name: str = Field(min_length=1, max_length=255)
    vendor: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=128)
    function: str | None = Field(default=None, max_length=255)
    annual_cost_usd: float | None = None
    license_count: IntNotBool | None = None
    notes: str | None = None


class CapabilityListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    version: int
    status: CapabilityListStatus
    # Defaulted so the whole response can be built from the ORM row in one
    # `model_validate` call; the route fills it from a separate query.
    items: list[CapabilityItemResponse] = []
    approved_at: datetime | None
    approved_by: uuid.UUID | None
    # True when the approved allow-list snapshot (W3) no longer matches current
    # security scope — a classification was overturned, or components were added
    # to an approved bundle. Those tools CANNOT be cited by the ATT&CK mapping
    # until the list is re-approved, so a technique they cover comes back as a
    # fabricated gap. Surfaced rather than auto-refreshed: silently widening a
    # hard allow-list is the defect #32 records, and silently narrowing it is
    # this one. Re-approval is the deliberate, audited way to change it.
    approved_membership_stale: bool = False
    # #640: False while the list is a draft, and false again after any step-2
    # edit to an approved list until step 3 approves it again. Finalize and
    # release refuse while it is false. Read from the ORM's derived property.
    approval_current: bool
    # #646: which mode drafted this list. Filled by the route from a separate
    # derivation, as `items` is; None only on a response built without it.
    ai_source: AiSource | None = None
    # Reconciliation of the source upload against what was extracted (0036).
    # NULL on lists created before the column existed — the UI renders no claim
    # rather than implying a complete inventory.
    source_rows_total: int | None = None
    excluded_rows: list[ExcludedRowResponse] = []
    # #177: whether the extraction attributed every item to one uploaded row.
    # NULL is "not recorded" (pre-0058, or no extraction), never complete.
    attribution_complete: bool | None = None
    # #833 / #834: what the extraction could not store as given. None is "not
    # recorded" (a list from before 0062); [] is "checked, nothing to record".
    extraction_findings: list[dict] | None = None
    # #177/#193: `reconcile.exclusion_count_state` -- whether the excluded count
    # is exact or only a floor, from the one reader every surface calls.
    exclusion_count_state: Literal["not_recorded", "exact", "unknown"] | None = None
    # #845: rows carrying v3.2's "Security tool not in use:" prefix while also
    # security-related -- the model contradicting itself, kept in ATT&CK scope.
    # Derived by the route from the stored rows, a consultant's override excluded.
    not_in_use_contradictions: int = 0

    @field_validator("excluded_rows", mode="before")
    @classmethod
    def _excluded_default(cls, v: object) -> object:
        """A NULL JSON column means no exclusions recorded, not a bad response."""
        return v or []


class SecurityClassificationOverride(BaseModel):
    """The model called this non-security; a consultant says otherwise."""

    # At least one function: "it is security-related but serves none of prevent,
    # detect or respond" is not a claim the ATT&CK mapping can act on.
    security_functions: list[SecurityFunction] = Field(min_length=1)


class CapabilityComponentInput(BaseModel):
    """One capability a consultant says is included in a bundled licence."""

    name: str = Field(min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=128)
    function: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class CapabilityComponentsRequest(BaseModel):
    """Name what a bundle contains.

    At least one component: an empty request would silently do nothing, and the
    caller would have no way to tell that from success.
    """

    components: list[CapabilityComponentInput] = Field(min_length=1)


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
    license_count: IntNotBool | None = None
    notes: str | None = None
    disposition: CapabilityDisposition | None = None
    disposition_rationale: str | None = Field(default=None, max_length=4000)
    consolidation_target_id: uuid.UUID | None = None
    # Work Order C2: lock/unlock this row against AI reruns.
    locked: bool | None = None


class CapabilityDispositionBulkSet(BaseModel):
    """Set one disposition on many rows of one list (#641).

    `disposition` has NO default: a body that omits it is a 422, never a
    request to return every selected row to undecided. `None` is accepted
    when sent, because the single-row select offers "Undecided" too.
    """

    item_ids: list[uuid.UUID] = Field(max_length=5000)
    disposition: CapabilityDisposition | None


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


class SavingsPreviewRequest(BaseModel):
    """#804: proposed dispositions, `{item_id: "cut" | "consolidate" | "keep" |
    null}`. Rows not named keep their stored disposition.

    Typed `object` on purpose: a malformed map is refused by the route with a
    typed `{reason, message}` 422, the convention the rest of Tech Debt uses,
    rather than by FastAPI's schema handler (CLAUDE.md, the `Query(ge=...)`
    entry)."""

    dispositions: object = None


class SavingsPreviewResponse(BaseModel):
    """What the proposed dispositions would make the savings figure. Computed
    by `tech_debt.savings.estimated_savings`, the deliverable's derivation;
    nothing is written."""

    capability_list_id: uuid.UUID
    estimated_annual_savings: float
    savings_cost_known: bool
    keep_count: int
    consolidate_count: int
    cut_count: int
    undecided_count: int


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
    #: #781: what `total_cost` may honestly be called -- "Total annual cost",
    #: "Included annual cost" or "Annual cost (may not be complete)". The
    #: deliverable's own `cost_label` over the same list, so the admin card and
    #: the released document cannot disagree. Required: a response built
    #: without deciding it must fail, never default to "Total".
    total_cost_label: str
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
