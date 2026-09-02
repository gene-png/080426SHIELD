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


# ---------------------------------------------------------------------------
# "What feeds this mapping, and what does NOT" — item 7 part 2
#
# Not a second payload view: `POST /ai/preview` already answers "what will be
# sent?", redacted, for all three services. This answers the question nothing
# answers today — **what was NOT sent, and where did what was sent come from?**
#
# `_client_capability_membership` is CORRECT on all three counts (security
# scope, list status, approved-snapshot membership). That is the point: a
# correct filter whose drops are invisible, so a `gap` on a client deliverable
# can mean "no control here" or "the tool was filtered and nobody could see it".
#
# Every list field is defaulted so an older client parses a newer response and
# vice versa (the C0 pattern).
# ---------------------------------------------------------------------------


class AttackAiInputDocument(BaseModel):
    """The client-uploaded file a capability was extracted from."""

    id: uuid.UUID
    title: str  # the sanitised original filename
    uploaded_at: datetime


class AttackAiInputCapability(BaseModel):
    """One capability the model WILL be offered, and where it came from."""

    name: str
    vendor: str | None = None
    category: str | None = None
    security_functions: list[str] = []
    # The model called this row non-security and no consultant has agreed yet.
    # It is still IN scope deliberately — `app/tech_debt/security_scope.py` —
    # and is surfaced so a misclassification can be caught before it becomes a
    # fabricated gap. Computed by `awaiting_security_signoff`, never re-spelled:
    # `security_related=None` must never read as a negative.
    awaiting_signoff: bool = False
    capability_list_id: uuid.UUID | None = None
    source_list_version: int | None = None
    source_document: AttackAiInputDocument | None = None
    # True for a snapshot entry whose live row is gone. It is still sent, under
    # the snapshot's own name (#96: a deletion must not silently narrow a hard
    # allow-list) — but it carries no description, and saying so is the
    # difference between "uncategorised" and "we cannot look".
    live_row_missing: bool = False


class AttackAiInputWithheld(BaseModel):
    """A named capability that exists on a list and is NOT offered to the model.

    `reason` is one of:

    * ``security_scope`` — out of the ATT&CK subset: the model called it
      non-security and a consultant agreed. Used for a DRAFT list's live rows
      and for an APPROVED list's non-snapshot rows alike, because the same tool
      in the same state gets the same reason regardless of list status.
    * ``not_in_approved_snapshot`` — live, in scope, and absent from the
      membership frozen at approval. Deliberately names the observable STATE and
      not a cause: the row was either created after approval or reclassified
      into scope after, and nothing readable at request time separates those.
      Re-approval is the remedy, and it is exactly what clears
      `approved_membership_stale`.
    """

    name: str
    vendor: str | None = None
    reason: str
    capability_list_id: uuid.UUID | None = None
    source_list_version: int | None = None
    source_document: AttackAiInputDocument | None = None


class AttackAiInputExcludedRow(BaseModel):
    """An uploaded SOURCE ROW that produced no capability at all.

    Distinct from `AttackAiInputWithheld` and deliberately not merged with it:
    this row never became a capability, so it has no name to withhold. It is
    the earliest drop in the chain and the only one the ATT&CK service cannot
    re-derive — it is read back from what Tech Debt recorded at extraction.
    """

    capability_list_id: uuid.UUID
    index: int
    summary: str


class AttackAiInputSourceList(BaseModel):
    """A Tech Debt capability list contributing to (or held back from) the map."""

    capability_list_id: uuid.UUID
    tech_debt_service_id: uuid.UUID
    tech_debt_service_title: str
    version: int
    status: str
    # False => a LATER version of the same list exists and this one still
    # counts. Surfaced because it routinely surprises people: every
    # non-discarded version feeds the mapping, not just the newest.
    is_latest_for_service: bool = True
    # True when the APPROVED snapshot decides membership; False when live rows
    # do (a DRAFT, or a list approved before migration 0043 — NULL means nobody
    # recorded it, which is not the same as nothing having been approved).
    membership_from_snapshot: bool = False
    # `approved_membership_stale` — the snapshot no longer matches current
    # security scope, and re-approval is the one audited way to move it.
    # Always False when `membership_from_snapshot` is False, because there is no
    # snapshot to be stale.
    membership_stale: bool = False
    sent_count: int = 0
    not_sent_count: int = 0
    # Rows in the uploaded file, as Tech Debt recorded them at extraction. NULL
    # on a pre-0036 list, which makes no claim at all.
    source_rows_total: int | None = None
    # How much this endpoint may honestly say about rows dropped at extraction:
    #
    # * ``complete`` — named rows are on record, so the reconciliation balanced.
    # * ``unknown``  — nothing is named and the count is not knowable from what
    #   was stored. `Reconciliation.attribution_complete` is NOT persisted, and
    #   the writer records an empty list both when nothing was excluded and when
    #   attribution failed. Those are the same stored bytes, so this endpoint
    #   refuses to report zero — that would be a silent under-report inside the
    #   endpoint built to end silent drops.
    # * ``not_recorded`` — pre-0036 list; no reconciliation was ever stored.
    excluded_attribution: str = "not_recorded"
    # How many rows are NAMED in `excluded`, which is always literally true.
    # Deliberately not called a count of what was excluded: under ``unknown``
    # this is zero and the number excluded is not zero-or-anything-else known.
    excluded_rows_named: int = 0


class AttackAiInputTotals(BaseModel):
    sent: int = 0
    not_sent: int = 0
    awaiting_signoff: int = 0
    withheld_security_scope: int = 0
    withheld_not_in_approved_snapshot: int = 0
    excluded_rows_named: int = 0
    # Contributing lists whose extraction-time exclusions cannot be reported.
    # Rendered beside `excluded_rows_named` for the same reason a withheld count
    # is rendered beside a coverage percentage: a total over an unknowable
    # population is not self-describing.
    lists_with_unknown_exclusions: int = 0
    sent_without_source_document: int = 0


class AttackAiInputsResponse(BaseModel):
    service_id: uuid.UUID
    capabilities: list[AttackAiInputCapability] = []
    not_sent: list[AttackAiInputWithheld] = []
    excluded: list[AttackAiInputExcludedRow] = []
    sources: list[AttackAiInputSourceList] = []
    totals: AttackAiInputTotals = AttackAiInputTotals()
