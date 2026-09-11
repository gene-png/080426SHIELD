"""Client-portal read routes (Sprint 5).

The client-facing surface for released deliverables (Master Spec §6.7, §12).
Tenant-enforced: the `{client_id}` in the path must match the caller's resolved
tenant (client-role users are pinned; platform admins select via X-Client-Id),
and a mismatch 404s — never 403 — so one tenant can't probe another's ids.

Only RELEASED deliverables are ever returned here (§12 release rule): a client
sees nothing until a consultant explicitly releases the finalized deliverable.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, NamedTuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.attack.analytics import compute as attack_compute
from app.attack.catalog import all_codes as attack_all_codes
from app.attack.catalog import tactic_by_id as attack_tactic_by_id
from app.attack.catalog import technique_by_id as attack_technique_by_id
from app.attack.pending import pending_codes as attack_pending_codes
from app.csf.gap import MAX_TIER as CSF_MAX_TIER
from app.csf.gap import analyze as csf_analyze_gaps
from app.csf.gap import resolve_target_tier as csf_resolve_target_tier
from app.csf.scoring import _label_from_average as csf_label_from_average
from app.csf.scoring import compute as csf_compute
from app.db.session import get_db
from app.dependencies import current_client, current_user
from app.logging import get_logger
from app.models.artifact import Artifact
from app.models.attack_assessment import (
    AttackAssessment,
    AttackAssessmentStatus,
    AttackCoverage,
)
from app.models.capability import (
    CapabilityDisposition,
    CapabilityItem,
    CapabilityList,
    CapabilityListStatus,
)
from app.models.client import Client
from app.models.csf_assessment import CsfAnswer, CsfAssessment, CsfAssessmentStatus
from app.models.deliverable import Deliverable
from app.models.risk_register import RiskEntry, RiskRegister
from app.models.service import Service, ServiceKind
from app.models.service_request import ServiceRequest
from app.models.user import User, UserRole
from app.models.zt_assessment import (
    ZtAnswer,
    ZtAssessment,
    ZtAssessmentStatus,
    ZtFramework,
)
from app.risk.engine import (
    Impact,
    Likelihood,
    RecommendedAction,
    RiskAxis,
    RiskTier,
    action_counts,
    axis_counts,
    matrix_counts,
    tier_counts,
)
from app.schemas.clients import (
    AttackDashboardResponse,
    AttackDashboardRollup,
    AttackDashboardTechnique,
    AttackTacticCoverage,
    ClientDeliverableListResponse,
    ClientDeliverableResponse,
    CsfDashboardResponse,
    CsfFunctionDashboard,
    CsfGapDashboard,
    RiskDashboardEntry,
    RiskDashboardResponse,
    RiskMatrixCell,
    TechDebtCategorySpend,
    TechDebtDashboardResponse,
    TechDebtItem,
    TechDebtRedundancy,
    ValueSummaryResponse,
    ZtDashboardResponse,
    ZtPillarDashboard,
)
from app.zt.catalog import capability_by_code as zt_capability_by_code
from app.zt.maturity import ZtFrameworkCode
from app.zt.maturity import stage_label as zt_stage_label
from app.zt.scoring import analyze_gaps as zt_analyze_gaps
from app.zt.scoring import compute as zt_compute
from app.zt.scoring import effective_target_stages as zt_effective_target_stages
from app.zt.scoring import (
    engagement_target_capability_count as zt_engagement_target_capability_count,
)
from app.zt.scoring import resolve_target_stage as zt_resolve_target_stage

router = APIRouter(prefix="/clients", tags=["clients"])

_log = get_logger(__name__)


def _artifact_title(db: Session, artifact_id: uuid.UUID | None) -> str | None:
    if artifact_id is None:
        return None
    art = db.get(Artifact, artifact_id)
    return art.title if art else None


@router.get(
    "/{client_id}/deliverables",
    response_model=ClientDeliverableListResponse,
    summary="Released deliverables for the client (client + admin)",
)
# SEE `_released_service_ids_by_kind` ABOVE: this endpoint's result set is
# asserted by a client-facing sentence on the home page ("still available under
# Results"). Narrowing what this returns -- hiding superseded rows, a visibility
# flag, a soft-delete, filtering by kind -- makes that sentence false without
# touching it. Nothing here enforces the agreement; it is stated so the next
# editor knows the dependency exists.
def list_client_deliverables(
    client_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> ClientDeliverableListResponse:
    # Tenant enforcement: the path id must be the caller's resolved tenant.
    # 404 (never 403) so we don't confirm another tenant's client id exists.
    if client_id != client.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found.",
        )

    rows = (
        db.execute(
            select(Deliverable, Service)
            .join(Service, Service.id == Deliverable.service_id)
            .where(
                Service.client_id == client.id,
                Deliverable.released_at.is_not(None),
            )
            .order_by(Deliverable.released_at.desc())
        )
        .tuples()
        .all()
    )
    _log.info(
        "client.deliverables.listed",
        client_id=str(client.id),
        actor_user_id=str(user.id),
        count=len(rows),
    )

    items = [
        ClientDeliverableResponse(
            id=deliv.id,
            service_id=deliv.service_id,
            service_kind=svc.kind,
            service_title=svc.title,
            title=deliv.title,
            summary=deliv.summary,
            version=deliv.version,
            released_at=deliv.released_at,
            superseded=deliv.superseded_by is not None,
            pdf_artifact_id=deliv.pdf_artifact_id,
            xlsx_artifact_id=deliv.xlsx_artifact_id,
            docx_artifact_id=deliv.docx_artifact_id,
            pdf_filename=_artifact_title(db, deliv.pdf_artifact_id),
            xlsx_filename=_artifact_title(db, deliv.xlsx_artifact_id),
            docx_filename=_artifact_title(db, deliv.docx_artifact_id),
        )
        for deliv, svc in rows
    ]
    return ClientDeliverableListResponse(items=items)


# ---------------------------------------------------------------------------
# Cross-service value loop (Master Spec §2.5)
#
# "AI suggests, code computes." Every number below is recomputed by a pure
# deterministic engine over the frozen post-release answer rows — never an LLM
# call. A service only feeds the client-visible summary once it has a RELEASED
# deliverable (§12): a service without one contributes null (the card renders
# "pending"), so a pre-release number can never leak.
# ---------------------------------------------------------------------------


def _deliverable_parent(db: Session, model, deliv: Deliverable, statuses):
    """The parent row `deliv` was BUILT from, resolved from the deliverable
    itself rather than from whatever is newest (#114).

    `parent_version` is stamped at finalize, which is where the content freezes
    against a specific parent (migration 0041). Resolving through it is the only
    rule under which a dashboard's numbers and the `deliverable_version` beside
    them describe the SAME record.

    What this replaced, and why the replacement is not a refinement: the old
    `_latest_finalized` took the highest-version row whose status was APPROVED or
    RELEASED, and its docstring claimed that "keeps the summary pinned to released
    work so a post-release draft can never leak its in-progress numbers to the
    client (§12)". It did — until a consultant clicked Approve on v2. Approving is
    a PREREQUISITE for finalizing v2, not an unusual act, so the guard's stated
    guarantee expired at the first ordinary step of the next engagement round and
    the client's dashboard switched to v2's numbers under a header still naming
    v1 and the PDF they already held.

    Returns None when the link cannot be established. That is two different
    worlds, and neither may fall back to "latest":

      * `parent_version` is NULL — finalized before migration 0041. Nothing ever
        fills it in for a multi-version service (#59 is open on exactly that), and
        guessing is the thing the column exists to prevent.
      * no row at that version holds a finalized status.

    Falling back to "latest finalized" for those rows would reinstate #114 for
    precisely the services most likely to HAVE several versions, so every caller
    refuses instead. `(service_id, version)` is unique in all four parent tables,
    so `scalar_one_or_none` raising on a second row is the wanted behaviour.
    """
    if deliv.parent_version is None:
        return None
    return db.execute(
        select(model).where(
            model.service_id == deliv.service_id,
            model.version == deliv.parent_version,
            model.status.in_(statuses),
        )
    ).scalar_one_or_none()


def _unresolved_parent(deliv: Deliverable, *, surface: str) -> HTTPException:
    """The refusal both halves of #114 raise when a deliverable's parent cannot
    be resolved. Logged with the cause, because the two ways to get here are not
    the same fault and a single message would send the reader the wrong way.

    404 rather than a 5xx keeps the transport identical to every other refusal on
    these routes (tenant parity: 404, never 403). The MESSAGE does not reuse
    "no released report yet", which would be false — there is one; what is
    missing is the link saying which assessment it was built from.
    """
    _log.warning(
        "client.dashboard_parent_unresolved",
        surface=surface,
        deliverable_id=str(deliv.id),
        service_id=str(deliv.service_id),
        deliverable_version=deliv.version,
        parent_version=deliv.parent_version,
        # Two causes named, three possible: a row PRESENT at that version with a
        # status outside `statuses` is indistinguishable here from no row at all,
        # and the two have different repairs. Left as-is because case three is
        # unreachable today (finalize requires APPROVED, and no path moves a
        # parent backwards), and it goes live the day a reopen path lands.
        # Tracked in #238.
        cause=(
            "parent_version is NULL (finalized before migration 0041; see #59)"
            if deliv.parent_version is None
            else "no finalized parent row at that version"
        ),
    )
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "reason": "dashboard_version_unresolved",
            "message": (
                "This report cannot be shown yet: we cannot establish which "
                "assessment version it was built from. Please contact your "
                "consultant."
            ),
        },
    )


def _released_parent(db: Session, model, service_id: uuid.UUID, statuses):
    """The parent row behind a service's RELEASED deliverable, or None when it
    cannot be resolved — the value-summary half of #114.

    The per-service dashboards resolve a deliverable first and pass it in; the
    cross-service cards start from a service id, so they resolve the released
    deliverable here. Released only, never the admin-preview `finalized`
    fallback: §12 says a service feeds the client-visible summary once it has a
    RELEASED deliverable, and these figures reach a client with no version label
    beside them to qualify what they describe.

    Returns None on an unresolvable parent. THREE options were available; each
    is stated WITH ITS OWN COST, because an earlier draft put the cost of the
    chosen option two paragraphs below the list, where a reader deciding whether
    to overturn it never reached it.

      1. **Skip the service inside the loop** (what the old code did). Rejected:
         these four callers SUM over services, so skipping one drops its gaps or
         its savings out of a total the client reads as the whole picture — a
         floor presented as a figure, with nothing on the card saying so.
      2. **Report the kind as UNRESOLVED**, which is what this does. Its cost:
         the client sees one card of four saying the figure cannot be resolved,
         beside a released report they can still open from `/results`. That is a
         false NEGATIVE and it is contradicted one click away, so it is the
         recoverable direction — the standing rule is that the cost of
         fail-closed is rework a human can clear.
      3. **Raise.** Rejected, and it is what an earlier version of this function
         did. Its cost is not confined to this card: it takes the whole
         `/value-summary` response with it, and `apps/web/src/app/home/page.tsx`
         fetches that endpoint inside an unguarded `Promise.all` beside the
         deliverables list, engagements and inbox, with no Next error boundary
         anywhere under `apps/web/src/app` (confirmed by glob: only
         `not-found.tsx` exists) — so the client loses the HOME PAGE, not one
         card. Filed as #236.

    **The trigger rates are not comparable, and that is what decided it.** The
    raise fires when ONE service of ONE kind is unresolvable; option 2 loses a
    single card in the same case. A whole page lost on one unresolvable service,
    against one card saying so, is not a trade between two equal false claims.

    **Nulling alone was not enough, and that is the other half of this change.**
    A bare null already means "pending", so reusing it would tell a client who
    HAS a released report that they do not — the exact falsehood
    `_unresolved_parent` refuses to write. The caller therefore reports
    `unresolved` BESIDE the null and the card says which it is. That is the
    `not_recorded`-versus-`null` distinction this repo already draws inside a
    single service, applied one layer out.

    **What an earlier draft got wrong, stated precisely so the retraction is not
    itself misread.** It called an unresolvable parent "a broken invariant, not a
    state the product can reach today". The SECOND clause stands and is
    re-asserted below. The FIRST is withdrawn: migration 0041 creates the NULL
    deliberately for multi-version services, and `deliverable_release.py`
    tolerates it — loudly and non-fatally, logged at WARNING precisely so it
    cannot be mistaken for the healthy path — so it is an anticipated legacy
    state, not a violated invariant.

    **Unreachable today, for two DIFFERENT reasons, one per cause.** A NULL
    `parent_version` cannot be produced because every `Deliverable` the product
    builds stamps it (four finalize routes; `seed_demo.py` too), so only a
    database carrying pre-0041 rows can hold one. A row present at that version
    with a non-finalized status cannot be produced for an unrelated reason —
    finalize requires APPROVED and nothing moves a parent backwards; see
    `_unresolved_parent`. One conclusion, two arguments; neither establishes the
    other.

    **Note for whoever repairs a NULL:** `deliverable_release.py` and migration
    0041 both say a re-release repairs it. It does not — `_release_parent`
    returns at the NULL check — and #59 is open on exactly that, including
    correcting those two comments. They are not corrected here: both files are
    outside this track's territory.
    """
    deliv = _latest_released_deliverable(db, service_id)
    if deliv is None:  # pragma: no cover - callers pass only released services
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "reason": "dashboard_version_unresolved",
                "message": (
                    "This summary cannot be shown yet: a service reported as "
                    "released has no released report. Please contact your "
                    "consultant."
                ),
            },
        )
    row = _deliverable_parent(db, model, deliv, statuses)
    if row is None:
        # Logged, not raised. The refusal still has to be OBSERVABLE from the
        # server side even though it no longer reaches the client as a 4xx --
        # otherwise "the figure could not be resolved" becomes a state nobody
        # can see happening. `_unresolved_parent` still builds the typed detail
        # for the per-service dashboards, which DO refuse.
        _log.warning(
            "client.value_summary.parent_unresolved",
            service_id=str(service_id),
            deliverable_id=str(deliv.id),
            deliverable_version=deliv.version,
            parent_version=deliv.parent_version,
            model=model.__name__,
        )
        return None
    return row

    # SYNCHRONIZED WITH `list_client_deliverables`, NOT DERIVED FROM IT, AND A
    # CLIENT-FACING SENTENCE DEPENDS ON THE TWO AGREEING.
    #
    # Both select on `Service.client_id == client.id` and
    # `Deliverable.released_at.is_not(None)`. `ValueLoopCard`'s unresolved copy
    # tells the client their reports are "still available under Results", which
    # is true only while this predicate and that one describe the same set.
    # Nothing ties them and no update closes the window, because it is not a
    # race -- it is two independently maintained predicates that happen to be
    # identical today.
    #
    # The WIDENING direction is guarded by a stated rule (`_released_parent`:
    # "Released only, never the admin-preview `finalized` fallback"). The
    # NARROWING direction has no guard at all: if the Results list ever hides
    # superseded rows -- it already computes `superseded` and today still lists
    # them -- or gains a per-artifact visibility flag, a soft-delete, or filters
    # by kind, then a client whose only report of a kind is filtered out reads
    # "still available under Results" over a list that does not contain it.
    #
    # The person making that change is editing a list endpoint and has no way to
    # know a string on the home page asserts its result set. That is what this
    # comment buys. Deriving both from one helper is the real fix and is a
    # refactor across two routes; filed rather than done here.


def _released_service_ids_by_kind(
    db: Session, client_id: uuid.UUID
) -> dict[ServiceKind, list[uuid.UUID]]:
    """Distinct service ids that have at least one RELEASED deliverable, grouped
    by service kind. This is the §12 visibility gate for the value summary."""
    rows = (
        db.execute(
            select(Service.id, Service.kind)
            .join(Deliverable, Deliverable.service_id == Service.id)
            .where(
                Service.client_id == client_id,
                Deliverable.released_at.is_not(None),
            )
            .distinct()
        )
        .tuples()
        .all()
    )
    out: dict[ServiceKind, list[uuid.UUID]] = {}
    for sid, kind in rows:
        out.setdefault(kind, []).append(sid)
    return out


def _csf_function_label(average_tier: float | None) -> str:
    """ "Unscored" when a function has no answers, else its tier band.

    ZT has `_zt_pillar_label` for exactly this. Without it a function nobody
    assessed renders as an em dash and sorts to the TOP of a list ordered by
    "largest move required" — because its gap is computed against 0 — with
    "0 gaps" beside it. A client reads their worst function as one that was
    never scored.
    """
    if average_tier is None:
        return "Unscored"
    return csf_label_from_average(average_tier)


def _csf_client_target_tier(db: Session, service_id: uuid.UUID) -> int | None:
    """The CSF target tier the client chose at intake, via the source request.

    Deliberately duplicated from `routes/csf.py::_client_target_tier` rather
    than imported: that one is private to the admin router, and a router
    importing another router's underscore helper is how import cycles start.
    Three lines, one query, and the duplication is stated here so the next
    reader does not "fix" it by reaching across.
    """
    svc = db.get(Service, service_id)
    if svc is None or svc.source_request_id is None:
        return None
    sr = db.get(ServiceRequest, svc.source_request_id)
    return sr.csf_target_tier if sr is not None else None


def _zt_client_target_stage(db: Session, service_id: uuid.UUID) -> int | None:
    """The ZT target stage the client chose at intake, via the source request.

    Twin of `_csf_client_target_tier` above, and duplicated from
    `routes/zt.py::_client_target_stage` for the same reason stated there.
    """
    svc = db.get(Service, service_id)
    if svc is None or svc.source_request_id is None:
        return None
    sr = db.get(ServiceRequest, svc.source_request_id)
    return sr.zt_target_stage if sr is not None else None


class _KindTotal(NamedTuple):
    """A per-kind aggregate, and WHY it is absent when it is absent.

    Three states, because a bare `None` was carrying two facts (#114 review):

      * `value=N,    unresolved=False` — a resolved figure.
      * `value=None, unresolved=False` — the client has no RELEASED service of
        this kind. Genuinely PENDING, which is what a null has always meant here.
      * `value=None, unresolved=True`  — the client HAS one, and the deliverable
        it is labelled with cannot be resolved to the assessment behind it.

    The third is the one that had nowhere to live. Reporting it as a null would
    tell a client who has a released report that they do not; raising took the
    whole home page down. See `_released_parent` for the full trade.

    A kind goes unresolved WHOLESALE rather than per service: these totals SUM,
    so dropping one service's contribution would publish a floor as a figure.
    """

    value: float | int | None
    unresolved: bool


class _TechDebtTotal(NamedTuple):
    """`_KindTotal` plus the savings floor flag. `cost_known` is False when a CUT
    capability lacked a cost, so the UI can mark the figure as a floor — an
    existing qualifier, kept distinct from `unresolved`, which is about whether
    the figure could be computed at all."""

    value: float | None
    cost_known: bool
    unresolved: bool


def _csf_gap_total(db: Session, service_ids: list[uuid.UUID]) -> _KindTotal:
    if not service_ids:
        return _KindTotal(None, False)
    total = 0
    for sid in service_ids:
        # #114: the released deliverable's parent, not the latest APPROVED row.
        # The `found` flag this loop used to carry went with the `continue` that
        # set it. `_released_parent` now returns None where that skipped, and the
        # kind is reported UNRESOLVED rather than summed over what is left — see
        # `_KindTotal`. Do not restore the skip: it publishes a floor.
        a = _released_parent(
            db,
            CsfAssessment,
            sid,
            (CsfAssessmentStatus.APPROVED, CsfAssessmentStatus.RELEASED),
        )
        if a is None:
            # One unresolvable service makes the whole KIND unresolved. Summing
            # the rest would publish a floor as a figure — option 1 in
            # `_released_parent`, rejected there for this reason.
            return _KindTotal(None, True)
        rows = db.execute(select(CsfAnswer).where(CsfAnswer.assessment_id == a.id)).scalars().all()
        answers: dict[str, int | None] = {r.subcategory_code: r.maturity_tier for r in rows}
        # Per-service client tier, same as the dashboard and the exporter (#79).
        # This card sits one click from the dashboard; reporting a different
        # number for the same assessment is what made the inconsistency visible.
        tier = _csf_client_target_tier(db, sid)
        # #184: resolve rather than branch on `is not None`. An unusable stored
        # tier used to reach the engine and be clamped, so this card could count
        # gaps against a target the dashboard beside it reported differently.
        resolved_tier, _source = csf_resolve_target_tier(tier)
        total += csf_analyze_gaps(answers, target_tier=resolved_tier).total_gap_count
    return _KindTotal(total, False)


def _zt_gap_total(db: Session, service_ids: list[uuid.UUID]) -> _KindTotal:
    if not service_ids:
        return _KindTotal(None, False)
    total = 0
    for sid in service_ids:
        # #114: the released deliverable's parent, not the latest APPROVED row.
        # See `_csf_gap_total` above for why the `found` flag went with it.
        a = _released_parent(
            db,
            ZtAssessment,
            sid,
            (ZtAssessmentStatus.APPROVED, ZtAssessmentStatus.RELEASED),
        )
        if a is None:
            # One unresolvable service makes the whole KIND unresolved. Summing
            # the rest would publish a floor as a figure — option 1 in
            # `_released_parent`, rejected there for this reason.
            return _KindTotal(None, True)
        fw = (
            ZtFrameworkCode.CISA_ZTMM_2_0
            if a.framework == ZtFramework.CISA_ZTMM_2_0
            else ZtFrameworkCode.DOD_ZTRA
        )
        rows = db.execute(select(ZtAnswer).where(ZtAnswer.assessment_id == a.id)).scalars().all()
        answers: dict[str, int | None] = {r.capability_code: r.maturity_stage for r in rows}
        targets: dict[str, int | None] = {r.capability_code: r.target_stage for r in rows}
        # Both targets, exactly as the exporter resolves them (#73/#79). Passing
        # `targets` alone left every capability with no per-row override on
        # DEFAULT_TARGET_STAGE, so a client on stage 4 with everything scored at
        # 3 saw "0 gaps" on this card while their released report listed 37.
        # That is #79's symptom in the service #73 was filed against, and this
        # function sat directly below the CSF twin that was fixed for it.
        stage = _zt_client_target_stage(db, sid)
        # #125: resolve rather than let `zt_analyze_gaps` clamp -- it now
        # raises, and an unresolved stored value would 500 the client's own
        # dashboard. STATED EXEMPTION: the resolved `source` is discarded here
        # because this helper returns a bare gap TOTAL and has nowhere to put
        # it. That is a real disclosure gap -- a client on an out-of-range
        # target sees a number computed against a stage they did not choose,
        # with no flag.
        #
        # #124 FIXED THE DASHBOARD, NOT THIS CARD, and this comment used to say
        # otherwise -- it claimed #124 "is rewriting this card to carry the
        # engagement target and its provenance", which would have been left
        # standing as a false statement about shipped code. The scope is
        # genuinely different: `zt_dashboard` reports on ONE service, so a
        # single `target_stage_source` describes it exactly, while this helper
        # sums across every released ZT service a client has and there is no
        # honest single source for a mixed set -- one engagement on the client's
        # own stage and another on the default is not "client" and not
        # "default". Answering that needs a decision about what the value card
        # should say, not a wider signature.
        #
        # Its CSF twin `_csf_gap_total` above loses the same FACT the same way
        # NOW, and this comment used to say otherwise. It read "there is no CSF
        # resolver to un-discard ... Same effect on the card, different repair",
        # which was true until #184 gave CSF a `resolve_target_tier`. Both twins
        # now compute a source and drop it into `_source`, so the two halves of
        # #207 are ONE repair: surface the source on the value card.
        #
        # Corrected here rather than left, because the sentence was sited
        # exactly where #207's owner would read it and would have sent them to
        # build a resolver that already shipped.
        #
        # Fixing only one would still leave the value card internally
        # inconsistent -- the half-fix shape that made #79 worse than the defect
        # it replaced. Both are left, together and on purpose, tracked in #207.
        resolved_stage, _source = zt_resolve_target_stage(fw, stage)
        total += zt_analyze_gaps(
            fw,
            answers,
            targets=targets,
            target_stage=resolved_stage,
        ).total_gap_count
    return _KindTotal(total, False)


def _attack_uncovered_total(db: Session, service_ids: list[uuid.UUID]) -> _KindTotal:
    if not service_ids:
        return _KindTotal(None, False)
    total = 0
    for sid in service_ids:
        # #114: the released deliverable's parent, not the latest APPROVED row.
        # See `_csf_gap_total` above for why the `found` flag went with it.
        a = _released_parent(
            db,
            AttackAssessment,
            sid,
            (AttackAssessmentStatus.APPROVED, AttackAssessmentStatus.RELEASED),
        )
        if a is None:
            # One unresolvable service makes the whole KIND unresolved. Summing
            # the rest would publish a floor as a figure — option 1 in
            # `_released_parent`, rejected there for this reason.
            return _KindTotal(None, True)
        rows = (
            db.execute(select(AttackCoverage).where(AttackCoverage.assessment_id == a.id))
            .scalars()
            .all()
        )
        coverage_map: dict[str, str | None] = {r.technique_code: r.status for r in rows}
        # No `pending_codes` here, and that is deliberate rather than an
        # oversight (#102). This reads `.gap` only, and `gap` is not a
        # withholdable status -- see `analytics._WITHHOLDABLE` and
        # `attack/pending.py` for why withholding an absence claim would delete a
        # finding while raising the coverage ratio. Passing the codes in would be
        # a guaranteed no-op on this number. If this ever starts reading
        # `covered`, `partial` or `coverage_pct`, it MUST pass them.
        #
        # `attack_dashboard` below DOES read all three, and shipped without
        # them; the §14 audit caught it. This comment was written for THIS
        # function and read as though it covered the file. Checking the callers
        # of what you just changed finds every copy that went through it and
        # misses every other caller sitting beside it.
        total += attack_compute(coverage_map).gap
    return _KindTotal(total, False)


def _tech_debt_savings(db: Session, service_ids: list[uuid.UUID]) -> _TechDebtTotal:
    """(annual savings, cost_known). Savings = sum of annual cost over CUT
    capabilities; cost_known is False when any CUT item lacked a cost (so the
    figure is a floor). Mirrors routes/tech_debt.py:consolidation_plan_summary."""
    if not service_ids:
        return _TechDebtTotal(None, True, False)
    total = 0.0
    cost_known = True
    for sid in service_ids:
        # #114: the released deliverable's parent, not the latest APPROVED list.
        # See `_csf_gap_total` above for why the `found` flag went with it.
        cl = _released_parent(
            db,
            CapabilityList,
            sid,
            (CapabilityListStatus.APPROVED, CapabilityListStatus.RELEASED),
        )
        if cl is None:
            # See `_csf_gap_total`: one unresolvable list makes the kind
            # unresolved rather than publishing a partial savings figure.
            return _TechDebtTotal(None, True, True)
        items = (
            db.execute(select(CapabilityItem).where(CapabilityItem.capability_list_id == cl.id))
            .scalars()
            .all()
        )
        for it in items:
            if it.disposition == CapabilityDisposition.CUT:
                if it.annual_cost_usd is None:
                    cost_known = False
                else:
                    total += float(it.annual_cost_usd)
    return _TechDebtTotal(total, cost_known, False)


@router.get(
    "/{client_id}/value-summary",
    response_model=ValueSummaryResponse,
    summary="Cross-service executive value summary (client + admin)",
)
def value_summary(
    client_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> ValueSummaryResponse:
    # Tenant enforcement mirrors the deliverables route: 404 (never 403) so one
    # tenant can't confirm another's id exists.
    if client_id != client.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found.",
        )

    by_kind = _released_service_ids_by_kind(db, client.id)
    td = _tech_debt_savings(db, by_kind.get(ServiceKind.TECH_DEBT, []))
    zt_ids = by_kind.get(ServiceKind.ZERO_TRUST_CISA, []) + by_kind.get(
        ServiceKind.ZERO_TRUST_DOD, []
    )
    zt = _zt_gap_total(db, zt_ids)
    attack = _attack_uncovered_total(db, by_kind.get(ServiceKind.ATTACK_COVERAGE, []))
    csf = _csf_gap_total(db, by_kind.get(ServiceKind.NIST_CSF, []))

    has_any = any(v is not None for v in (td.value, zt.value, attack.value, csf.value))
    # Published as its own field rather than left for the card to derive by
    # OR-ing four booleans. The card has to render when this is True even though
    # `has_any_data` is False -- that combination is a client who HAS released
    # reports and no resolvable figures, and it is exactly the case that used to
    # make the whole card disappear in silence.
    has_unresolved = any((td.unresolved, zt.unresolved, attack.unresolved, csf.unresolved))

    _log.info(
        "client.value_summary.computed",
        client_id=str(client.id),
        actor_user_id=str(user.id),
        has_any_data=has_any,
        has_unresolved=has_unresolved,
    )
    return ValueSummaryResponse(
        tech_debt_savings_usd=td.value,
        tech_debt_savings_cost_known=td.cost_known,
        tech_debt_savings_unresolved=td.unresolved,
        zt_gap_count=zt.value,
        zt_gap_unresolved=zt.unresolved,
        attack_uncovered_count=attack.value,
        attack_uncovered_unresolved=attack.unresolved,
        csf_gap_count=csf.value,
        csf_gap_unresolved=csf.unresolved,
        has_any_data=has_any,
        has_unresolved=has_unresolved,
    )


# ---------------------------------------------------------------------------
# Client-facing executive dashboards (D-035)
#
# Interactive per-service dashboards the client views AFTER release. Like the
# value summary, every number is recomputed by the deterministic engine over the
# released assessment's frozen rows — no LLM. Reached only when the service has a
# RELEASED deliverable (§12), gated via the same `_released_service_ids_by_kind`.
# ---------------------------------------------------------------------------


def _latest_released_deliverable(db: Session, service_id: uuid.UUID) -> Deliverable | None:
    """The most recently released deliverable for a service (for released_at +
    version), or None if the service has never released one."""
    return db.execute(
        select(Deliverable)
        .where(
            Deliverable.service_id == service_id,
            Deliverable.released_at.is_not(None),
        )
        .order_by(Deliverable.released_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _latest_finalized_deliverable(db: Session, service_id: uuid.UUID) -> Deliverable | None:
    """The most recent finalized deliverable, released or not (issue 4).

    Backs the ADMIN PREVIEW: after AI processing and finalize, the analyst can
    see the dashboard the client will get, before deciding to release it.
    """
    return db.execute(
        select(Deliverable)
        .where(
            Deliverable.service_id == service_id,
            Deliverable.finalized_at.is_not(None),
        )
        .order_by(Deliverable.finalized_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _dashboard_deliverable(
    db: Session,
    *,
    service_id: uuid.UUID,
    user: User,
    released_service_ids: list[uuid.UUID],
) -> tuple[Deliverable, bool] | None:
    """Resolve the deliverable a dashboard should render, and whether it is released.

    Issue 4 — the visibility rule for every service dashboard, in one place:

      * **Client**: released only. Unchanged from D-035; a client must never
        see figures an analyst has not signed off.
      * **Admin**: released, or merely FINALIZED. Previously an admin had no
        way to see the dashboard at all — finalize produced a PDF and an XLSX
        and nothing else — so they released it to the client sight-unseen.

    Returns ``(deliverable, is_released)``, or ``None`` when the caller may not
    see a dashboard yet. Both roles then run the SAME builder below, which is
    what stops the admin preview and the client view from ever drifting.
    """
    if service_id in released_service_ids:
        deliv = _latest_released_deliverable(db, service_id)
        if deliv is not None:
            return deliv, True
    if user.role == UserRole.ADMIN:
        deliv = _latest_finalized_deliverable(db, service_id)
        if deliv is not None:
            return deliv, False
    return None


def _dashboard_stamp(deliv: Deliverable, is_released: bool) -> datetime:
    """The timestamp a dashboard header shows.

    Released: when the client got it. Admin preview: when it was finalized —
    the response's `released` flag says which, so the UI can label a preview
    as a preview rather than implying the client can already see it.
    """
    return deliv.released_at if is_released and deliv.released_at else deliv.finalized_at


@router.get(
    "/{client_id}/attack/{service_id}/dashboard",
    response_model=AttackDashboardResponse,
    summary="Released ATT&CK coverage dashboard for the client (client + admin)",
)
def attack_dashboard(
    client_id: uuid.UUID,
    service_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> AttackDashboardResponse:
    """Coverage rollup + per-technique matrix for a released ATT&CK service.

    Tenant-enforced (404, never 403). Release-gated on the deliverable (NOT the
    assessment status), so it is visible exactly when the downloadable report is.
    """
    if client_id != client.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found.")

    released_attack_ids = _released_service_ids_by_kind(db, client.id).get(
        ServiceKind.ATTACK_COVERAGE, []
    )
    resolved = _dashboard_deliverable(
        db, service_id=service_id, user=user, released_service_ids=released_attack_ids
    )
    if resolved is None:
        # Typed 404 (D-016): the dashboard exists only once a deliverable is
        # released (or, for an admin, finalized). 404 (not 403) keeps parity
        # with the tenant-not-found path.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "reason": "dashboard_not_released",
                "message": "No released ATT&CK coverage report for this service yet.",
            },
        )
    deliv, is_released = resolved

    svc = db.get(Service, service_id)
    if svc is None:
        # A finalized deliverable implies a service; if that invariant is
        # broken, fail loudly rather than serve an empty dashboard.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "reason": "dashboard_not_released",
                "message": "No released ATT&CK coverage report for this service yet.",
            },
        )
    # #114: the numbers below and `deliverable_version` in the response must
    # name the same record, so the assessment is resolved FROM `deliv`.
    assessment = _deliverable_parent(
        db,
        AttackAssessment,
        deliv,
        (AttackAssessmentStatus.APPROVED, AttackAssessmentStatus.RELEASED),
    )
    if assessment is None:
        raise _unresolved_parent(deliv, surface="attack_dashboard")

    valid = attack_all_codes()
    rows = (
        db.execute(select(AttackCoverage).where(AttackCoverage.assessment_id == assessment.id))
        .scalars()
        .all()
    )
    coverage_map: dict[str, str | None] = {
        r.technique_code: r.status for r in rows if r.technique_code in valid
    }
    # The SAME derivation `heatmap` and `finalize_attack_deliverable` use. This
    # route reads `covered`, `partial` and `coverage_pct`, so it is exactly the
    # case `_attack_uncovered_total`'s comment names above -- and it is the one
    # a CLIENT reads, gated to appear when the released PDF does.
    rollup = attack_compute(coverage_map, attack_pending_codes(rows))

    techniques: list[AttackDashboardTechnique] = []
    # The SAME set the rollup above was built from, not a second derivation.
    withheld = attack_pending_codes(rows)
    for r in rows:
        if r.status is None or r.technique_code not in valid:
            continue
        tech = attack_technique_by_id(r.technique_code)
        tactic_name = attack_tactic_by_id(tech.tactics[0]).name if tech.tactics else ""
        techniques.append(
            AttackDashboardTechnique(
                code=tech.id,
                name=tech.name,
                tactic_name=tactic_name,
                status=r.status,
                pending_review=r.technique_code in withheld,
                detection_tools=list(r.detection_tools or []),
                prevention_tools=list(r.prevention_tools or []),
                response_tools=list(r.response_tools or []),
                rationale=r.rationale,
            )
        )
    techniques.sort(key=lambda t: t.code)

    _log.info(
        "client.attack_dashboard.built",
        client_id=str(client.id),
        service_id=str(service_id),
        actor_user_id=str(user.id),
        evaluated=len(techniques),
        coverage_pct=rollup.coverage_pct,
    )

    return AttackDashboardResponse(
        service_id=service_id,
        service_title=svc.title,
        released_at=_dashboard_stamp(deliv, is_released),
        released=is_released,
        deliverable_version=deliv.version,
        rollup=AttackDashboardRollup(
            total_evaluated=rollup.covered + rollup.partial + rollup.gap,
            covered=rollup.covered,
            partial=rollup.partial,
            gap=rollup.gap,
            not_applicable=rollup.not_applicable,
            pending_review=rollup.pending_review,
            coverage_pct=rollup.coverage_pct,
            by_tactic=[
                AttackTacticCoverage(
                    tactic_id=tc.tactic_id,
                    tactic_name=tc.tactic_name,
                    covered=tc.covered,
                    partial=tc.partial,
                    gap=tc.gap,
                    not_applicable=tc.not_applicable,
                    unscored=tc.unscored,
                    pending_review=tc.pending_review,
                    coverage_pct=tc.coverage_pct,
                )
                for tc in rollup.by_tactic
            ],
        ),
        techniques=techniques,
    )


_ZT_FRAMEWORK_LABELS = {
    ZtFrameworkCode.CISA_ZTMM_2_0: "CISA ZTMM 2.0",
    ZtFrameworkCode.DOD_ZTRA: "DoD ZTRA",
}


def _zt_pillar_label(average_stage: float | None, fw: ZtFrameworkCode) -> str:
    if average_stage is None:
        return "Unscored"
    return zt_stage_label(round(average_stage), fw)


@router.get(
    "/{client_id}/zt/{service_id}/dashboard",
    response_model=ZtDashboardResponse,
    summary="Released Zero Trust maturity dashboard for the client (client + admin)",
)
def zt_dashboard(
    client_id: uuid.UUID,
    service_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> ZtDashboardResponse:
    """Current-vs-target per-pillar maturity for a released Zero Trust service.

    Release-gated on the deliverable (either ZT framework kind), tenant-enforced.
    """
    if client_id != client.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found.")

    by_kind = _released_service_ids_by_kind(db, client.id)
    released_zt_ids = by_kind.get(ServiceKind.ZERO_TRUST_CISA, []) + by_kind.get(
        ServiceKind.ZERO_TRUST_DOD, []
    )
    resolved = _dashboard_deliverable(
        db, service_id=service_id, user=user, released_service_ids=released_zt_ids
    )
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "reason": "dashboard_not_released",
                "message": "No released Zero Trust report for this service yet.",
            },
        )
    deliv, is_released = resolved

    svc = db.get(Service, service_id)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "reason": "dashboard_not_released",
                "message": "No released Zero Trust report for this service yet.",
            },
        )
    # #114, as in `attack_dashboard` above: resolved FROM `deliv`.
    assessment = _deliverable_parent(
        db,
        ZtAssessment,
        deliv,
        (ZtAssessmentStatus.APPROVED, ZtAssessmentStatus.RELEASED),
    )
    if assessment is None:
        raise _unresolved_parent(deliv, surface="zt_dashboard")

    fw = (
        ZtFrameworkCode.CISA_ZTMM_2_0
        if assessment.framework == ZtFramework.CISA_ZTMM_2_0
        else ZtFrameworkCode.DOD_ZTRA
    )
    rows = (
        db.execute(select(ZtAnswer).where(ZtAnswer.assessment_id == assessment.id)).scalars().all()
    )
    answers: dict[str, int | None] = {r.capability_code: r.maturity_stage for r in rows}
    targets: dict[str, int | None] = {r.capability_code: r.target_stage for r in rows}

    # The client's OWN target, resolved ONCE, with its provenance (#124).
    #
    # This used to be `zt_compute(fw, targets)` — the per-capability targets
    # and nothing else. Only Run-AI and the client's self-assessment submit
    # ever write those, so a consultant-scored assessment left every one NULL,
    # `target_pct` came back None, and every pillar's gap rounded to 0.0 while
    # the released PDF from the same assessment listed its gaps against the
    # stage the client contracted for. Two surfaces, one assessment, opposite
    # stories — #79's symptom one service over, in the view the client reads.
    #
    # `resolve_target_stage` is the same call `routes/zt.py` makes on the
    # finalize path, so the number and its provenance come from one place
    # rather than being derived independently by two pieces of code that can
    # disagree (#125). `effective_target_stages` is the same rule `analyze_gaps`
    # applies per capability, imported rather than re-derived — #84 is on
    # record as `risk.py` re-deriving exactly this comparison inline, where a
    # complete call-site sweep reported clean over it.
    chosen = _zt_client_target_stage(db, service_id)
    target_stage, target_stage_source = zt_resolve_target_stage(fw, chosen)
    effective_targets = zt_effective_target_stages(fw, targets, target_stage)
    # NOT `gap`: the per-pillar loop below binds that name to a float.
    gap_analysis = zt_analyze_gaps(fw, answers, targets=targets, target_stage=target_stage)
    # How much of the rendered target the ENGAGEMENT stage actually decided.
    # Both ends are ordinary: a consultant-scored assessment sets no per-row
    # target and this is every capability, while a fully AI-scored one can
    # override all of them and this is zero. The UI needs it to avoid the
    # mirror image of #124 -- captioning a percentage built entirely from
    # per-capability overrides "your target, chosen at intake".
    engagement_target_capability_count = zt_engagement_target_capability_count(fw, targets)

    current = zt_compute(fw, answers)
    target = zt_compute(fw, effective_targets)
    target_by_code = {p.pillar_code: p for p in target.by_pillar}

    pillars: list[ZtPillarDashboard] = []
    for pc in current.by_pillar:
        tp = target_by_code.get(pc.pillar_code)
        cur_pct = pc.maturity_pct
        tgt_pct = tp.maturity_pct if tp is not None else None
        gap = round(max(0.0, (tgt_pct or 0.0) - (cur_pct or 0.0)), 1)
        weakest = [zt_capability_by_code(code).name for code in pc.weakest_capability_codes]
        pillars.append(
            ZtPillarDashboard(
                code=pc.pillar_code,
                name=pc.pillar_name,
                capability_count=pc.capability_count,
                answered_count=pc.answered_count,
                current_pct=cur_pct,
                current_label=_zt_pillar_label(pc.average_stage, fw),
                target_pct=tgt_pct,
                target_label=_zt_pillar_label(tp.average_stage, fw) if tp else "Unscored",
                gap_pct=gap,
                weakest=weakest,
            )
        )

    largest = max(pillars, key=lambda p: p.gap_pct, default=None)

    _log.info(
        "client.zt_dashboard.built",
        client_id=str(client.id),
        service_id=str(service_id),
        actor_user_id=str(user.id),
        framework=fw.value,
        current_pct=current.maturity_pct,
        # The three values you would want when a client disputes the numbers,
        # and the three this endpoint was most recently wrong about (#124).
        total_gap_count=gap_analysis.total_gap_count,
        target_stage=target_stage,
        target_stage_source=target_stage_source,
        engagement_target_capability_count=engagement_target_capability_count,
        # #188. `target_stage_source` records a fault in the ENGAGEMENT target;
        # this records the same class of fault one level down, and it belongs
        # in the row for the same reason: it is a number the client can dispute.
        unusable_target_codes=list(gap_analysis.unusable_target_codes),
    )

    return ZtDashboardResponse(
        service_id=service_id,
        service_title=svc.title,
        released_at=_dashboard_stamp(deliv, is_released),
        released=is_released,
        deliverable_version=deliv.version,
        framework=fw.value,
        framework_label=_ZT_FRAMEWORK_LABELS.get(fw, fw.value),
        current_label=current.overall_stage_label,
        current_pct=current.maturity_pct,
        target_label=target.overall_stage_label,
        target_pct=target.maturity_pct,
        target_stage=target_stage,
        target_stage_source=target_stage_source,
        engagement_target_capability_count=engagement_target_capability_count,
        # #188: taken off the SAME GapAnalysis the deliverable renders, not
        # re-derived here. A second derivation is #84's shape, and this one
        # would be worse than most -- the screen and the PDF would be stating
        # different facts about one assessment.
        unusable_target_codes=list(gap_analysis.unusable_target_codes),
        total_gap_count=gap_analysis.total_gap_count,
        largest_gap_pillar=largest.name if largest else None,
        largest_gap_pct=largest.gap_pct if largest else 0.0,
        pillars=pillars,
    )


_UNCATEGORIZED = "Uncategorized"


def _td_item(it: CapabilityItem) -> TechDebtItem:
    return TechDebtItem(
        name=it.name,
        vendor=it.vendor,
        category=it.category,
        function=it.function,
        annual_cost_usd=(float(it.annual_cost_usd) if it.annual_cost_usd is not None else None),
        license_count=it.license_count,
        disposition=(it.disposition.value if it.disposition is not None else None),
        notes=it.notes,
    )


@router.get(
    "/{client_id}/tech-debt/{service_id}/dashboard",
    response_model=TechDebtDashboardResponse,
    summary="Released software-portfolio dashboard for the client (client + admin)",
)
def tech_debt_dashboard(
    client_id: uuid.UUID,
    service_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> TechDebtDashboardResponse:
    """Software-portfolio spend / sprawl / redundancy / savings for a released
    Tech Debt service. Release-gated on the deliverable, tenant-enforced."""
    if client_id != client.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found.")

    released_ids = _released_service_ids_by_kind(db, client.id).get(ServiceKind.TECH_DEBT, [])
    resolved = _dashboard_deliverable(
        db, service_id=service_id, user=user, released_service_ids=released_ids
    )
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "reason": "dashboard_not_released",
                "message": "No released Tech Debt report for this service yet.",
            },
        )
    deliv, is_released = resolved

    svc = db.get(Service, service_id)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "reason": "dashboard_not_released",
                "message": "No released Tech Debt report for this service yet.",
            },
        )
    # #114, as in `attack_dashboard` above: resolved FROM `deliv`. Tech Debt's
    # parent is a CapabilityList rather than an assessment; `parent_version` is
    # stamped from `cap_list.version` at finalize, so the key is the same one.
    cl = _deliverable_parent(
        db,
        CapabilityList,
        deliv,
        (CapabilityListStatus.APPROVED, CapabilityListStatus.RELEASED),
    )
    if cl is None:
        raise _unresolved_parent(deliv, surface="tech_debt_dashboard")

    items = (
        db.execute(select(CapabilityItem).where(CapabilityItem.capability_list_id == cl.id))
        .scalars()
        .all()
    )

    annual_spend = 0.0
    savings = 0.0
    savings_cost_known = True
    # #126: the same floor question the SAVINGS figure has always asked, asked
    # of SPEND. An uncosted item contributes 0.0 below and is still counted in
    # `total_applications`, so the spend figure was a floor and said so nowhere
    # while `savings` beside it carried a flag for exactly this.
    spend_cost_known = True
    # category -> {"total": float, "count": int, "items": [CapabilityItem]}
    by_cat: dict[str, dict] = {}
    for it in items:
        cost = float(it.annual_cost_usd) if it.annual_cost_usd is not None else 0.0
        if it.annual_cost_usd is None:
            spend_cost_known = False
        annual_spend += cost
        if it.disposition == CapabilityDisposition.CUT:
            if it.annual_cost_usd is None:
                savings_cost_known = False
            else:
                savings += cost
        cat = it.category or _UNCATEGORIZED
        bucket = by_cat.setdefault(cat, {"total": 0.0, "count": 0, "items": []})
        bucket["total"] += cost
        bucket["count"] += 1
        bucket["items"].append(it)

    spend_by_category = [
        TechDebtCategorySpend(category=cat, total_usd=round(b["total"], 2), count=b["count"])
        for cat, b in sorted(by_cat.items(), key=lambda kv: kv[1]["total"], reverse=True)
    ]
    sprawl_by_category = [
        TechDebtCategorySpend(category=cat, total_usd=round(b["total"], 2), count=b["count"])
        for cat, b in sorted(by_cat.items(), key=lambda kv: kv[1]["count"], reverse=True)
        if b["count"] > 1
    ]
    redundancies = [
        TechDebtRedundancy(
            category=cat,
            count=b["count"],
            savings_usd=round(
                sum(
                    float(i.annual_cost_usd)
                    for i in b["items"]
                    if i.disposition == CapabilityDisposition.CUT and i.annual_cost_usd is not None
                ),
                2,
            ),
            items=[_td_item(i) for i in b["items"]],
        )
        for cat, b in sorted(by_cat.items(), key=lambda kv: kv[1]["count"], reverse=True)
        if b["count"] > 1
    ]

    _log.info(
        "client.tech_debt_dashboard.built",
        client_id=str(client.id),
        service_id=str(service_id),
        actor_user_id=str(user.id),
        applications=len(items),
        savings=savings,
    )

    # #126, the excluded-rows half. `build_context` (tech_debt/exporters.py) has
    # derived this since N-010 and the dashboard never received it, so a client
    # card could not disclose an exclusion even in principle. Derived the same
    # way as the exporter -- source-derived items only, so decomposing a bundle
    # into children can never move the arithmetic.
    source_rows_total = getattr(cl, "source_rows_total", None)
    included_count = sum(1 for it in items if getattr(it, "parent_item_id", None) is None)
    excluded_count = (
        max(source_rows_total - included_count, 0) if source_rows_total is not None else 0
    )
    # THREE states. "unknown" is not a hedge, it is the pre-0036 population and
    # every list not cut by an extraction: `source_rows_total` is NULL and no
    # reconciliation was ever recorded, so neither "complete" nor "partial" is a
    # claim the data supports. `services/stages.py`, in the helper returning
    # `getattr(cap_list, "source_rows_total", None) is not None`, already reads
    # NULL here as un-analysed and calls that the conservative direction; this
    # agrees with it rather than contradicting it.
    if source_rows_total is None:
        spend_completeness = "unknown"
    elif excluded_count or not spend_cost_known:
        spend_completeness = "partial"
    elif included_count > source_rows_total:
        # THE UNBALANCED CASE, and it must not reach "complete".
        #
        # `excluded_count` is `max(source_rows_total - included_count, 0)`, so
        # when more items exist than there were source rows -- two items sharing
        # one `source_row_index`, say -- the subtraction FLOORS TO ZERO and the
        # first two branches both fall through. With every cost known that
        # landed on "complete", whose definition in `schemas/clients.py` is
        # "every source row is accounted for and every item is costed". The
        # accounting demonstrably does not balance, so that claim is false.
        #
        # `build_context` already records this case for the exporter and pins
        # it with a test; the dashboard derived `excluded_count` "the same way"
        # and inherited the hole WITHOUT the caveat -- and it is strictly worse
        # here, because the exporter merely fails to disclose while this makes
        # the affirmative claim.
        #
        # "partial" rather than "unknown": completeness WAS recorded for this
        # list, it just does not reconcile, and "unknown" is defined as never
        # recorded. Neither word fits exactly -- this is a fourth state wearing
        # a three-state label -- but only one of the three is safe, and
        # CLAUDE.md's rule is that missing or unreliable data defaults to
        # UNCONFIRMED. Telling the truth about WHY needs `attribution_complete`
        # persisted, which is a migration this change does not carry.
        spend_completeness = "partial"
    else:
        spend_completeness = "complete"

    return TechDebtDashboardResponse(
        service_id=service_id,
        service_title=svc.title,
        released_at=_dashboard_stamp(deliv, is_released),
        released=is_released,
        deliverable_version=deliv.version,
        total_applications=len(items),
        annual_spend_usd=round(annual_spend, 2),
        identified_savings_usd=round(savings, 2),
        savings_cost_known=savings_cost_known,
        spend_completeness=spend_completeness,
        source_rows_total=source_rows_total,
        included_count=included_count,
        excluded_count=excluded_count,
        redundant_category_count=len(sprawl_by_category),
        spend_by_category=spend_by_category,
        sprawl_by_category=sprawl_by_category,
        redundancies=redundancies,
        items=[_td_item(i) for i in items],
    )


def _safe_enum(enum_cls, value):
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError:
        return None


@router.get(
    "/{client_id}/risk/dashboard",
    response_model=RiskDashboardResponse,
    summary="Finalized Risk Register dashboard for the client (client + admin)",
)
def risk_dashboard(
    client_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> RiskDashboardResponse:
    """The synthesized 5x5 Risk Register for the client. Client-level (not
    per-service); gated on the register being FINALIZED (exported), tenant-scoped.
    """
    if client_id != client.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found.")

    # The latest FINALIZED register, not the latest register (#123).
    #
    # This took the highest version and then 404'd if that one was unfinalized.
    # `generate` always mints the next version and only `export` sets
    # `finalized_at` -- so the moment a consultant clicked Generate to refresh
    # a delivered register, the client's dashboard 404'd with "No finalized
    # Risk Register for your organization yet". One existed, and they had been
    # reading it a minute earlier. It also removed the Risk link from Results,
    # which probes this endpoint to decide whether to show it, and it stayed
    # gone for however long the review took, with nothing telling anyone.
    #
    # Same root cause as #114: resolve the record being LABELLED, never
    # whatever row happens to be newest. Filtering in the QUERY rather than
    # checking after the fact is what makes generating a new version unable to
    # retract a delivered one -- the post-hoc check could only ever turn a
    # delivered register into a 404.
    #
    # The admin's `_latest_register` in `routes/risk.py` deliberately does NOT
    # filter this way and is not a twin: a consultant refreshing a register
    # needs to see the draft they just generated. Stated rather than left
    # implicit, because an unstated exemption reads as an oversight.
    reg = db.execute(
        select(RiskRegister)
        .where(
            RiskRegister.client_id == client.id,
            RiskRegister.finalized_at.is_not(None),
        )
        .order_by(RiskRegister.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    if reg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "reason": "dashboard_not_released",
                "message": "No finalized Risk Register for your organization yet.",
            },
        )

    entries = (
        db.execute(
            select(RiskEntry).where(RiskEntry.register_id == reg.id).order_by(RiskEntry.created_at)
        )
        .scalars()
        .all()
    )

    pairs: list[tuple[Likelihood, Impact]] = []
    for e in entries:
        lk = _safe_enum(Likelihood, e.likelihood)
        im = _safe_enum(Impact, e.impact)
        if lk is not None and im is not None:
            pairs.append((lk, im))
    matrix = matrix_counts(pairs)

    tiers = [t for t in (_safe_enum(RiskTier, e.tier) for e in entries) if t is not None]
    axes = [a for a in (_safe_enum(RiskAxis, e.axis) for e in entries) if a is not None]
    actions = [
        a for a in (_safe_enum(RecommendedAction, e.recommended_action) for e in entries) if a
    ]
    tc = tier_counts(tiers)

    _log.info(
        "client.risk_dashboard.built",
        client_id=str(client.id),
        actor_user_id=str(user.id),
        entries=len(entries),
    )

    return RiskDashboardResponse(
        client_id=client.id,
        released_at=reg.finalized_at,
        version=reg.version,
        total_entries=len(entries),
        critical_count=tc.get(RiskTier.CRITICAL.value, 0),
        high_count=tc.get(RiskTier.HIGH.value, 0),
        tier_counts=tc,
        axis_counts=axis_counts(axes),
        action_counts=action_counts(actions),
        matrix=[
            RiskMatrixCell(
                likelihood=cell.likelihood,
                impact=cell.impact,
                tier=cell.tier,
                count=cell.count,
            )
            for cell in matrix
        ],
        entries=[
            RiskDashboardEntry(
                title=e.title,
                axis=e.axis,
                likelihood=e.likelihood,
                impact=e.impact,
                tier=e.tier,
                recommended_action=e.recommended_action,
            )
            for e in entries
        ],
    )


@router.get(
    "/{client_id}/csf/{service_id}/dashboard",
    response_model=CsfDashboardResponse,
    summary="Released NIST CSF 2.0 dashboard for the client (client + admin)",
)
def csf_dashboard(
    client_id: uuid.UUID,
    service_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfDashboardResponse:
    """Per-function current-vs-target maturity for a released CSF service.

    Release-gated on the deliverable, tenant-enforced — the same contract the
    other four dashboards use. Deterministic: every figure comes from
    `csf/scoring.py` and `csf/gap.py`; no LLM output reaches this payload.
    """
    if client_id != client.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found.")

    released_csf_ids = _released_service_ids_by_kind(db, client.id).get(ServiceKind.NIST_CSF, [])
    resolved = _dashboard_deliverable(
        db, service_id=service_id, user=user, released_service_ids=released_csf_ids
    )
    not_released = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "reason": "dashboard_not_released",
            "message": "No released NIST CSF report for this service yet.",
        },
    )
    if resolved is None:
        raise not_released
    deliv, is_released = resolved

    svc = db.get(Service, service_id)
    if svc is None:
        raise not_released
    # #114, as in `attack_dashboard` above: resolved FROM `deliv`.
    assessment = _deliverable_parent(
        db,
        CsfAssessment,
        deliv,
        (CsfAssessmentStatus.APPROVED, CsfAssessmentStatus.RELEASED),
    )
    if assessment is None:
        raise _unresolved_parent(deliv, surface="csf_dashboard")

    rows = (
        db.execute(select(CsfAnswer).where(CsfAnswer.assessment_id == assessment.id))
        .scalars()
        .all()
    )
    answers: dict[str, int | None] = {r.subcategory_code: r.maturity_tier for r in rows}

    # The client's OWN target, not the engine default.
    #
    # #73 is open because the ZT exporter has computed gaps against a hardcoded
    # 3 for the life of the repo while the client had chosen 4 at intake — so
    # the delivered document listed a different gap set than the consultant
    # approved, and a stored target of 2 printed as 3. Reading the intake choice
    # here is that lesson applied before the same defect can be built, and
    # `target_tier_source` says which one was used so a fallback is never
    # mistaken for a decision.
    chosen = _csf_client_target_tier(db, service_id)
    # #184: one resolver, four sources. This was
    # `"client" if chosen is not None else "default"` -- keyed on whether a
    # value was OFFERED, never on whether it SURVIVED -- so a stored tier the
    # engine then discarded was reported to the client as their own choice.
    target_tier, target_tier_source = csf_resolve_target_tier(chosen)

    score = csf_compute(answers)
    gap = csf_analyze_gaps(answers, target_tier=target_tier)

    max_tier = CSF_MAX_TIER
    target_pct = round(target_tier / max_tier * 100, 1)

    functions: list[CsfFunctionDashboard] = []
    largest_gap_function: str | None = None
    largest_gap_pct = 0.0
    for fn in score.by_function:
        current_pct = (
            round(fn.average_tier / max_tier * 100, 1) if fn.average_tier is not None else None
        )
        gap_pct = round(max(0.0, target_pct - (current_pct or 0.0)), 1)
        if current_pct is not None and gap_pct > largest_gap_pct:
            largest_gap_pct = gap_pct
            largest_gap_function = fn.function_name
        functions.append(
            CsfFunctionDashboard(
                code=str(fn.function.value),
                name=fn.function_name,
                subcategory_count=fn.subcategory_count,
                answered_count=fn.answered_count,
                coverage_pct=fn.coverage_pct,
                current_tier=fn.average_tier,
                current_pct=current_pct,
                current_label=_csf_function_label(fn.average_tier),
                target_pct=target_pct,
                gap_pct=gap_pct,
                gap_count=gap.gap_count_by_function.get(str(fn.function.value), 0),
                weakest=list(fn.weakest_subcategory_codes),
            )
        )

    _log.info(
        "client.csf_dashboard.built",
        client_id=str(client.id),
        service_id=str(svc.id),
        actor_user_id=str(user.id),
        released=is_released,
        total_gap_count=gap.total_gap_count,
        # The two values you would want when a client disputes the numbers, and
        # the two this endpoint is most likely to be wrong about.
        target_tier=target_tier,
        target_tier_source=target_tier_source,
    )
    return CsfDashboardResponse(
        service_id=svc.id,
        service_title=svc.title,
        released_at=_dashboard_stamp(deliv, is_released),
        released=is_released,
        deliverable_version=deliv.version,
        overall_label=score.overall_maturity_label,
        current_tier=score.average_tier,
        current_pct=(
            round(score.average_tier / max_tier * 100, 1)
            if score.average_tier is not None
            else None
        ),
        coverage_pct=score.coverage_pct,
        target_tier=target_tier,
        target_label=gap.target_label,
        target_pct=target_pct,
        target_tier_source=target_tier_source,
        total_gap_count=gap.total_gap_count,
        largest_gap_function=largest_gap_function,
        largest_gap_pct=largest_gap_pct,
        functions=functions,
        top_gaps=[
            CsfGapDashboard(
                code=g.code,
                name=g.name,
                function=str(g.function.value),
                function_name=g.function_name,
                current_tier=g.current_tier,
                target_tier=g.target_tier,
                gap_size=g.gap_size,
                priority_score=g.priority_score,
            )
            for g in gap.gaps
        ],
    )
