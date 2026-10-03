"""Request and response bodies for the ATT&CK what-if (#802 slice A)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ScenarioCreateRequest(BaseModel):
    """`removed` is the tools to take away, by the names the base assessment
    cites. Typed loosely on purpose: an empty or missing list is refused by the
    route with a typed `{reason, message}` 422, never FastAPI's schema 422."""

    removed: list[str] | None = None
    #: Slice B: tools the client doesn't have, each `{name, vendor, category,
    #: security_functions}`. Typed loosely for the same reason: every refusal
    #: is a typed 422 from `scenario.validate_added`.
    added: list[Any] | None = None


class ScenarioAddedTool(BaseModel):
    """A tool the admin added to the what-if (slice B)."""

    name: str
    vendor: str | None
    category: str | None
    security_functions: list[str]


class ScenarioRollup(BaseModel):
    """One side of the comparison: the client dashboard's own figures."""

    coverage_pct: float
    covered: int
    partial: int
    gap: int
    not_applicable: int
    #: Withheld from the percentage, rendered beside it (#102).
    pending_review: int
    scored_count: int
    catalogue_count: int
    #: Q4 (R3): techniques scored as if tools awaiting review were not in
    #: place, and the approved sentence stating it beside the percentage (None
    #: at zero), as `computed.awaiting_review_sentence` words it.
    awaiting_review: int
    awaiting_review_text: str | None
    #: #621's two counts outside the assessed denominator, stated beside the
    #: percentage. None for a base approved before #620's rules, which never
    #: stated them (`exporters.states_outside_counts`).
    unable_to_determine: int | None
    outside_control_surface: int | None


class ScenarioDifference(BaseModel):
    """A technique whose computed status moves under the change."""

    technique_code: str
    today: str | None
    after: str | None
    #: True when `after` ranks above `today` and no tool the admin ADDED was
    #: credited here: the AI credited a remaining tool the last confirmed
    #: assessment did not. Counted in `scored_higher` (copy 18).
    scored_higher: bool
    #: Slice B: the AI credited a tool the admin added here (B12).
    credited_tool_you_added: bool
    #: The AI credited a tool added to the client's list after the base was
    #: approved (the advisor's (b2)).
    credited_added_tool: bool


class ScenarioTechnique(BaseModel):
    """An affected technique's lists under the scenario, and the accepted AI
    rows behind them."""

    technique_code: str
    detection_tools: list[str]
    prevention_tools: list[str]
    response_tools: list[str]
    ai_rows: list[dict[str, Any]]
    #: The tools added since the base that the AI credited here (b2).
    credited_added_tools: list[str]
    #: Slice B: the tools the admin added that the AI credited here.
    credited_tools_you_added: list[str]


class ScenarioSummary(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    state: str
    removed: list[str]
    #: Slice B: the names of the tools the admin added.
    added: list[str]
    affected_count: int
    base_assessment_id: uuid.UUID
    base_version: int
    created_at: datetime


class ScenarioBase(BaseModel):
    """The assessment a new what-if would compare with, and the tools it
    cites: the only names a removal may pick."""

    assessment_id: uuid.UUID
    version: int
    approved_at: datetime | None
    tools: list[str]


class ScenarioListResponse(BaseModel):
    #: None when there is no confirmed assessment to compare with.
    base: ScenarioBase | None
    scenarios: list[ScenarioSummary]


class ScenarioRunError(BaseModel):
    reason: str | None
    message: str | None


class ScenarioResponse(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    state: str
    removed: list[str]
    #: Slice B: the tools the admin added.
    added: list[ScenarioAddedTool]
    affected_codes: list[str]
    #: Of `affected_codes`: those a removed tool appears on (copy 6), and those
    #: only an added tool could change (B9). They sum to the whole.
    affected_by_removal: int
    affected_by_addition_only: int
    base_assessment_id: uuid.UUID
    base_version: int
    base_catalog_version: str | None
    base_approved_at: datetime | None
    #: A newer assessment is now the confirmed base. Shown, never re-based.
    stale: bool
    #: True when the run route would refuse with 503 (no prompt text yet).
    analysis_available: bool
    ai_run_id: uuid.UUID | None
    #: The run's status (`running`, `completed`, `failed`), None before a run.
    run_status: str | None
    #: Why the run failed, as the run records it (`{reason, message}`); None
    #: unless `run_status` is `failed`. A failed what-if can be run again.
    run_error: ScenarioRunError | None
    today: ScenarioRollup
    #: None until a run has completed.
    after: ScenarioRollup | None
    differences: list[ScenarioDifference]
    techniques: list[ScenarioTechnique]
    #: Counted contract drops by reason; None before a run.
    dropped: dict[str, int] | None
    #: Affected techniques no batch re-assessed: they take the removal alone.
    not_reassessed: list[str] | None
    #: How many affected techniques would score HIGHER than today because the
    #: AI credited a REMAINING tool (copy 18); None before a run.
    scored_higher: int | None
    #: Slice B: how many would score higher with a tool the admin added (B11).
    #: Derived from the stored rows; None before a run.
    higher_with_added: int | None
    #: How many offered tools were added to the client's list after the base
    #: was approved (b2). None before a run AND when it could not be checked:
    #: never 0 for "unknown". A client reads "could not be checked" only beside
    #: a result (`after`).
    tools_added_since_base: int | None
    created_at: datetime
