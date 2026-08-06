"""Derived progress stages — one vocabulary across all four services.

Presentation only. Nothing here writes, and no service's state machine, route or
audit vocabulary changes: `status` still means exactly what it meant before.
This module answers a narrower question — "how far along does this version
look?" — so the four workspaces can show one progress bar instead of four
different ones.

Six stages: prepare, analyze, review, approve, generate, release.

Two of them are not states anybody stores. A capability list is DRAFT before a
Run-AI and still DRAFT afterwards, and generating a deliverable does not move
`status` either. So `analyze` and `generate` are derived from evidence:

  analyze   a COMPLETED llm_call for this service, for one of the service's
            analysis purposes
  generate  a Deliverable row for this service

THE VERSION TRAP. `llm_calls` carries `service_id` and no version link at all,
and `Deliverable.version` counts deliverables, not assessments. So "has this
service ever had an AI run?" is trivially answerable and completely wrong: it
would light up `analyze` on a brand-new draft because some earlier, discarded
draft was analysed months ago — a stale-evidence bug of exactly the shape that
bit Sprint 9.

Both signals are therefore anchored to the version's own ``created_at``: only
evidence produced at or after this version came into existence counts for it.
Evidence from v1 is strictly older than v2's creation, so it cannot leak
forward. This needs no migration and no new column — the timestamps that decide
it are already there.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deliverable import Deliverable
from app.models.llm_call import LLMCall, LLMCallStatus
from app.models.service import ServiceKind

# Stage keys, in order. Stable identifiers — the UI supplies the wording.
STAGE_KEYS = ("prepare", "analyze", "review", "approve", "generate", "release")

# Which llm_call purposes count as "this service was analysed". Deliberately
# excludes narrative/generate purposes: drafting a summary is not analysis.
ANALYSIS_PURPOSES: dict[ServiceKind, frozenset[str]] = {
    ServiceKind.TECH_DEBT: frozenset({"extract.capabilities"}),
    # Both Zero Trust frameworks (CISA ZTMM and DoD ZTRA) score through the
    # same purpose; they are separate service kinds but one analysis job.
    ServiceKind.ZERO_TRUST_CISA: frozenset({"zt_score"}),
    ServiceKind.ZERO_TRUST_DOD: frozenset({"zt_score"}),
    ServiceKind.NIST_CSF: frozenset({"csf_score"}),
    ServiceKind.ATTACK_COVERAGE: frozenset({"mitre_map"}),
}

# `prepare` means "the input this service runs on has arrived". For Zero Trust
# and CSF that is the client submitting their self-assessment, which is a real
# stored status. Tech Debt and ATT&CK have no client-input step at all, so for
# them the stage is complete as soon as the version exists — there is nothing
# to wait for. No stage is shown greyed-out and permanently dead; the asymmetry
# lives in what `prepare` means per service, not in a stage that never lights.
_CLIENT_INPUT_KINDS = frozenset(
    {
        ServiceKind.ZERO_TRUST_CISA,
        ServiceKind.ZERO_TRUST_DOD,
        ServiceKind.NIST_CSF,
    }
)


@dataclass(frozen=True)
class Stage:
    key: str
    #: complete | current | pending
    state: str


def analysis_ran_for_version(
    db: Session,
    *,
    service_id,
    kind: ServiceKind,
    version_created_at: datetime | None,
) -> bool:
    """True when an AI analysis completed for THIS version.

    Anchored to ``version_created_at``: a run belonging to an earlier draft is
    older than this version's creation and is not counted. A version with no
    ``created_at`` (shouldn't happen — TimestampMixin sets it) claims nothing
    rather than claiming everything.
    """
    purposes = ANALYSIS_PURPOSES.get(kind)
    if not purposes or version_created_at is None:
        return False
    stmt = select(LLMCall.id).where(
        LLMCall.service_id == service_id,
        LLMCall.purpose.in_(tuple(purposes)),
        LLMCall.status == LLMCallStatus.COMPLETED,
        LLMCall.requested_at >= version_created_at,
    )
    return db.execute(stmt.limit(1)).first() is not None


def deliverable_exists_for_version(
    db: Session,
    *,
    service_id,
    version_created_at: datetime | None,
) -> bool:
    """True when a deliverable was generated for THIS version.

    Same anchor, same reason: ``Deliverable.version`` is its own counter and
    says nothing about which assessment version it was built from.
    """
    if version_created_at is None:
        return False
    stmt = select(Deliverable.id).where(
        Deliverable.service_id == service_id,
        Deliverable.created_at >= version_created_at,
    )
    return db.execute(stmt.limit(1)).first() is not None


def derive_stages(
    *,
    kind: ServiceKind,
    status: str,
    client_input_received: bool,
    analyzed: bool,
    generated: bool,
) -> list[Stage]:
    """Map stored status + derived evidence onto the six stages.

    Pure: every input is already resolved, so the whole table is testable
    without a database.
    """
    released = status == "released"
    approved = status in ("approved", "released")

    prepared = True if kind not in _CLIENT_INPUT_KINDS else client_input_received
    # `review` is the consultant working the draft. There is no stored marker
    # for "I have looked at this", so it is treated as reached once there is
    # something to review and not yet signed off by approval.
    reviewed = approved
    done = {
        "prepare": prepared,
        "analyze": prepared and analyzed,
        "review": reviewed,
        "approve": approved,
        "generate": generated,
        "release": released,
    }

    # Progress is monotonic: reaching a stage means the ones before it are
    # behind you. Without this the bar renders its cursor BEHIND finished work
    # — an approved, generated list whose extraction predates the current
    # version shows `analyze` as "current" sitting left of three completed
    # stages, which reads as a broken step rather than a passed one. Evidence
    # of a specific AI run is a different question from process position, and
    # this bar answers the second.
    reached = False
    resolved: dict[str, bool] = {}
    for key in reversed(STAGE_KEYS):
        reached = reached or done[key]
        resolved[key] = reached

    stages: list[Stage] = []
    current_assigned = False
    for key in STAGE_KEYS:
        if resolved[key]:
            stages.append(Stage(key=key, state="complete"))
            continue
        # The first unfinished stage is where the work actually is.
        stages.append(Stage(key=key, state="pending" if current_assigned else "current"))
        current_assigned = True
    return stages
