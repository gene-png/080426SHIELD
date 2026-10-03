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
    #: True when `after` ranks above `today`: the AI credited a remaining tool
    #: the last confirmed assessment did not. Counted in `scored_higher`.
    scored_higher: bool


class ScenarioTechnique(BaseModel):
    """An affected technique's lists under the scenario, and the accepted AI
    rows behind them."""

    technique_code: str
    detection_tools: list[str]
    prevention_tools: list[str]
    response_tools: list[str]
    ai_rows: list[dict[str, Any]]


class ScenarioSummary(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    state: str
    removed: list[str]
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


class ScenarioResponse(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    state: str
    removed: list[str]
    affected_codes: list[str]
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
    today: ScenarioRollup
    #: None until a run has completed.
    after: ScenarioRollup | None
    differences: list[ScenarioDifference]
    techniques: list[ScenarioTechnique]
    #: Counted contract drops by reason; None before a run.
    dropped: dict[str, int] | None
    #: Affected techniques no batch re-assessed: they take the removal alone.
    not_reassessed: list[str] | None
    #: How many affected techniques would score HIGHER than today; None before
    #: a run.
    scored_higher: int | None
    created_at: datetime
