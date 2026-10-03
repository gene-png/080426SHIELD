"""The ATT&CK what-if routes (#802 slice A). Admin only.

An admin removes tools from the client's last confirmed ATT&CK assessment and
sees how coverage would change. Nothing here writes to the real assessment, a
deliverable or anything the client sees: a scenario has its own tables
(migration 0060), and every figure is computed by `app.attack.scenario` from
the base assessment's rows and the scenario's own.

The AI job (`attack_scenario_delta`) ships UNREGISTERED until #806 releases its
prompt text; until then the run route refuses with a typed 503 before anything
is spent.
"""

from __future__ import annotations

import functools
import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session

from app.ai.batching import run_batches
from app.ai.llm import LLMClient
from app.ai.runs import (
    RunContext,
    RunFailed,
    Runner,
    RunOutcome,
    get_ai_run_runner,
    require_serves,
    running_run,
    start_run,
)
from app.attack import scenario
from app.attack.citations import Candidate
from app.attack.computed import awaiting_review_sentence
from app.attack.rules import parents_computed
from app.audit import audit
from app.config import get_settings
from app.db.session import get_db
from app.dependencies import current_client, require_role
from app.logging import get_logger
from app.models.ai_run import AiRun, AiRunStatus
from app.models.attack_assessment import AttackAssessment, AttackCoverage
from app.models.attack_scenario import AttackScenario, AttackScenarioRow, AttackScenarioState
from app.models.audit_entry import AuditEntry
from app.models.capability import CapabilityItem
from app.models.client import Client
from app.models.service import ServiceKind
from app.models.user import User, UserRole

# The egress projection and the LLM builder are mitre_map's own, imported
# rather than copied: the what-if offers the model the same four fields per
# tool, chosen by the same membership rules, and calls the provider the same
# way. It reads the client's CURRENT Tech Debt membership, NOT the set the
# base assessment was offered when it ran: a tool added to or dropped from
# the capability list since then is offered, or not, accordingly.
from app.routes.attack import _capability_payload, _client_capability_membership, _llm_dep
from app.schemas.ai_runs import AiRunStarted, RunAiRequest
from app.schemas.attack_scenario import (
    ScenarioBase,
    ScenarioCreateRequest,
    ScenarioDifference,
    ScenarioListResponse,
    ScenarioResponse,
    ScenarioRollup,
    ScenarioRunError,
    ScenarioSummary,
    ScenarioTechnique,
)
from app.security.rate_limit import RateLimiter, get_rate_limiter
from app.tenant import require_service_in_tenant

_log = get_logger(__name__)

router = APIRouter(prefix="/attack", tags=["attack"])

_admin_required = Depends(require_role(UserRole.ADMIN))

#: The audit action `routes/tech_debt.override_security_classification`
#: writes. A COPY of that literal: if it is renamed there, the (ii) half of the
#: drift check finds nothing and undercounts. `test_attack_scenario_routes`
#: drives the real endpoint, so a rename goes red there.
OVERRIDE_ACTION = "capability_item.security_classification_overridden"

#: Concurrent batches, as `mitre_map` runs them.
_MAX_WORKERS = 5

# NEEDS_CONFIRMED_MESSAGE and UNAVAILABLE_MESSAGE are COPIED into
# `apps/web/src/components/admin/attack/AttackScenarioPanel.tsx` (`NO_BASE`,
# `UNAVAILABLE`), which shows them before any request is refused. Change both.
NEEDS_CONFIRMED_MESSAGE = (
    "There is no confirmed assessment to compare with yet. Approve the ATT&CK "
    "assessment and review every technique in its review queue, then try again."
)
UNAVAILABLE_MESSAGE = "AI analysis for what-ifs is not available yet."
EMPTY_MESSAGE = "Choose at least one tool to remove."


def _unknown_tool_message(name: str) -> str:
    return f"{name} is not a tool this assessment cites. Pick it from the list."


def _refuse(code: int, reason: str, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"reason": reason, "message": message})


def _base_rows(db: Session, assessment_id: uuid.UUID) -> list[AttackCoverage]:
    return list(
        db.execute(select(AttackCoverage).where(AttackCoverage.assessment_id == assessment_id))
        .scalars()
        .all()
    )


def _scenario_or_404(db: Session, scenario_id: uuid.UUID, client: Client) -> AttackScenario:
    found = db.get(AttackScenario, scenario_id)
    if found is None or found.client_id != client.id:
        raise _refuse(
            status.HTTP_404_NOT_FOUND, "scenario_not_found", "This what-if was not found."
        )
    return found


def _rollup(r: Any, *, states_outside: bool, awaiting: int) -> ScenarioRollup:
    return ScenarioRollup(
        awaiting_review=awaiting,
        # Q4's approved sentence, from the one function every surface calls.
        awaiting_review_text=awaiting_review_sentence(awaiting),
        coverage_pct=r.coverage_pct,
        covered=r.covered,
        partial=r.partial,
        gap=r.gap,
        not_applicable=r.not_applicable,
        pending_review=r.pending_review,
        scored_count=r.scored_count,
        catalogue_count=r.catalogue_count,
        unable_to_determine=r.unable_to_determine if states_outside else None,
        outside_control_surface=r.outside_control_surface if states_outside else None,
    )


def _scenario_lists(db: Session, scenario_id: uuid.UUID) -> list[AttackScenarioRow]:
    return list(
        db.execute(
            select(AttackScenarioRow)
            .where(AttackScenarioRow.scenario_id == scenario_id)
            .order_by(AttackScenarioRow.technique_code)
        )
        .scalars()
        .all()
    )


def _lists_of(rows: list[AttackScenarioRow]) -> dict[str, dict[str, list[str]]]:
    return {
        r.technique_code: {
            "detection_tools": list(r.detection_tools),
            "prevention_tools": list(r.prevention_tools),
            "response_tools": list(r.response_tools),
        }
        for r in rows
    }


def _serialize(db: Session, s: AttackScenario) -> ScenarioResponse:
    base = db.get(AttackAssessment, s.base_assessment_id)
    base_rows = _base_rows(db, base.id)
    run = db.get(AiRun, s.ai_run_id) if s.ai_run_id else None
    if run is not None and run.status is AiRunStatus.RUNNING:
        # The panel's own run-status read (the workspace's leaves this purpose
        # out). Reap first, as every "in progress" read does, so a run no job
        # will finish is never shown as running.
        running_run(db, service_id=s.service_id, purpose=scenario.PURPOSE)
        db.refresh(run)
    rows = _scenario_lists(db, s.id)
    # The scenario's rows exist only once a run completed: before that there
    # is no "after", and the comparison is today against itself.
    what_if = scenario.scenario_rows(base_rows, _lists_of(rows)) if rows else base_rows
    comparison = scenario.compare(base, base_rows, what_if)
    higher = set(scenario.scored_higher(comparison, s.affected_codes))
    added = {t.casefold() for t in (s.tools_added_since_base or [])}
    # A mark needs a CREDIT: an accepted row with every function false names a
    # tool and credits it with nothing (#815 review round 3).
    credited_added = {
        r.technique_code: sorted(
            {
                a["tool"]
                for a in r.ai_rows
                if str(a.get("tool", "")).casefold() in added
                and any(a.get(f) is True for f in ("detection", "prevention", "response"))
            },
            key=str.casefold,
        )
        for r in rows
    }
    # The deliverable's own rule for stating the outside counts (#621, option
    # (a)): `states_outside_counts` reads `parents_computed`, so this does too.
    outside = parents_computed(base)
    return ScenarioResponse(
        id=s.id,
        service_id=s.service_id,
        state=s.state.value,
        removed=list(s.change_list.get("removed") or []),
        affected_codes=list(s.affected_codes),
        base_assessment_id=s.base_assessment_id,
        base_version=s.base_version,
        base_catalog_version=s.base_catalog_version,
        base_approved_at=base.approved_at,
        stale=scenario.is_stale(db, s.service_id, s.base_assessment_id),
        analysis_available=scenario.analysis_available(),
        ai_run_id=s.ai_run_id,
        run_status=run.status.value if run is not None else None,
        run_error=(
            ScenarioRunError(reason=run.error_reason, message=run.error_message)
            if run is not None and run.status is AiRunStatus.FAILED
            else None
        ),
        today=_rollup(comparison.today, states_outside=outside, awaiting=comparison.today_awaiting),
        after=(
            _rollup(comparison.after, states_outside=outside, awaiting=comparison.after_awaiting)
            if rows
            else None
        ),
        differences=[
            ScenarioDifference(
                technique_code=code,
                today=before,
                after=after,
                scored_higher=code in higher,
                credited_added_tool=bool(credited_added.get(code)),
            )
            for code, before, after in comparison.changed
        ],
        techniques=[
            ScenarioTechnique(
                technique_code=r.technique_code,
                detection_tools=list(r.detection_tools),
                prevention_tools=list(r.prevention_tools),
                response_tools=list(r.response_tools),
                ai_rows=list(r.ai_rows),
                credited_added_tools=credited_added[r.technique_code],
            )
            for r in rows
        ],
        dropped=s.dropped,
        not_reassessed=s.not_reassessed,
        scored_higher=s.scored_higher,
        tools_added_since_base=(
            len(s.tools_added_since_base) if s.tools_added_since_base is not None else None
        ),
        created_at=s.created_at,
    )


@router.post(
    "/services/{service_id}/scenarios",
    response_model=ScenarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a what-if: remove tools from the last confirmed assessment (admin)",
)
def create_scenario(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
    body: ScenarioCreateRequest | None = None,
) -> ScenarioResponse:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.ATTACK_COVERAGE)
    base = scenario.confirmed_base(db, svc.id)
    if base is None:
        raise _refuse(
            status.HTTP_409_CONFLICT, "scenario_needs_confirmed_assessment", NEEDS_CONFIRMED_MESSAGE
        )
    base_rows = _base_rows(db, base.id)
    try:
        removed = scenario.resolve_removed(base_rows, (body.removed if body else None) or [])
    except scenario.UnknownTool as exc:
        raise _refuse(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "scenario_unknown_tool",
            _unknown_tool_message(exc.name),
        ) from exc
    except scenario.EmptyChangeList as exc:
        raise _refuse(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "scenario_empty_change", EMPTY_MESSAGE
        ) from exc
    spellings = scenario.removed_spellings(
        removed,
        client_org_name=client.legal_name,
        redaction_mode=get_settings().shield_redaction_mode,
    )
    affected = scenario.affected_codes(base_rows, spellings)
    s = AttackScenario(
        client_id=client.id,
        service_id=svc.id,
        base_assessment_id=base.id,
        base_version=base.version,
        base_catalog_version=base.catalog_version,
        base_status_rules=base.status_rules,
        change_list={"removed": removed, "added": []},
        affected_codes=affected,
        state=AttackScenarioState.DRAFT,
        created_by=user.id,
    )
    db.add(s)
    db.flush()
    # Counts only: tool names are the client's data.
    audit(
        db,
        action="attack.scenario.created",
        target_type="attack_scenario",
        target_id=s.id,
        actor_user_id=user.id,
        details={
            "service_id": str(svc.id),
            "base_assessment_id": str(base.id),
            "removed": len(removed),
            "affected": len(affected),
        },
    )
    db.commit()
    _log.info(
        "attack.scenario.created",
        scenario_id=str(s.id),
        removed=len(removed),
        affected=len(affected),
    )
    return _serialize(db, s)


@router.get(
    "/services/{service_id}/scenarios",
    response_model=ScenarioListResponse,
    summary="The service's what-ifs, newest first (admin)",
)
def list_scenarios(
    service_id: uuid.UUID,
    _user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> ScenarioListResponse:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.ATTACK_COVERAGE)
    found = (
        db.execute(
            select(AttackScenario)
            .where(AttackScenario.service_id == svc.id)
            .order_by(AttackScenario.created_at.desc())
        )
        .scalars()
        .all()
    )
    base = scenario.confirmed_base(db, svc.id)
    return ScenarioListResponse(
        base=(
            None
            if base is None
            else ScenarioBase(
                assessment_id=base.id,
                version=base.version,
                approved_at=base.approved_at,
                tools=scenario.cited_tools(_base_rows(db, base.id)),
            )
        ),
        scenarios=[
            ScenarioSummary(
                id=s.id,
                service_id=s.service_id,
                state=s.state.value,
                removed=list(s.change_list.get("removed") or []),
                affected_count=len(s.affected_codes),
                base_assessment_id=s.base_assessment_id,
                base_version=s.base_version,
                created_at=s.created_at,
            )
            for s in found
        ],
    )


@router.get(
    "/scenarios/{scenario_id}",
    response_model=ScenarioResponse,
    summary="A what-if: coverage today against with-these-changes (admin)",
)
def get_scenario(
    scenario_id: uuid.UUID,
    _user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> ScenarioResponse:
    return _serialize(db, _scenario_or_404(db, scenario_id, client))


@router.post(
    "/scenarios/{scenario_id}/discard",
    response_model=ScenarioResponse,
    summary="Set a what-if aside (admin)",
)
def discard_scenario(
    scenario_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> ScenarioResponse:
    s = _scenario_or_404(db, scenario_id, client)
    s.state = AttackScenarioState.DISCARDED
    audit(
        db,
        action="attack.scenario.discarded",
        target_type="attack_scenario",
        target_id=s.id,
        actor_user_id=user.id,
        details={"service_id": str(s.service_id)},
    )
    db.commit()
    _log.info("attack.scenario.discarded", scenario_id=str(s.id))
    return _serialize(db, s)


def _llm_builder(db: Annotated[Session, Depends(get_db)]) -> Callable[[], LLMClient]:
    """The provider, built only when called: mitre_map's `_llm_dep`, deferred
    until the run route has made every refusal (#815 review, F4)."""
    return lambda: _llm_dep(db)


def _refuse_unless_runnable(db: Session, s: AttackScenario) -> None:
    if s.state is AttackScenarioState.DISCARDED:
        raise _refuse(
            status.HTTP_409_CONFLICT,
            "scenario_discarded",
            "This what-if was set aside, so it cannot be run. Start a new one.",
        )
    if _scenario_lists(db, s.id):
        raise _refuse(
            status.HTTP_409_CONFLICT,
            "scenario_already_run",
            "This what-if has already been analysed. Start a new one to change it.",
        )
    if scenario.is_stale(db, s.service_id, s.base_assessment_id):
        raise _refuse(
            status.HTTP_409_CONFLICT,
            "scenario_stale",
            "A newer confirmed assessment exists, so this what-if would compare with an "
            "out-of-date one. Start a new what-if.",
        )


@router.post(
    "/scenarios/{scenario_id}/run",
    response_model=AiRunStarted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-assess a what-if's affected techniques in the background (admin)",
)
def run_scenario(
    scenario_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
    build_llm: Annotated[Callable[[], LLMClient], Depends(_llm_builder)],
    runner: Annotated[Runner, Depends(get_ai_run_runner)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    body: RunAiRequest | None = None,
) -> AiRunStarted:
    """Every refusal that needs no AI is made here, synchronously, before
    anything is spent. The work is `_scenario_run_work`, in the background.

    The rate limit and the provider are taken HERE, in the body, after the
    route's own refusals (404, 503, the `serves` 422, and the discarded,
    already-run and stale 409s), not as dependencies: a dependency runs before
    the body, so a run the 503 refused used to spend a rate-limit token and
    build a provider (#815 review, F4). `start_run`'s refusals (#504's mode
    change, a run in progress on other input) still come after both."""
    s = _scenario_or_404(db, scenario_id, client)
    if not scenario.analysis_available():
        raise _refuse(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "scenario_analysis_unavailable",
            UNAVAILABLE_MESSAGE,
        )
    serves = require_serves(body.serves if body else None)
    _refuse_unless_runnable(db, s)
    limiter.enforce_ai(client.id)
    llm = build_llm()
    started = start_run(
        db,
        llm=llm,
        serves=serves,
        service_id=s.service_id,
        client_id=client.id,
        purpose=scenario.PURPOSE,
        subject_id=s.id,
        requested_by=user.id,
        runner=runner,
        work=functools.partial(_scenario_run_work, scenario_id=s.id),
    )
    # Written as UPDATEs, not through `s`: the job may already be running, and
    # a discard may have landed since `s` was read. Assigning `s.state` would
    # flush CONFIRMED over that discard. The run id is recorded either way;
    # the state moves only from DRAFT.
    #
    # Nor is the run id repointed once a result exists: a run that completed
    # between `_refuse_unless_runnable` and `start_run` stays the scenario's
    # run, and the later one fails `scenario_already_run` on its own (#815
    # review round 2).
    db.execute(
        update(AttackScenario)
        .where(
            AttackScenario.id == s.id,
            ~exists().where(AttackScenarioRow.scenario_id == AttackScenario.id),
        )
        .values(ai_run_id=started.run_id)
        .execution_options(synchronize_session=False)
    )
    db.execute(
        update(AttackScenario)
        .where(
            AttackScenario.id == s.id,
            AttackScenario.state == AttackScenarioState.DRAFT,
        )
        .values(state=AttackScenarioState.CONFIRMED)
        .execution_options(synchronize_session=False)
    )
    audit(
        db,
        action="attack.scenario.run_started",
        target_type="attack_scenario",
        target_id=s.id,
        actor_user_id=user.id,
        details={"run_id": str(started.run_id), "joined": started.joined},
    )
    db.commit()
    return started


def _scenario_run_work(session: Session, ctx: RunContext, *, scenario_id: uuid.UUID) -> RunOutcome:
    """The re-assessment, in the background job's own session.

    Re-loads everything by id. Writes only the scenario's own rows; the base
    assessment's rows are read, copied and never touched."""
    db = session
    s = db.get(AttackScenario, scenario_id)
    if s is None or s.state is AttackScenarioState.DISCARDED:
        raise RunFailed("scenario_discarded", "This what-if was set aside before the run finished.")
    base = db.get(AttackAssessment, s.base_assessment_id)
    client = db.get(Client, ctx.client_id)
    base_rows = _base_rows(db, base.id)
    removed = list(s.change_list.get("removed") or [])
    affected = list(s.affected_codes)
    mode = get_settings().shield_redaction_mode
    # Every spelling of a removed tool goes, the redacted one included (F2),
    # from what the model is offered AND from what the resolver may confirm,
    # so a removed tool the AI names anyway is counted, never credited.
    spellings = scenario.removed_spellings(
        removed, client_org_name=client.legal_name, redaction_mode=mode
    )
    membership = _client_capability_membership(db, ctx.client_id)
    kept_offers = [p for p in membership.sent if not spellings.covers(p.capability.name)]
    kept = [p.capability for p in kept_offers]
    indistinct = [c.name for c in kept if spellings.shares_shown_form(c.name)]
    # (b2): which offered tools are newer than the base, or None if unknowable.
    item_ids = [uuid.UUID(p.item_id) for p in kept_offers if p.item_id]
    created = {
        str(i): at
        for i, at in db.execute(
            select(CapabilityItem.id, CapabilityItem.created_at).where(
                CapabilityItem.id.in_(item_ids)
            )
        ).all()
    }
    # (ii): the latest classification override per offered item. The audit
    # row is the only record of WHEN; `updated_at` moves on every edit.
    overridden = {
        str(i): at
        for i, at in db.execute(
            select(AuditEntry.target_id, func.max(AuditEntry.at))
            .where(
                AuditEntry.action == OVERRIDE_ACTION,
                AuditEntry.target_type == "capability_item",
                AuditEntry.target_id.in_(item_ids),
            )
            .group_by(AuditEntry.target_id)
        ).all()
    }
    added = scenario.tools_added_since(
        kept_offers, membership.lists, created, base.approved_at, overridden
    )
    inputs = scenario.batch_inputs(
        base_rows, affected, spellings, _capability_payload(kept), size=scenario.BATCH_SIZE
    )
    remaining = [Candidate(name=c.name, vendor=c.vendor) for c in kept]
    out = run_batches(
        db,
        ctx.llm,
        scenario.PURPOSE,
        inputs,
        requested_by=ctx.requested_by,
        service_id=ctx.service_id,
        client_id=ctx.client_id,
        client_org_name=client.legal_name,
        name_hints=(),
        deadline_at=ctx.deadline_at,
        max_workers=_MAX_WORKERS,
        deadline_message=(
            "This what-if did not finish within its time limit, so it was stopped "
            "and nothing from it was kept. Run it again."
        ),
    )
    index = {tuple(b["technique_codes"]): i for i, b in enumerate(inputs)}
    parsed: dict[int, scenario.ParsedDelta] = {}
    shape_failures = 0
    for asked, data in zip(out.inputs, out.answers, strict=True):
        codes = list(asked["technique_codes"])
        i = index[tuple(codes)]
        try:
            parsed[i] = scenario.parse_delta(
                data,
                asked=codes,
                available=remaining,
                lost=inputs[i]["lost_functions"],
                indistinct=indistinct,
                client_org_name=client.legal_name,
                redaction_mode=mode,
            )
        except scenario.ScenarioShapeError:
            # Answered, but not in the contract's shape: its techniques are not
            # re-assessed, and the batch counts as failed. A RATCHET: the job's
            # parser (`top_level_key="rows"`) already fails such a batch inside
            # `run_batches`, so no answer reaches here without a `rows` list
            # today. It would again if the job were given its own parser.
            shape_failures += 1
    merged = scenario.merge_batches(inputs, parsed)

    # D-031's re-read: a discard that raced the run wins.
    db.refresh(s)
    if s.state is AttackScenarioState.DISCARDED:
        raise RunFailed("scenario_discarded", "This what-if was set aside before the run finished.")
    # The run route checks this before `start_run`, but a run completing in
    # between could let a second one start. Its answer is never written over
    # the first's: refused, typed, nothing deleted (#815 review, F5).
    if _scenario_lists(db, s.id):
        raise RunFailed(
            "scenario_already_run",
            "This what-if was analysed by another run while this one was working, "
            "so this run's result was not kept.",
        )
    by_code: dict[str, list[dict[str, Any]]] = {}
    for row in merged.accepted:
        by_code.setdefault(row["technique_code"], []).append(row)
    for code in affected:
        lists = merged.lists[code]
        db.add(
            AttackScenarioRow(
                scenario_id=s.id,
                technique_code=code,
                detection_tools=lists["detection_tools"],
                prevention_tools=lists["prevention_tools"],
                response_tools=lists["response_tools"],
                ai_rows=by_code.get(code, []),
            )
        )
    comparison = scenario.compare(base, base_rows, scenario.scenario_rows(base_rows, merged.lists))
    higher = scenario.scored_higher(comparison, affected)
    s.dropped = merged.dropped
    s.not_reassessed = merged.not_reassessed
    s.scored_higher = len(higher)
    s.tools_added_since_base = added
    db.flush()
    reassessed = len(affected) - len(merged.not_reassessed)
    return RunOutcome(
        result={
            "affected": len(affected),
            "reassessed": reassessed,
            "not_reassessed": len(merged.not_reassessed),
            "dropped": merged.dropped,
            "scored_higher": len(higher),
        },
        applied_count=reassessed,
        batches_total=out.total,
        batches_failed=out.failed + shape_failures,
        accounting=(
            "attack.scenario.run_applied",
            {
                "scenario_id": str(s.id),
                "affected": len(affected),
                "reassessed": reassessed,
                "scored_higher": len(higher),
            },
        ),
    )
