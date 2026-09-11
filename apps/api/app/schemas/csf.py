"""NIST CSF 2.0 route schemas (Phase 4 stage 2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.models.csf_assessment import CsfAssessmentStatus
from app.models.service import ServiceKind, ServiceStatus
from app.schemas._numeric import IntNotBool

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class CatalogSubcategory(BaseModel):
    code: str
    function: str
    category: str
    name: str
    outcome: str
    # Minimum impact profile (LOW/MOD/HIGH) at which this outcome applies, so a
    # client questionnaire can filter to their profile.
    min_profile: str = "LOW"


class CatalogCategory(BaseModel):
    code: str
    function: str
    name: str
    purpose: str
    subcategories: list[CatalogSubcategory]


class CatalogFunction(BaseModel):
    code: str
    name: str
    purpose: str
    categories: list[CatalogCategory]


class CatalogTier(BaseModel):
    tier: int
    short_label: str
    description: str


class CatalogResponse(BaseModel):
    """Returned by GET /csf/catalog. Static reference data."""

    functions: list[CatalogFunction]
    tiers: list[CatalogTier]
    total_subcategories: int


# ---------------------------------------------------------------------------
# Interview questionnaire (rich prompts loaded into the `questions` table)
# ---------------------------------------------------------------------------


class InterviewQuestion(BaseModel):
    """One interview prompt extracted from the Kentro Step 1.x .docx files."""

    external_id: str
    section_name: str
    order_index: int
    stem: str
    cues: list[str]
    # CSF 2.0 subcategory ids the prompt informs, so the workspace can show it
    # inline on those subcategory cards.
    csf_subcategories: list[str]


class CsfQuestionnaireResponse(BaseModel):
    """Tier-specific interview prompts for a CSF service.

    Resolved from the service's impact profile (LOW/MOD/HIGH -> tier),
    defaulting to the HIGH questionnaire when no profile is set. Read-only.
    """

    framework_key: str
    profile: str | None = None
    questions: list[InterviewQuestion]


# ---------------------------------------------------------------------------
# Assessment + answers
# ---------------------------------------------------------------------------


class CsfServiceCreateRequest(BaseModel):
    kind: ServiceKind = ServiceKind.NIST_CSF
    title: str = Field(min_length=1, max_length=255)
    source_request_id: uuid.UUID | None = None


class CsfServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ServiceKind
    status: ServiceStatus
    title: str
    source_request_id: uuid.UUID | None
    opened_by: uuid.UUID
    released_at: datetime | None
    created_at: datetime


class CsfAnswerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assessment_id: uuid.UUID
    subcategory_code: str
    maturity_tier: int | None
    notes: str | None
    evidence_artifact_id: uuid.UUID | None
    locked: bool = False
    answered_by: uuid.UUID | None
    answered_at: datetime | None


class CsfAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    version: int
    status: CsfAssessmentStatus
    approved_at: datetime | None
    approved_by: uuid.UUID | None
    documents_stale: bool = False
    answers: list[CsfAnswerResponse]
    # Target tier the client picked at intake (2-4), or null if not set.
    client_target_tier: int | None = None
    # Impact profile the client picked at intake (LOW/MOD/HIGH), or null. Drives
    # which subcategories the client self-assessment shows.
    client_profile: str | None = None


class CsfAnswerPatch(BaseModel):
    """Partial-update body for a single subcategory answer.

    Sending `maturity_tier: null` clears the score (returns it to
    "unscored" for the unanswered-count math).
    """

    maturity_tier: IntNotBool | None = Field(default=None, ge=1, le=4)
    notes: str | None = Field(default=None, max_length=8000)
    evidence_artifact_id: uuid.UUID | None = None
    # Work Order C2: lock/unlock this row against AI reruns (admin only).
    locked: bool | None = None


class CsfSelfAssessmentAnswerPatch(BaseModel):
    """What a CLIENT may change on their own draft answer (#195's CSF twin).

    Not filed as its own issue -- found by applying #195's question to the
    sibling service, which `CLAUDE.md` requires: "a defect found in one service
    exists in its twins until you have checked."

    `patch_self_assessment_answer` took the ADMIN `CsfAnswerPatch` and honoured
    two of its four fields, discarding `evidence_artifact_id` and `locked`
    behind a 200. The `locked` case is the one with teeth, and `CsfAnswerPatch`
    already says so: its comment reads "Work Order C2: lock/unlock this row
    against AI reruns (admin only)". The rule was written down beside the
    field; the route never enforced it, so a client could ask for a lock, be
    told it worked, and have the next AI run overwrite the row.

    ZT had the same shape plus `target_stage` -- see
    `ZtSelfAssessmentAnswerPatch`, which carries the reasoning for refusing
    rather than honouring, and the #188 constraint that decides it. CSF has no
    per-capability target, so this is the same fix with one field fewer.

    `extra="forbid"` makes the refusal set derived: a fifth field on
    `CsfAnswerPatch` cannot quietly start being dropped here.

    And it is a D-016 refusal, which it was not when written -- see the twin in
    `schemas/zt.py` for the reasoning. In short: a schema-level refusal
    surfaces through FastAPI's validation handler, so the caller got Pydantic's
    raw list where every neighbouring refusal returns `{reason, message}`.
    `app/exceptions.py::_handle_validation_error` now synthesises
    `reason` / `reasons` from the error types, so the refusal set stays derived
    and the envelope is typed (#285). Both twins, together, because one of them
    typed and one not is the half-fix that makes an integrator distrust both.
    """

    model_config = ConfigDict(extra="forbid")

    maturity_tier: IntNotBool | None = Field(default=None, ge=1, le=4)
    notes: str | None = Field(default=None, max_length=8000)

    @model_validator(mode="before")
    @classmethod
    def _name_the_fields_this_route_will_not_apply(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        unknown = sorted(set(data) - set(cls.model_fields))
        if unknown:
            # `PydanticCustomError` rather than a bare `ValueError`, so the
            # refusal carries a STABLE CODE rather than Pydantic's generic
            # `value_error` (#285). Measured: this `mode="before"` validator
            # runs ahead of `extra="forbid"`, so it -- not the forbidden-extra
            # rule -- is what a client actually receives, and a reason of
            # `schema_value_error` would be shared with every other custom
            # validator in the API. The code is the thing a client maps to
            # copy; the message is what it shows when it has none.
            raise PydanticCustomError(
                "unapplied_fields",
                f"This endpoint applies only {sorted(cls.model_fields)}. It "
                f"does not apply {unknown}, and returning 200 while dropping "
                f"them would report a change that never happened. Locking a "
                f"row against AI reruns is an admin action, through "
                f"PATCH /csf/answers/{{answer_id}}.",
            )
        return data


class CsfSelfAssessmentSubmit(BaseModel):
    """Client submits their self-assessment for admin review.

    `target_tier` lets the client confirm/adjust the maturity goal the gap
    engine measures against; persisted on the source request.
    """

    target_tier: IntNotBool | None = Field(default=None, ge=1, le=4)


# ---------------------------------------------------------------------------
# Scoring summary
# ---------------------------------------------------------------------------


class FunctionScore(BaseModel):
    function: str
    function_name: str
    subcategory_count: int
    answered_count: int
    average_tier: float | None
    coverage_pct: float  # answered / total * 100
    weakest_subcategory_codes: list[str]


class CsfScoreSummary(BaseModel):
    assessment_id: uuid.UUID
    version: int
    total_subcategories: int
    answered_subcategories: int
    coverage_pct: float
    average_tier: float | None
    overall_maturity_label: str
    by_function: list[FunctionScore]


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------


class GapItem(BaseModel):
    code: str
    function: str
    function_name: str
    category: str
    name: str
    outcome: str
    current_tier: int
    target_tier: int
    gap_size: int
    priority_score: float
    notes: str | None


class GapAnalysisResponse(BaseModel):
    assessment_id: uuid.UUID
    version: int
    target_tier: int
    target_label: str
    total_gap_count: int
    unscored_count: int
    gap_count_by_function: dict[str, int]
    gaps: list[GapItem]


# ---------------------------------------------------------------------------
# Full-Playbook tiered Working Profile (Work Order D4)
# ---------------------------------------------------------------------------


class CsfDimensionScoreResponse(BaseModel):
    id: uuid.UUID
    tier: str
    subcategory_code: str
    governance: int
    policy: int
    implementation: int
    monitoring: int
    improvement: int
    in_scope: bool
    rationale: str | None
    what_we_found: str | None
    has_evidence: bool
    target_level: int | None
    locked: bool
    # Code-computed (app/csf/playbook.py).
    total: int
    level: int
    evidence_capped: bool


class CsfProfileResponse(BaseModel):
    tier: str
    rows: list[CsfDimensionScoreResponse]


class CsfDimensionScorePatch(BaseModel):
    governance: IntNotBool | None = Field(default=None, ge=0, le=2)
    policy: IntNotBool | None = Field(default=None, ge=0, le=2)
    implementation: IntNotBool | None = Field(default=None, ge=0, le=2)
    monitoring: IntNotBool | None = Field(default=None, ge=0, le=2)
    improvement: IntNotBool | None = Field(default=None, ge=0, le=2)
    in_scope: bool | None = None
    rationale: str | None = Field(default=None, max_length=8000)
    what_we_found: str | None = Field(default=None, max_length=8000)
    has_evidence: bool | None = None
    target_level: IntNotBool | None = Field(default=None, ge=1, le=5)
    locked: bool | None = None


class ProfileSeedRequest(BaseModel):
    tiers: list[str] = ["high", "moderate", "low"]


class EnterpriseSubcategory(BaseModel):
    subcategory_code: str
    name: str
    function: str
    tier_levels: dict[str, int]
    enterprise_level: int
    rollup_rule: int
    target_level: int | None
    gap: bool
    priority: str | None


class EnterpriseProfileResponse(BaseModel):
    tiers_in_use: list[str]
    subcategories: list[EnterpriseSubcategory]


class CsfDimensionChange(BaseModel):
    """One field the csf_score AI run changed on a tiered row (Work Order D4/C2)."""

    tier: str
    subcategory_code: str
    field: str
    old: Any = None
    new: Any = None


class CsfDroppedSuggestion(BaseModel):
    """One suggestion the csf_score run did NOT apply, and why (W1, issue #44).

    Itemized rather than counted: a single integer cannot state its own scope,
    so every wording of it is true for the case it was written for and false for
    an adjacent one. Each entry here is self-describing instead.

    `reason` is one of:

    | reason         | meaning                                                  |
    |----------------|----------------------------------------------------------|
    | `entry_shape`  | the entry could not be read as a suggestion at all       |
    | `unknown_key`  | named a row that does not exist (key carried verbatim)   |
    | `unknown_field`| named a FIELD this code does not know — prompt/parser drift|
    | `unparseable`  | the value was not a whole number (`1.9`, `true`, `"n/a"`)|
    | `out_of_range` | the value fell outside the allowed 0-2                   |
    | `wrong_type`   | `what_we_found` came back as something other than a string|
    | `superseded`   | a later entry in the same response overwrote this value  |
    | `locked`       | a human locked the row — a by-design skip, not a defect  |
    | `protected`    | an offline run declined to overwrite a hand-typed score  |

    `locked` renders separately from the rest. Folding a by-design skip into one
    "N dropped" number rebuilds the alert-fatigue problem issue #31 rejected.
    """

    # A closed vocabulary on purpose. As a bare `str` a new reason code invented
    # server-side reaches the workspace as an unmapped label and renders as an
    # empty bullet — the count right, the explanation silently gone. Here it
    # fails loudly at serialization instead.
    reason: Literal[
        "entry_shape",
        "unknown_key",
        "unknown_field",
        "unparseable",
        "out_of_range",
        "wrong_type",
        "superseded",
        "locked",
        "protected",
    ]
    # "tier|subcategory_code" exactly as the model wrote it, or None when the
    # model omitted them. Never the literal "None|None" — that fabricates a row
    # nobody named. AI output: fine here (transient, admin-only, same trust
    # boundary as the run result), never in an audit row (#44 constraint 1).
    key: str | None = None
    # The dimension or narrative field, for drops attributable to one value.
    field: str | None = None
    # How many suggested values this record accounts for. Usually 1, but never
    # assume it: an entry-level drop states the whole row it lost (so a fully
    # rejected row is not undercounted as a single bad field), and ANY key whose
    # value is a container is charged the leaves it hides (so five scores under
    # one name are five, not one). Anything summing these must add `values`,
    # never count records.
    values: int = 1
    # The offending model output, bounded. API response only.
    value: Any = None


class CsfRunAiResponse(BaseModel):
    """Result of a csf_score Run-AI: what changed + the refreshed rows.

    The counts are in units of ONE SUGGESTED VALUE — one field the model asked
    to set on one row — and satisfy, for every response that parsed:

        suggestions_received == suggestions_applied + sum(d.values for d in dropped)

    A sum rather than `len(dropped)` (as issue #44 first wrote it) because
    entry-level drops account for more than one value each. The invariant turns
    "did we count everything?" into a test failure rather than an audit finding.
    """

    changed: list[CsfDimensionChange]
    rows: list[CsfDimensionScoreResponse]
    suggestions_received: int = 0
    suggestions_applied: int = 0
    dropped: list[CsfDroppedSuggestion] = []


class ExportedArtifact(BaseModel):
    kind: str  # xlsx | exec_pdf | exec_docx | full_pdf | full_docx
    label: str
    artifact_id: uuid.UUID
    filename: str


class CsfPlaybookExportResponse(BaseModel):
    """The stored CSF Playbook artifacts — XLSX workbook + executive briefing +
    full playbook, each as a downloadable file (Work Order D4)."""

    artifacts: list[ExportedArtifact]


# ---------------------------------------------------------------------------
# POA&M / gap action plan (Sprint 5 T5, spec step 10)
# ---------------------------------------------------------------------------

# Allowed enumerations, validated in-route so a bad value returns a D-016 typed
# error instead of a raw pydantic validation dump.
GAP_CHARACTERIZATIONS = ("accept", "mitigate", "transfer", "avoid")
GAP_PRIORITY_OVERRIDES = ("P1", "P2", "P3")


class CsfGapActionUpsert(BaseModel):
    """Autosave body for one gap's POA&M annotation. Every field optional; only
    the fields sent are written (partial update / upsert). Send an explicit
    empty string to clear a text field back to unset."""

    characterization: str | None = None
    priority_override: str | None = None
    owner: str | None = Field(default=None, max_length=255)
    deadline: str | None = Field(default=None, max_length=64)
    resources: str | None = Field(default=None, max_length=4000)
    success_criteria: str | None = Field(default=None, max_length=4000)
    poam_ref: str | None = Field(default=None, max_length=255)


class CsfGapActionResponse(BaseModel):
    """One enterprise gap plus its (possibly empty) POA&M annotation."""

    subcategory_code: str
    name: str
    function: str
    enterprise_level: int
    target_level: int | None
    # Code-computed default from gap_priority() via the Enterprise roll-up.
    default_priority: str | None
    characterization: str | None
    priority_override: str | None
    owner: str | None
    deadline: str | None
    resources: str | None
    success_criteria: str | None
    poam_ref: str | None
    # priority_override where set, else default_priority.
    effective_priority: str | None


class CsfGapActionsResponse(BaseModel):
    assessment_id: uuid.UUID
    actions: list[CsfGapActionResponse]
