"""ATT&CK Coverage route schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.attack.coverage import CoverageStatus
from app.attack.pending import is_pending_review
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


class UnconfirmedCitation(BaseModel):
    """One cited tool the resolver had to INFER rather than match (#101).

    Persisted on the coverage row by migration 0044, so the "queued for a human"
    list survives the reload it used to die on.

    `reason` is a `ReviewReason` value but is typed as a plain string on purpose:
    `resolve_citations` has a defensive `"unknown"` branch for a resolution that
    carries no reason, and validating this field against the enum would turn that
    branch from a degraded label into a 500 on READ -- failing loudly at the wrong
    end, long after the run that wrote it.
    """

    #: The capability this citation was APPLIED as, or `None` when it resolved to
    #: nothing at all. A rejected citation applies no tool and must never read as
    #: one, or it would cancel out a real tool in the row's lists.
    tool: str | None = None
    #: What the model actually wrote. `tool` carries what the resolver turned it
    #: into, and the difference is the part a consultant acts on: "Qradar" tells
    #: them the list holds "Splunk Enterprise", where the resolved name tells them
    #: nothing about why the citation was wrong.
    cited: str | None = None
    reason: str
    #: Which of detection_tools / prevention_tools / response_tools it supported.
    #: `None` for a `no_citation` entry, which supported no field because the
    #: model named no tool anywhere on the row.
    field: str | None = None
    #: NULL until a human vouches for the inference. Cleared entries are KEPT
    #: rather than deleted: "a human looked at this and accepted it" is a
    #: different state from "nobody ever cited it", and the difference is exactly
    #: what an auditor asking why a technique counts needs to see.
    cleared_at: datetime | None = None


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
    # #101. Additive + defaulted (C0) so rows written before migration 0044 parse
    # unchanged -- but NULL and `[]` are DIFFERENT answers here and the default is
    # the NULL one: `None` means nobody ever resolved this row's citations, and
    # that scores as pending, not as confirmed.
    unconfirmed_citations: list[UnconfirmedCitation] | None = None

    # A computed field rather than three hand-built assignments. This response is
    # constructed in three places (`_serialize_coverage`, `patch_coverage`, and
    # `run_ai`), and CLAUDE.md's standing lesson is that a defect found in one
    # copy exists in its twins until checked. Deriving it once means there is no
    # second copy to forget.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def pending_review(self) -> bool:
        """True when this row's status makes a claim its evidence does not back.

        #102 / 5.1. Derived, never stored: clearing a flag has to move the
        technique back into whichever of covered/partial/gap its stored status
        says, so the status must survive underneath.
        """
        citations = (
            None
            if self.unconfirmed_citations is None
            else [c.model_dump() for c in self.unconfirmed_citations]
        )
        return is_pending_review(
            self.status.value if self.status is not None else None,
            citations,
            [
                *(self.detection_tools or []),
                *(self.prevention_tools or []),
                *(self.response_tools or []),
            ],
        )


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
    # #102. How many rows this run left making a claim their evidence does not
    # back -- inferred-and-uncleared citations, plus the rows whose every
    # citation was rejected and now hold a status over an empty tool list.
    # Reported because `citations_needs_review` counts CITATIONS and the
    # consultant acts on TECHNIQUES; one flagged tool cited by forty techniques
    # is one number and forty pieces of work.
    pending_review_rows: int = 0


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
    # #102. Per-tactic as well as overall: the heatmap is where a consultant
    # actually reads coverage, and a number that is honest only in the total is
    # not honest where it is read.
    pending_review: int = 0
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
    # #102. `coverage_pct` is a ratio over what can currently be CLAIMED, so
    # withholding rows narrows its denominator and the percentage alone is not
    # self-describing -- see
    # `test_narrowing_the_denominator_can_raise_the_ratio_and_that_is_stated`.
    # This count must be rendered beside it. A bare 100% over a withheld row is
    # the false assurance the whole rule exists to prevent.
    pending_review: int = 0
    coverage_pct: float
    by_tactic: list[TacticHeatmapEntry]
