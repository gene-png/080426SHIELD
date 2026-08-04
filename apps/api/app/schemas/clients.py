"""Client-portal read schemas (Sprint 5).

The client-facing view of released deliverables (Master Spec §6.7, §12). Only
released deliverables ever reach these shapes; unreleased work and drafts never
serialize here.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.service import ServiceKind

__all__ = [
    "AttackDashboardResponse",
    "AttackDashboardRollup",
    "AttackDashboardTechnique",
    "AttackTacticCoverage",
    "ClientDeliverableListResponse",
    "ClientDeliverableResponse",
    "RiskDashboardEntry",
    "RiskDashboardResponse",
    "RiskMatrixCell",
    "TechDebtCategorySpend",
    "TechDebtDashboardResponse",
    "TechDebtItem",
    "TechDebtRedundancy",
    "ValueSummaryResponse",
    "ZtDashboardResponse",
    "ZtPillarDashboard",
]


class ClientDeliverableResponse(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    service_kind: ServiceKind
    service_title: str
    title: str
    summary: str | None
    version: int
    released_at: datetime | None
    superseded: bool
    pdf_artifact_id: uuid.UUID | None
    xlsx_artifact_id: uuid.UUID | None
    docx_artifact_id: uuid.UUID | None
    pdf_filename: str | None
    xlsx_filename: str | None
    docx_filename: str | None


class ClientDeliverableListResponse(BaseModel):
    items: list[ClientDeliverableResponse]


class AttackTacticCoverage(BaseModel):
    """Per-tactic coverage counts + weighted % for one MITRE tactic."""

    tactic_id: str
    tactic_name: str
    covered: int
    partial: int
    gap: int
    not_applicable: int
    unscored: int
    coverage_pct: float


class AttackDashboardTechnique(BaseModel):
    """One evaluated technique row for the client coverage matrix. Only techniques
    with a non-null coverage status are serialized (the 'evaluated' set)."""

    code: str
    name: str
    tactic_name: str
    status: str  # CoverageStatus value: covered | partial | gap | not_applicable
    detection_tools: list[str]
    prevention_tools: list[str]
    response_tools: list[str]
    rationale: str | None


class AttackDashboardRollup(BaseModel):
    """Overall coverage rollup for the KPI cards + charts."""

    total_evaluated: int  # covered + partial + gap (addressable set the % uses)
    covered: int
    partial: int
    gap: int
    not_applicable: int
    coverage_pct: float
    by_tactic: list[AttackTacticCoverage]


class AttackDashboardResponse(BaseModel):
    """Release-gated client-facing ATT&CK coverage dashboard payload (D-035).

    A DETERMINISTIC read of the released assessment's coverage — no LLM. Reached
    only when the service has a RELEASED deliverable (the §12 visibility gate),
    so no pre-release number ever leaks.
    """

    service_id: uuid.UUID
    service_title: str
    released_at: datetime
    deliverable_version: int
    rollup: AttackDashboardRollup
    techniques: list[AttackDashboardTechnique]


class ZtPillarDashboard(BaseModel):
    """One CISA/DoD pillar's current-vs-target maturity for the client radar."""

    code: str
    name: str
    capability_count: int
    answered_count: int
    current_pct: float | None
    current_label: str
    target_pct: float | None
    target_label: str
    gap_pct: float  # max(0, target_pct - current_pct)
    weakest: list[str]  # lowest-scored capability NAMES (focus areas)


class ZtDashboardResponse(BaseModel):
    """Release-gated client-facing Zero Trust maturity dashboard payload (D-035).

    Deterministic current-vs-target maturity from the ZT scoring engine — no LLM.
    """

    service_id: uuid.UUID
    service_title: str
    released_at: datetime
    deliverable_version: int
    framework: str  # "cisa_ztmm_2_0" | "dod_ztra"
    framework_label: str
    current_label: str
    current_pct: float | None
    target_label: str
    target_pct: float | None
    largest_gap_pillar: str | None
    largest_gap_pct: float
    pillars: list[ZtPillarDashboard]


class TechDebtItem(BaseModel):
    """One software-portfolio item for the client inventory table."""

    name: str
    vendor: str | None
    category: str | None
    function: str | None
    annual_cost_usd: float | None
    license_count: int | None
    disposition: str | None  # keep | consolidate | cut | None
    notes: str | None


class TechDebtCategorySpend(BaseModel):
    category: str
    total_usd: float
    count: int


class TechDebtRedundancy(BaseModel):
    """A category with more than one tool — the client's overlap clusters."""

    category: str
    count: int
    savings_usd: float  # sum of annual cost of items marked CUT in this category
    items: list[TechDebtItem]


class TechDebtDashboardResponse(BaseModel):
    """Release-gated client-facing software-portfolio dashboard payload (D-035).

    Deterministic spend / sprawl / redundancy / savings from the released
    capability list — no LLM.
    """

    service_id: uuid.UUID
    service_title: str
    released_at: datetime
    deliverable_version: int
    total_applications: int
    annual_spend_usd: float
    identified_savings_usd: float
    savings_cost_known: bool  # False when a CUT item lacked a cost (savings is a floor)
    redundant_category_count: int
    spend_by_category: list[TechDebtCategorySpend]
    sprawl_by_category: list[TechDebtCategorySpend]
    redundancies: list[TechDebtRedundancy]
    items: list[TechDebtItem]


class RiskMatrixCell(BaseModel):
    likelihood: str
    impact: str
    tier: str
    count: int


class RiskDashboardEntry(BaseModel):
    title: str
    axis: str | None
    likelihood: str | None
    impact: str | None
    tier: str | None
    recommended_action: str | None


class RiskDashboardResponse(BaseModel):
    """Release-gated client-facing Risk Register dashboard payload (D-035).

    The synthesized 5x5 register (client-level, not per-service). Visible once the
    register is finalized (exported). Deterministic — the tier is code-derived.
    """

    client_id: uuid.UUID
    released_at: datetime  # register.finalized_at
    version: int
    total_entries: int
    critical_count: int
    high_count: int
    tier_counts: dict[str, int]
    axis_counts: dict[str, int]
    action_counts: dict[str, int]
    matrix: list[RiskMatrixCell]
    entries: list[RiskDashboardEntry]


class ValueSummaryResponse(BaseModel):
    """Cross-service executive value loop (Master Spec §2.5).

    A DETERMINISTIC synthesis of already-computed engine outputs — no LLM, no new
    scoring. Each slot is `None` until the service has a RELEASED deliverable
    (§12 visibility): the card renders "pending" for a null, never a fake number.
    `tech_debt_savings_cost_known` is False when a cut capability lacked a cost,
    so the UI can flag the savings figure as a floor.
    """

    tech_debt_savings_usd: float | None
    tech_debt_savings_cost_known: bool
    zt_gap_count: int | None
    attack_uncovered_count: int | None
    csf_gap_count: int | None
    has_any_data: bool
