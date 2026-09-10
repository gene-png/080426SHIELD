"""Zero Trust route schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.service import ServiceKind, ServiceStatus
from app.models.zt_assessment import ZtAssessmentStatus, ZtFramework
from app.schemas._numeric import IntNotBool

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class CatalogCapability(BaseModel):
    code: str
    pillar_code: str
    name: str
    outcome: str


class CatalogPillar(BaseModel):
    code: str
    name: str
    purpose: str
    capabilities: list[CatalogCapability]


class CatalogStage(BaseModel):
    stage: int
    label: str
    description: str


class CatalogResponse(BaseModel):
    framework: ZtFramework
    pillars: list[CatalogPillar]
    stages: list[CatalogStage]
    total_capabilities: int


# ---------------------------------------------------------------------------
# Service + assessment
# ---------------------------------------------------------------------------


class ZtServiceCreateRequest(BaseModel):
    kind: ServiceKind = Field(description="One of zero_trust_cisa | zero_trust_dod.")
    title: str = Field(min_length=1, max_length=255)
    source_request_id: uuid.UUID | None = None


class ZtServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ServiceKind
    status: ServiceStatus
    title: str
    source_request_id: uuid.UUID | None
    opened_by: uuid.UUID
    released_at: datetime | None
    created_at: datetime


class ZtAnswerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assessment_id: uuid.UUID
    capability_code: str
    maturity_stage: int | None
    target_stage: int | None = None
    notes: str | None
    evidence_artifact_id: uuid.UUID | None
    locked: bool = False
    answered_by: uuid.UUID | None
    answered_at: datetime | None


class ZtAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    framework: ZtFramework
    version: int
    status: ZtAssessmentStatus
    approved_at: datetime | None
    approved_by: uuid.UUID | None
    documents_stale: bool = False
    answers: list[ZtAnswerResponse]
    # Target stage the client picked at intake (2-4), or null if not set.
    client_target_stage: int | None = None


class ZtAnswerPatch(BaseModel):
    # Lower bound is 0 to admit the DoD "Pre Zero Trust" baseline; the route
    # gates stage 0 to DoD assessments (CISA stays 1-4).
    maturity_stage: IntNotBool | None = Field(default=None, ge=0, le=4)
    # Work Order D3: per-capability target stage.
    target_stage: IntNotBool | None = Field(default=None, ge=1, le=4)
    notes: str | None = Field(default=None, max_length=8000)
    evidence_artifact_id: uuid.UUID | None = None
    # Work Order C2: lock/unlock this row against AI reruns.
    locked: bool | None = None


class ZtSelfAssessmentAnswerPatch(BaseModel):
    """What a CLIENT may change on their own draft answer (#195).

    Deliberately not `ZtAnswerPatch`. That schema is the ADMIN one, and
    `patch_self_assessment_answer` honoured only two of its five fields --
    writing `maturity_stage` and `notes`, discarding the rest behind a 200.
    #195 reports `target_stage`; the other two came out of listing what the
    handler actually reads:

        evidence_artifact_id -- a client attaches evidence, gets 200, and no
            evidence is attached.
        locked -- a client locks a row against AI reruns, gets 200, and the
            row is not locked.

    Core principle 2 forbids exactly this: "never a lie that something
    succeeded."

    ## Refused rather than honoured, and #188 is the reason

    #195 leaves the choice open -- honour `target_stage` here, or refuse it.
    Honouring would make this a THIRD writer of `ZtAnswer.target_stage`, and
    `zt/scoring.py::capability_target_override` carries a deliberate exemption
    whose stated expiry condition is "if a third writer appears, this exemption
    expires with it". Honouring would therefore activate a latent
    silent-fallback defect (#188) as a side effect of fixing a reporting one.
    Refusing holds the writer count at two and leaves that exemption intact.

    The per-capability target keeps its working writer in `patch_answer`, the
    admin route where setting it belongs.

    ## The refusal set is derived, not listed

    `extra="forbid"` means this class states what it ACCEPTS and everything
    else is refused by construction -- so a sixth field added to
    `ZtAnswerPatch` tomorrow cannot quietly start being dropped here. A
    hand-written deny list would have to be remembered; this cannot go stale.

    The validator sits alongside it only to name the CAUSE. Pydantic's own
    message for a forbidden extra is "Extra inputs are not permitted", which
    tells an integrator that a check failed but not why this route declines
    the field. Both derive from `model_fields`, so the two cannot disagree.
    """

    model_config = ConfigDict(extra="forbid")

    maturity_stage: IntNotBool | None = Field(default=None, ge=0, le=4)
    notes: str | None = Field(default=None, max_length=8000)

    @model_validator(mode="before")
    @classmethod
    def _name_the_fields_this_route_will_not_apply(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        unknown = sorted(set(data) - set(cls.model_fields))
        if unknown:
            raise ValueError(
                f"This endpoint applies only {sorted(cls.model_fields)}. It "
                f"does not apply {unknown}, and returning 200 while dropping "
                f"them would report a change that never happened. A "
                f"per-capability target_stage is set through the admin route "
                f"PATCH /zt/answers/{{answer_id}}."
            )
        return data


class ZtSelfAssessmentSubmit(BaseModel):
    """Client submits their self-assessment for admin review.

    `target_stage` lets the client confirm/adjust the maturity goal the gap
    engine measures against; persisted on the source request.
    """

    target_stage: IntNotBool | None = Field(default=None, ge=1, le=4)


# ---------------------------------------------------------------------------
# Scoring + gap
# ---------------------------------------------------------------------------


class PillarScore(BaseModel):
    pillar_code: str
    pillar_name: str
    capability_count: int
    answered_count: int
    average_stage: float | None
    maturity_pct: float | None = None
    coverage_pct: float
    weakest_capability_codes: list[str]


class ZtScoreSummary(BaseModel):
    assessment_id: uuid.UUID
    version: int
    framework: ZtFramework
    total_capabilities: int
    answered_capabilities: int
    coverage_pct: float
    average_stage: float | None
    maturity_pct: float | None = None
    overall_stage_label: str
    by_pillar: list[PillarScore]


class ZtCapabilityChange(BaseModel):
    """One field the zt_score AI run changed on a capability (Work Order D3/C2)."""

    capability_code: str
    field: str
    old: Any = None
    new: Any = None


class ZtDroppedSuggestion(BaseModel):
    """One suggestion the zt_score run did NOT apply, and why (W1, issue #44).

    Itemized rather than counted: a single integer cannot state its own scope,
    so every wording of it is true for the case it was written for and false for
    an adjacent one. Each entry here is self-describing instead.

    `reason` is one of:

    | reason         | meaning                                                  |
    |----------------|----------------------------------------------------------|
    | `entry_shape`  | the entry could not be read as a suggestion at all       |
    | `unknown_key`  | named a capability that does not exist (key verbatim)    |
    | `unknown_field`| named a FIELD this code does not know — prompt/parser drift|
    | `unparseable`  | the value was not a whole number (`1.9`, `true`, `"n/a"`)|
    | `out_of_range` | the value fell outside the framework's stage ladder      |
    | `superseded`   | a later entry in the same response overwrote this value  |
    | `locked`       | a human locked the row — a by-design skip, not a defect  |
    | `protected`    | an offline run declined to overwrite a non-AI answer     |

    `locked` and `protected` render separately from the rest. Both are by-design
    skips; folding them into one "N dropped" number rebuilds the alert-fatigue
    problem issue #31 rejected.

    ZT has no `wrong_type`: CSF needed it for a narrative field, and ZT's
    narrative fields were removed (#64). Every value ZT applies is a stage.
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
        "superseded",
        "locked",
        "protected",
    ]
    # The capability code as the model wrote it (escaped and bounded), or None
    # when the model omitted it — never the literal "None", which fabricates a
    # row nobody named.
    #
    # AI output, carried here deliberately: transient, admin-only, and the one
    # channel #44 sanctions for it. NOT the same trust boundary as the run
    # result, which is what this comment used to claim. A CLIENT-role user's
    # `notes` reach the model verbatim through `build_zt_ai_request`, so a
    # lower-privileged tenant user seeds the input whose output lands here and
    # renders on a consultant's screen. Bounded and escaped, no privilege
    # gained — but it is a trust boundary crossing and is tracked as #68.
    # Never in an audit row or a log (#44 constraint 1).
    key: str | None = None
    # "current" or "target", for drops attributable to one value.
    field: str | None = None
    # How many suggested values this record accounts for. Usually 1, but never
    # assume it: an entry-level drop states the whole row it lost (so a fully
    # rejected entry is not undercounted as a single bad field), and ANY key
    # whose value is a container is charged the leaves it hides. Anything
    # summing these must add `values`, never count records.
    values: int = 1
    # The offending model output, bounded. AI output — response only.
    value: Any = None


class ZtRunAiResponse(BaseModel):
    """Result of a zt_score Run-AI: what changed + the refreshed answers.

    `pillar_narratives`, `executive_summary` and `roadmap_summary` were removed
    in W1's ZT step (issue #64): all three were returned and none was ever
    persisted, exported or rendered. They are not deprecated fields left empty —
    a dead field implying a live one is its own defect (see #62) — they are
    gone, along with the prompt text that asked for them.
    """

    changed: list[ZtCapabilityChange]
    answers: list[ZtAnswerResponse]
    # Every suggested value the run received is either applied or itemized:
    #     received == applied + sum(d.values for d in dropped)
    # Counted in VALUES (one field on one capability), not entries — D-045.
    suggestions_received: int = 0
    suggestions_applied: int = 0
    dropped: list[ZtDroppedSuggestion] = []
    # How many answers an offline run deliberately left alone (migration 0035).
    # Always 0 for a live run. Surfaced so the skip is visible rather than
    # silent.
    #
    # NOT only client-submitted ones. `protected_keys` protects every answered
    # row whose source is not AI, and `answer_source` is written in exactly two
    # places — `submit_self_assessment` and the AI run. So this also covers a
    # self-assessment still in progress AND any row a consultant typed through
    # `update_answer`, which never writes the field. The name is kept for
    # compatibility; the population is "answers the AI did not write".
    preserved_client_answers: int = 0


class ZtInterviewQuestion(BaseModel):
    """One verbatim ZT interview prompt (Work Order C8)."""

    external_id: str
    section_name: str
    order_index: int
    stem: str
    cues: list[str]
    # ZT capability/activity hints the prompt informs (catalog-code mapping is
    # imported with the ZT cross-references in the service phase).
    capabilities: list[str]


class ZtQuestionnaireResponse(BaseModel):
    """Framework-specific interview prompts for a ZT service (read-only)."""

    framework_key: str
    framework: ZtFramework
    questions: list[ZtInterviewQuestion]


class GapItem(BaseModel):
    code: str
    pillar_code: str
    pillar_name: str
    name: str
    outcome: str
    current_stage: int
    target_stage: int
    gap_size: int
    priority_score: float
    notes: str | None


class RoadmapEntry(BaseModel):
    """One gap placed in a month of the 12-month roadmap (Work Order D3)."""

    month: int
    code: str
    pillar_code: str
    pillar_name: str
    name: str
    current_stage: int
    target_stage: int
    priority_score: float


class GapAnalysisResponse(BaseModel):
    assessment_id: uuid.UUID
    version: int
    framework: ZtFramework
    target_stage: int
    target_label: str
    total_gap_count: int
    unscored_count: int
    # Capabilities whose stored per-capability target could not be used, so the
    # engagement target was applied instead (#188). The consultant workspace
    # reads this endpoint, and a fault disclosed in the client's PDF and the
    # client's dashboard but hidden from the person who can FIX it would be the
    # worst of the three places to leave silent.
    unusable_target_codes: list[str] = []
    gap_count_by_pillar: dict[str, int]
    gaps: list[GapItem]
    roadmap: list[RoadmapEntry] = []
