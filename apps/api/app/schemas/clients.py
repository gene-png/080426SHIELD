"""Client-portal read schemas (Sprint 5).

The client-facing view of released deliverables (Master Spec §6.7, §12). Only
released deliverables ever reach these shapes; unreleased work and drafts never
serialize here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.service import ServiceKind

__all__ = [
    "AttackDashboardResponse",
    "AttackDashboardRollup",
    "AttackDashboardTechnique",
    "AttackTacticCoverage",
    "CsfDashboardResponse",
    "CsfFunctionDashboard",
    "CsfGapDashboard",
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
    # #102. Additive + defaulted (C0). A status whose supporting citation is
    # unconfirmed is withheld from `coverage_pct` -- which narrows its
    # denominator, so this count has to be rendered beside it and never dropped.
    pending_review: int = 0
    coverage_pct: float


class AttackDashboardTechnique(BaseModel):
    """One evaluated technique row for the client coverage matrix. Only techniques
    with a non-null coverage status are serialized (the 'evaluated' set)."""

    code: str
    name: str
    tactic_name: str
    status: str  # CoverageStatus value: covered | partial | gap | not_applicable
    # #102. The rollup beside this array withholds unbacked claims; without this
    # flag the matrix listed those same techniques as `covered`, naming the
    # unconfirmed tool under Detection. One page, two answers.
    #
    # Carried BESIDE `status`, never over it: clearing the citation puts the
    # technique back into whichever status it says, so the status is what the
    # claim is withheld FROM, not something pending replaces.
    pending_review: bool = False
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
    # #102. The CLIENT-facing half of the rule. This route is gated to appear
    # exactly when the released PDF does, so a rollup computed without
    # withholding hands the same client two numbers for one assessment.
    pending_review: int = 0
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
    # Issue 4: False when an ADMIN is previewing a finalized-but-unreleased
    # dashboard. Clients only ever receive True (their gate is unchanged), so
    # the default keeps every existing consumer working.
    released: bool = True
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


class CsfFunctionDashboard(BaseModel):
    """One CSF 2.0 function's current-vs-target maturity for the client view.

    Mirrors `ZtPillarDashboard`. CSF's six functions (Govern, Identify, Protect,
    Detect, Respond, Recover) are the natural analogue of ZT's pillars, and the
    engine already rolls up to exactly that grain (`csf/scoring.py`).
    """

    code: str
    name: str
    subcategory_count: int
    answered_count: int
    coverage_pct: float
    current_tier: float | None
    current_pct: float | None
    # "Unscored" when nothing in this function was answered. Without it the UI
    # can only render an em dash, and an unanswered function is then
    # indistinguishable from a poorly-scored one — while sorting to the TOP of a
    # list ordered by "largest move required", with 0 gaps beside it.
    current_label: str
    target_pct: float | None
    gap_pct: float  # max(0, target_pct - current_pct)
    gap_count: int
    weakest: list[str]  # lowest-scored subcategory CODES (focus areas)


class CsfGapDashboard(BaseModel):
    """One prioritized gap, as the engine ranked it."""

    code: str
    name: str
    function: str
    function_name: str
    current_tier: int
    target_tier: int
    gap_size: int
    priority_score: float


class CsfDashboardResponse(BaseModel):
    """Release-gated client-facing NIST CSF 2.0 dashboard payload.

    Deterministic, from `csf/scoring.py` and `csf/gap.py` — no LLM. Every figure
    is engine-derived; the curated prose in the mockups is deliberately not
    reproduced, matching the other four dashboards.

    TARGET TIER comes from the client's intake choice, not the engine default.
    That is the #73 lesson applied preventively: the ZT exporter shipped for the
    life of the repo computing gaps against a hardcoded 3 while the client had
    chosen 4, so the document listed a different gap set than the consultant
    approved. `target_tier_source` states which one was used, so a reader can
    tell a real choice from a fallback rather than having to guess.
    """

    service_id: uuid.UUID
    service_title: str
    released_at: datetime
    # False when an ADMIN previews a finalized-but-unreleased dashboard; clients
    # only ever receive True. Same contract as the other four (issue 4).
    released: bool = True
    deliverable_version: int

    overall_label: str
    current_tier: float | None
    current_pct: float | None
    coverage_pct: float

    target_tier: int
    target_label: str
    target_pct: float
    # "client" when the tier came from the intake choice, "default" when the
    # client never set one. Never silently conflated — see the docstring.
    target_tier_source: str

    total_gap_count: int
    largest_gap_function: str | None
    largest_gap_pct: float

    functions: list[CsfFunctionDashboard]
    # Ranked, and TRUNCATED. `total_gap_count` above is the real total, and the
    # UI must show it: #75 was filed because the ZT exporter rendered a 20-item
    # slice with the true count nowhere on the page, so a client read 20 of 37
    # remediation items with no statement that anything was omitted. #75 is
    # CLOSED (PR #86, D-049) — the requirement on this field is unchanged, but
    # the reason is a precedent now, not a live defect. An earlier draft said
    # "is open", which sends the next reader to fix something already fixed.
    top_gaps: list[CsfGapDashboard]


class ZtDashboardResponse(BaseModel):
    """Release-gated client-facing Zero Trust maturity dashboard payload (D-035).

    Deterministic current-vs-target maturity from the ZT scoring engine — no LLM.

    TARGET STAGE comes from the client's intake choice, not from the
    per-capability targets alone. That is #124, and it is #79's symptom in the
    surface the client actually looks at: this endpoint used to derive the
    target purely from per-row `target_stage` values, which only Run-AI and the
    client's self-assessment ever write. A consultant-scored assessment leaves
    every one of them NULL, so the target rolled up to None, every pillar's gap
    computed as 0.0, and the client read "Target maturity: Unscored · +0 points
    to target" beside a released PDF from the same assessment saying "37 gap(s)
    at target S4". "+0 points to target" is not a wrong-LOOKING number — it
    reads as good news, which is why this shipped unnoticed.

    `target_stage_source` states which target was used, so a fallback is never
    mistaken for a decision. It carries FOUR values, not the CSF twin's two,
    because `zt/scoring.py::resolve_target_stage` distinguishes "the client
    chose nothing" from "the client's choice could not be used" — and the
    latter is answerable by re-asking them, so flattening the two would throw
    away the more actionable fact. See `targetNote` in `lib/dashboards/zt.ts`,
    which renders all four.
    """

    service_id: uuid.UUID
    service_title: str
    released_at: datetime
    # Issue 4: False when an ADMIN is previewing a finalized-but-unreleased
    # dashboard. Clients only ever receive True (their gate is unchanged), so
    # the default keeps every existing consumer working.
    released: bool = True
    deliverable_version: int
    framework: str  # "cisa_ztmm_2_0" | "dod_ztra"
    framework_label: str
    current_label: str
    current_pct: float | None
    target_label: str
    target_pct: float | None

    # The engagement-level target the gaps were computed against, and where it
    # came from: "client" | "default" | "client_out_of_range" |
    # "client_unparseable". Never silently conflated — see the docstring.
    target_stage: int
    target_stage_source: str

    # How many capabilities the engagement stage above actually decided, i.e.
    # carried no usable per-capability override. ZT differs from CSF here: CSF
    # has no per-function targets, so its tier describes its percentage
    # exactly, while a fully AI-scored ZT assessment can override every
    # capability and leave the engagement stage deciding nothing. Without this,
    # the UI cannot tell whether "your target, chosen at intake" describes the
    # number beside it — which is #124's own defect facing the other way.
    engagement_target_capability_count: int

    # Capabilities whose stored per-capability target could NOT be used, so the
    # engagement stage was applied instead (#188). Sibling of
    # `target_stage_source`, one level down: that field distinguishes "the
    # client chose nothing" from "the client's choice could not be used" for
    # the ENGAGEMENT target, and this is the same distinction per capability.
    #
    # It is here because the deliverable discloses it in `_gap_plan_caption`,
    # and a fact stated in the client's PDF and withheld from the client's
    # SCREEN is a disagreement between two surfaces reading the same
    # assessment. `engagement_target_capability_count` above counts these
    # capabilities as taking the engagement target, which is true and does not
    # say a choice was discarded to get there.
    #
    # Empty on an ordinary engagement. Codes rather than a count, so the UI can
    # name the rows and the count stays derivable.
    unusable_target_codes: list[str] = []

    # The real total: every gap the engine found, not a rendered subset. The ZT
    # dashboard shows no truncated gap list today, and this is in the payload
    # before one is added rather than after — #75 was exactly that omission in
    # the ZT exporter (fixed, PR #86, D-049, and `_gap_plan_caption` now states
    # the true total in all three renderers).
    #
    # NOT guaranteed equal to the released document's count, and an earlier
    # draft of this comment said "matching the deliverable's". Both are
    # computed by the same engine from the same approved answers, so they agree
    # for a given target — but the deliverable is frozen at finalize while this
    # is resolved per request from `ServiceRequest.zt_target_stage`, which
    # `submit_self_assessment` can still write afterwards. Tracked in #209.
    total_gap_count: int

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
    # Issue 4: False when an ADMIN is previewing a finalized-but-unreleased
    # dashboard. Clients only ever receive True (their gate is unchanged), so
    # the default keeps every existing consumer working.
    released: bool = True
    deliverable_version: int
    total_applications: int
    annual_spend_usd: float
    identified_savings_usd: float
    savings_cost_known: bool  # False when a CUT item lacked a cost (savings is a floor)
    # #126. THREE states, not a bool mirroring `savings_cost_known`.
    #
    #   "complete" every source row is accounted for and every item is costed
    #   "partial"  something is known to be missing OR the accounting does not
    #              reconcile - an uncosted item, rows excluded from the upload,
    #              or more items than there were source rows (which floors
    #              `excluded_count` to 0 and would otherwise read "complete")
    #   "unknown"  completeness was never RECORDED for this list
    #
    # A bool cannot carry the third, and the third is not a rounding error: it
    # is the whole population of pre-0036 lists and any list not cut by an AI
    # extraction. Collapsing it into "complete" is what let the exporter print
    # "Total annual cost" over a figure nobody had reconciled; collapsing it
    # into "partial" would claim a defect nobody observed. Same three-answer
    # shape as the ATT&CK citation record, and for the same reason: absence of
    # evidence is not evidence of either outcome.
    spend_completeness: Literal["complete", "partial", "unknown"] = "unknown"
    # The reconciliation the exporter has carried since N-010 and the dashboard
    # never received, so the excluded-rows half of #126 was not merely
    # undisclosed - it was inexpressible. NULL `source_rows_total` means the
    # upload was never reconciled, which is why it is optional rather than 0:
    # zero rows received and no record of how many are different facts.
    source_rows_total: int | None = None
    included_count: int = 0
    excluded_count: int = 0
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
    # Issue 4: False when an ADMIN is previewing a finalized-but-unreleased
    # dashboard. Clients only ever receive True (their gate is unchanged), so
    # the default keeps every existing consumer working.
    released: bool = True
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

    **A null slot carries TWO facts and needs a companion flag to tell them
    apart (#114 review).** `<kind>_unresolved` is True when the client HAS a
    released report of that kind but the deliverable it is labelled with cannot
    be resolved to the assessment behind it. Without the flag that case renders
    as "pending", telling a client who has a released report that they do not —
    and the alternative, refusing the whole response, took the client's home
    page down with it. See `routes/clients.py::_released_parent` for the trade
    and its trigger rates.

    **`has_unresolved` is published rather than derived** so a renderer cannot
    show the card only when `has_any_data` is True: a client with released
    reports and no resolvable figures has False there and True here, which is
    precisely the case that used to disappear silently.

    **A gap count is computed against a TARGET, and the card used to call it
    "your target" unconditionally (#207).** The ZT and CSF figures each sum over
    every released service of their kind, and each summand is counted against a
    target resolved from the client's stored choice -- where that choice was
    usable. Where it was absent, out of range, or unparseable, the engine
    default applied and nothing said so, so a client who had chosen nothing read
    "Capabilities below your target maturity stage" over a stage they had never
    seen.

    `<kind>_targets_defaulted` and `<kind>_targets_unusable` are COUNTS rather
    than a source label, because there is no honest single source for a mixed
    set: one engagement on the client's own stage and another on the default is
    neither. `<kind>_services` is the denominator, without which "2 reports use
    the standard target" does not say whether that is 2 of 2 or 2 of 9.

    The two counts stay APART on `resolve_target_stage`/`resolve_target_tier`'s
    own reasoning: "chose nothing" and "chose something unusable" resolve to the
    same number and are different facts, and only the second is answerable by
    re-asking the client. Both resolvers carry that distinction the whole way;
    collapsing it at the last step would discard the more actionable half.

    **Both counts are `None`, never `0`, when the figure is `None`.** A kind
    goes unresolved wholesale and returns on the first unresolvable service, so
    any tally reached by then describes a prefix of a sum nobody published --
    and a `0` would read as "nothing was assumed" over something unmeasured,
    which is the reassuring direction the rule above forbids.
    """

    tech_debt_savings_usd: float | None
    tech_debt_savings_cost_known: bool
    tech_debt_savings_unresolved: bool
    zt_gap_count: int | None
    zt_gap_unresolved: bool
    zt_services: int
    zt_targets_defaulted: int | None
    zt_targets_unusable: int | None
    attack_uncovered_count: int | None
    attack_uncovered_unresolved: bool
    csf_gap_count: int | None
    csf_gap_unresolved: bool
    csf_services: int
    csf_targets_defaulted: int | None
    csf_targets_unusable: int | None
    has_any_data: bool
    has_unresolved: bool

    # REQUIRED, not `= False`. These shipped with a default for one commit, and
    # the default pointed the reassuring way: a construction site that forgot
    # one would publish "Pending" over a figure that could not be resolved,
    # silently. That is the direction the standing rule forbids -- missing data
    # defaults to UNCONFIRMED, never to confirmed -- and the C0 argument for
    # optional fields does not apply, because these are written by the server
    # rather than parsed from an older one.
