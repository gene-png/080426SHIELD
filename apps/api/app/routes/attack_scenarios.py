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
from collections.abc import Callable, Iterable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session

from app.ai.batching import run_batches
from app.ai.engine import run_job
from app.ai.llm import LLMClient
from app.ai.runs import (
    RunContext,
    RunFailed,
    Runner,
    RunOutcome,
    get_ai_run_runner,
    provider_serves,
    require_serves,
    running_run,
    start_run,
)
from app.attack import scenario, scenario_intent
from app.attack.citations import Candidate
from app.attack.computed import awaiting_review_sentence
from app.attack.rules import parents_computed
from app.audit import audit
from app.config import get_settings
from app.db.session import get_db
from app.dependencies import current_client, require_role
from app.logging import correlation_id_var, get_logger
from app.models.ai_run import AiRun, AiRunStatus
from app.models.attack_assessment import AttackAssessment, AttackCoverage
from app.models.attack_scenario import AttackScenario, AttackScenarioRow, AttackScenarioState
from app.models.audit_entry import AuditEntry
from app.models.capability import CapabilityItem
from app.models.client import Client
from app.models.llm_call import LLMCall
from app.models.service import ServiceKind
from app.models.user import User, UserRole

# The egress projection and the LLM builder are mitre_map's own, imported
# rather than copied: the what-if offers the model the same four fields per
# tool, chosen by the same membership rules, and calls the provider the same
# way. It reads the client's CURRENT Tech Debt membership, NOT the set the
# base assessment was offered when it ran: a tool added to or dropped from
# the capability list since then is offered, or not, accordingly.
from app.routes.attack import _capability_payload, _client_capability_membership, _llm_dep
from app.routes.tech_debt import SECURITY_CLASSIFICATION_OVERRIDDEN
from app.schemas.ai_runs import AiRunStarted, RunAiRequest
from app.schemas.attack_scenario import (
    ScenarioAddedTool,
    ScenarioBase,
    ScenarioCreateRequest,
    ScenarioDifference,
    ScenarioListResponse,
    ScenarioNotUnderstood,
    ScenarioParseRequest,
    ScenarioParseResponse,
    ScenarioResponse,
    ScenarioRollup,
    ScenarioRunError,
    ScenarioSummary,
    ScenarioTechnique,
)
from app.security.rate_limit import RateLimiter, get_rate_limiter
from app.tech_debt.extract import name_hints_for_tenant
from app.tenant import require_service_in_tenant

_log = get_logger(__name__)

router = APIRouter(prefix="/attack", tags=["attack"])

_admin_required = Depends(require_role(UserRole.ADMIN))

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
# B8 (14:58Z) replaces copy 17: a what-if may only add.
EMPTY_MESSAGE = "Choose at least one tool to remove or add."
# NEW copy, for the advisor.
NOTHING_AFFECTED_MESSAGE = (
    "Every technique the last confirmed assessment scored already has in place what "
    "you chose under What it does, so there is nothing to re-assess."
)


def _unknown_tool_message(name: str) -> str:
    return f"{name} is not a tool this assessment cites. Pick it from the list."


# Slice C, approved 18:32Z with copy C1-C9.
CHAT_EMPTY_MESSAGE = "Describe the change first."
CHAT_TOO_LONG_MESSAGE = f"Keep the description to {scenario.MAX_CHAT} characters or fewer."


def _not_understood_message(item: scenario.NotUnderstood, *, cited: Iterable[str]) -> str:
    """C5 for a clause the matcher will not guess at; B4 (or B4b) where an add
    phrase named one of the client's tools, as the plan says."""
    if item.reason == "already_clients" and item.name is not None:
        return _added_refusal(scenario.AlreadyClients(item.name), cited=cited)[1]
    return f'Not understood: "{item.text}". Pick the tool from the list instead.'


def _client_tools(db: Session, client: Client, cited: Iterable[str]) -> list[str]:
    """The client's tools an added name may not be: every tool on the
    client's capability lists, offered or withheld, and every cited one."""
    membership = _client_capability_membership(db, client.id)
    return [
        *(p.capability.name for p in membership.sent),
        *(w.name for w in membership.withheld),
        *cited,
    ]


def _added_refusal(exc: Exception, *, cited: Iterable[str]) -> tuple[str, str]:
    """An added tool's refusal as (reason, message): B4-B7, approved at
    14:58Z, and the plan's malformed cases."""
    if isinstance(exc, scenario.TooMany):
        return "scenario_too_many_added", f"A what-if can add up to {exc.limit} tools."
    name = getattr(exc, "name", "")
    if isinstance(exc, scenario.AlreadyClients):
        # B4 names "Tools to remove", a control that lists only the tools the
        # base CITES. A client tool the base does not cite is not there, so it
        # is refused without that clause (NEW copy, B4b).
        if scenario.cited_key(name) in {scenario.cited_key(c) for c in cited}:
            return (
                "scenario_added_tool_is_clients",
                f"{name} is already one of the client's tools. Choose it under Tools to "
                "remove, or give the new tool a different name.",
            )
        return (
            "scenario_added_tool_is_clients",
            f"{name} is already one of the client's tools. Give the new tool a different name.",
        )
    if isinstance(exc, scenario.Indistinct):
        return (
            "scenario_added_tool_indistinct",
            f"The AI would be shown {name} under the same name as another tool, so its "
            "credit could not be told apart. Give it a different name.",
        )
    if isinstance(exc, scenario.NoFunctions):
        return (
            "scenario_added_tool_no_functions",
            f"Choose at least one of Detect, Prevent or Respond for {name}.",
        )
    if isinstance(exc, scenario.BadFunction):
        return (
            "scenario_added_tool_bad_function",
            f'What it does for {name} must be Detect, Prevent or Respond, not "{exc.value}".',
        )
    if isinstance(exc, scenario.Duplicate):
        return (
            "scenario_added_tool_duplicate",
            f"{name} is listed twice under Tools to add. Remove one with Remove this tool.",
        )
    if isinstance(exc, scenario.Unprintable):
        # Copy approved by the advisor as written, 00:03Z (#826). The Name case does not echo
        # the name: it is the text holding the character.
        what = "A Name under Tools to add" if exc.field == "Name" else f"{exc.field} for {name}"
        return (
            "scenario_added_tool_unprintable",
            f"{what} contains a line break or another character that cannot be "
            "shown. Retype it.",
        )
    if isinstance(exc, scenario.TooLong):
        return (
            "scenario_added_tool_too_long",
            f"{exc.field} for {name} is longer than {scenario.MAX_TEXT} characters. " "Shorten it.",
        )
    return "scenario_added_tool_no_name", "Give each tool under Tools to add a Name."


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


def _added_tools(s: AttackScenario) -> list[scenario.AddedTool]:
    return [scenario.AddedTool.from_stored(e) for e in s.change_list.get("added") or []]


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
    tools_you_added = _added_tools(s)
    you_added = {t.name.casefold() for t in tools_you_added}
    higher_list, from_added = scenario.split_higher(
        base,
        base_rows,
        _lists_of(rows),
        comparison,
        s.affected_codes,
        added_names=[t.name for t in tools_you_added],
    )
    higher = set(higher_list)
    by_removal = set(
        scenario.affected_codes(
            base_rows,
            scenario.removed_spellings(
                list(s.change_list.get("removed") or []),
                client_org_name=db.get(Client, s.client_id).legal_name,
                redaction_mode=get_settings().shield_redaction_mode,
            ),
        )
    )
    credited_you_added = {
        r.technique_code: sorted(
            {
                a["tool"]
                for a in r.ai_rows
                if str(a.get("tool", "")).casefold() in you_added
                and any(a.get(f) is True for f in ("detection", "prevention", "response"))
            },
            key=str.casefold,
        )
        for r in rows
    }
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
        added=[
            ScenarioAddedTool(
                name=t.name,
                vendor=t.vendor,
                category=t.category,
                security_functions=list(t.functions),
            )
            for t in tools_you_added
        ],
        affected_codes=list(s.affected_codes),
        affected_by_removal=len(by_removal & set(s.affected_codes)),
        affected_by_addition_only=len(set(s.affected_codes) - by_removal),
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
                credited_tool_you_added=bool(credited_you_added.get(code)),
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
                credited_tools_you_added=credited_you_added[r.technique_code],
            )
            for r in rows
        ],
        dropped=s.dropped,
        not_reassessed=s.not_reassessed,
        scored_higher=s.scored_higher,
        higher_with_added=len(from_added) if rows else None,
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
    mode = get_settings().shield_redaction_mode
    cited = scenario.cited_tools(base_rows)
    try:
        removed = scenario.resolve_removed(base_rows, (body.removed if body else None) or [])
    except scenario.UnknownTool as exc:
        raise _refuse(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "scenario_unknown_tool",
            _unknown_tool_message(exc.name),
        ) from exc
    # Slice B. "The client's tools" an added name may not be: every tool on
    # the client's capability lists, offered or withheld, and every tool the
    # base cites.
    client_tools = _client_tools(db, client, cited)
    try:
        added = scenario.validate_added(
            (body.added if body else None) or [],
            client_tools=client_tools,
            client_org_name=client.legal_name,
            redaction_mode=mode,
        )
    except (scenario.AddedToolRefused, scenario.TooMany) as exc:
        reason, message = _added_refusal(exc, cited=cited)
        raise _refuse(status.HTTP_422_UNPROCESSABLE_ENTITY, reason, message) from exc
    try:
        scenario.require_change(removed, added)
    except scenario.EmptyChangeList as exc:
        raise _refuse(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "scenario_empty_change", EMPTY_MESSAGE
        ) from exc
    spellings = scenario.removed_spellings(
        removed, client_org_name=client.legal_name, redaction_mode=mode
    )
    affected = sorted(
        set(scenario.affected_codes(base_rows, spellings))
        | set(scenario.open_functions(base_rows, added, removed=spellings))
    )
    if not affected:
        # Only possible when tools are only ADDED and every technique already
        # has each declared function in place: nothing to ask, nothing to pay
        # for. A removal always affects the techniques that cite it.
        raise _refuse(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "scenario_nothing_affected",
            NOTHING_AFFECTED_MESSAGE,
        )
    s = AttackScenario(
        client_id=client.id,
        service_id=svc.id,
        base_assessment_id=base.id,
        base_version=base.version,
        base_catalog_version=base.catalog_version,
        base_status_rules=base.status_rules,
        change_list={"removed": removed, "added": [t.payload() for t in added]},
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
            "added": len(added),
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


def _llm_builder(db: Annotated[Session, Depends(get_db)]) -> Callable[[], LLMClient]:
    """The provider, built only when called: mitre_map's `_llm_dep`, deferred
    until the run route has made every refusal (#815 review, F4)."""
    return lambda: _llm_dep(db)


@router.post(
    "/services/{service_id}/scenarios/parse",
    response_model=ScenarioParseResponse,
    summary="Propose a what-if's change list from a description (admin)",
)
def parse_scenario_text(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
    build_llm: Annotated[Callable[[], LLMClient], Depends(_llm_builder)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    body: ScenarioParseRequest | None = None,
) -> ScenarioParseResponse:
    """The chat box. The slice C matcher (`scenario.parse_change`) reads the
    text first; where it leaves something not understood, the AI may be asked
    (`_ai_reading`, #802). Either way the result is a PROPOSED change list that
    pre-fills the picker: nothing is stored or run.

    The matcher path writes nothing. An AI attempt writes only its own
    `llm_calls` row (in `invoke`) and a counts-only audit entry. The text itself
    is never logged; only the counts are."""
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.ATTACK_COVERAGE)
    base = scenario.confirmed_base(db, svc.id)
    if base is None:
        raise _refuse(
            status.HTTP_409_CONFLICT, "scenario_needs_confirmed_assessment", NEEDS_CONFIRMED_MESSAGE
        )
    text = body.text if body else None
    if not isinstance(text, str) or not text.strip():
        raise _refuse(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "scenario_chat_empty", CHAT_EMPTY_MESSAGE
        )
    if len(text) > scenario.MAX_CHAT:
        raise _refuse(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "scenario_chat_too_long", CHAT_TOO_LONG_MESSAGE
        )
    serves = require_serves(body.serves) if body and body.serves is not None else None
    cited = scenario.cited_tools(_base_rows(db, base.id))
    client_tools = _client_tools(db, client, cited)
    mode = get_settings().shield_redaction_mode
    parsed = scenario.parse_change(
        text,
        cited=cited,
        client_tools=client_tools,
        client_org_name=client.legal_name,
        redaction_mode=mode,
    )
    source, note = "matcher", None
    understood = not parsed.not_understood and bool(parsed.removed or parsed.added)
    if not understood and serves == "live" and scenario_intent.available():
        reading, note = _ai_reading(
            db,
            build_llm,
            limiter,
            user=user,
            client=client,
            service_id=svc.id,
            text=text,
            cited=cited,
            client_tools=client_tools,
            mode=mode,
        )
        if reading is not None:
            parsed, source = reading, "ai"
    _log.info(
        "attack.scenario.chat_parsed",
        service_id=str(svc.id),
        source=source,
        fell_back=note is not None,
        removed=len(parsed.removed),
        added=len(parsed.added),
        not_understood=len(parsed.not_understood),
    )
    return ScenarioParseResponse(
        removed=parsed.removed,
        added=parsed.added,
        not_understood=[
            ScenarioNotUnderstood(
                text=n.text, reason=n.reason, message=_not_understood_message(n, cited=cited)
            )
            for n in parsed.not_understood
        ],
        source=source,
        note=note,
    )


def _attempt_call_id(db: Session, *, service_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
    """The id of the `llm_calls` row this attempt wrote, or None.

    QUERIED by purpose, service, requester and the request's correlation id.
    The query sees this attempt's row (`invoke` adds and flushes it before the
    provider is called, and marks it FAILED on an error) and also any earlier
    COMMITTED row under the same id: a parse makes at most one attempt, but a
    client may send an `X-Request-ID` again. More than one match is therefore
    possible, and is reported as unknown rather than guessed. Not read from the
    session's identity map, which holds a clean row only weakly; on a failure it
    was gone once the exception was (#863 review, round 2)."""
    correlation = correlation_id_var.get()
    if correlation is None:
        return None
    ids = list(
        db.execute(
            select(LLMCall.id).where(
                LLMCall.purpose == scenario_intent.PURPOSE,
                LLMCall.service_id == service_id,
                LLMCall.requested_by == user_id,
                LLMCall.correlation_id == correlation,
            )
        ).scalars()
    )
    return str(ids[0]) if len(ids) == 1 else None


#: N2, approved by the advisor verbatim (16:40Z, #802 comment 5982109105).
AI_FALLBACK_NOTE = (
    "The AI could not read your description just now, so only the tools named exactly "
    "as listed were filled in."
)


def _ai_reading(
    db: Session,
    build_llm: Callable[[], LLMClient],
    limiter: RateLimiter,
    *,
    user: User,
    client: Client,
    service_id: uuid.UUID,
    text: str,
    cited: list[str],
    client_tools: list[str],
    mode: Any,
) -> tuple[scenario.ParsedChange | None, str | None]:
    """The AI's reading, checked, or None with N2 when it could not be used.

    Called only when the page acknowledged "live" and the purpose is released.
    A provider that is not live (the fixture) is not asked and says nothing: a
    canned answer is no reading of the text. The rate limit is taken here, so a
    parse the matcher answered spends nothing."""
    llm = build_llm()
    if provider_serves(llm) != "live":
        return None, None
    try:
        limiter.enforce_ai(client.id)
    except HTTPException as exc:
        if exc.status_code != status.HTTP_429_TOO_MANY_REQUESTS:
            raise
        _log.info("attack.scenario.chat_ai_rate_limited", service_id=str(service_id))
        return None, AI_FALLBACK_NOTE
    # The tenant's user names are a name dictionary for the redactor, as Tech
    # Debt's extraction uses them: a colleague named in the description is
    # sent as [NAME] (#863 review, F1). The SAME hints go to the sent text,
    # the call and the reading, so condition 1 checks what was sent.
    hints = name_hints_for_tenant(db, client.id)
    sent = scenario_intent.sent_description(
        text,
        cited,
        redaction_mode=mode,
        client_org_name=client.legal_name,
        name_hints=hints,
    )
    reading: scenario.ParsedChange | None = None
    failure: str | None = None
    try:
        result = run_job(
            db,
            llm,
            scenario_intent.PURPOSE,
            inputs=scenario_intent.payload(text, cited),
            requested_by=user.id,
            service_id=service_id,
            client_id=client.id,
            client_org_name=client.legal_name,
            name_hints=hints,
        )
        reading = scenario_intent.read(
            result.data,
            sent=sent,
            cited=cited,
            client_tools=client_tools,
            client_org_name=client.legal_name,
            redaction_mode=mode,
            name_hints=hints,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - recorded below and disclosed as N2
        failure = type(exc).__name__
        _log.warning(
            "attack.scenario.chat_ai_unusable",
            service_id=str(service_id),
            error=f"{type(exc).__name__}: {exc}",
        )
    call_id = _attempt_call_id(db, service_id=service_id, user_id=user.id)
    if call_id is None:
        # Loud, never a silent null: this entry cannot name the attempt's
        # llm_calls row. There may be none (a failure before `invoke` wrote it)
        # or more than one under this correlation id (a reused X-Request-ID).
        # Recorded in its own key, so `failure` keeps the attempt's own outcome
        # (#863 review, round 3). Not raised: that would turn a disclosed
        # fallback into a 500 over a bookkeeping gap.
        _log.error(
            "attack.scenario.chat_ai_call_row_unknown",
            service_id=str(service_id),
            failure=failure,
        )
    # Counts only: the text and the tool names are the client's data.
    audit(
        db,
        action="attack.scenario.chat_ai_parse",
        target_type="service",
        target_id=service_id,
        actor_user_id=user.id,
        details={
            "llm_call_id": call_id,
            "fell_back": reading is None,
            "failure": failure,
            "call_row": "found" if call_id is not None else "unknown",
            "removed": len(reading.removed) if reading else 0,
            "added": len(reading.added) if reading else 0,
            "not_understood": len(reading.not_understood) if reading else 0,
        },
    )
    # The llm_calls row `invoke` wrote (COMPLETED or FAILED) and this entry are
    # the evidence of the attempt; a rollback at the end of the request would
    # lose them.
    db.commit()
    return reading, (None if reading is not None else AI_FALLBACK_NOTE)


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
                added=[t.name for t in _added_tools(s)],
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


def _added_collision(db: Session, s: AttackScenario, client: Client) -> str | None:
    """The first tool the admin added that can no longer be told apart from
    the client's CURRENT tools, or None. The client's list can gain a tool
    after the what-if was created; every credit to either would then be
    dropped as outside the change, so the run must not happen (#818 review,
    F4). Decided by the same validation creation ran, against today's tools."""
    added = _added_tools(s)
    if not added:
        return None
    base_rows = _base_rows(db, s.base_assessment_id)
    membership = _client_capability_membership(db, client.id)
    current = [
        *(p.capability.name for p in membership.sent),
        *(w.name for w in membership.withheld),
        *scenario.cited_tools(base_rows),
    ]
    try:
        scenario.validate_added(
            [t.payload() for t in added],
            client_tools=current,
            client_org_name=client.legal_name,
            redaction_mode=get_settings().shield_redaction_mode,
            # A stored row's characters are not a collision: a draft stored
            # before #826 may hold a line feed (only NUL failed to insert),
            # and calling it one gave a false message (#831 review, F1).
            check_characters=False,
        )
    except (scenario.AlreadyClients, scenario.Indistinct, scenario.Duplicate) as exc:
        # ONLY the collision refusals. The others check a field's own
        # content, which creation already checked and nothing has changed
        # since; one here would be a new rule meeting an old row, and it
        # raises rather than being reported as a collision it is not.
        return exc.name
    return None


def _collision_message(name: str) -> str:
    # NEW copy, for the advisor. "Start a new what-if" is the panel's control.
    return (
        f"{name}, a tool you added, can no longer be told apart from one of the client's "
        "tools, so this what-if cannot be analysed. Start a new what-if."
    )


def _refuse_if_added_collides(db: Session, s: AttackScenario, client: Client) -> None:
    name = _added_collision(db, s, client)
    if name is not None:
        raise _refuse(
            status.HTTP_409_CONFLICT, "scenario_added_tool_collides", _collision_message(name)
        )


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
    _refuse_if_added_collides(db, s, client)
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
    # F4 again, in the job: the list can change between the POST and now.
    collides = _added_collision(db, s, client)
    if collides is not None:
        raise RunFailed("scenario_added_tool_collides", _collision_message(collides))
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
                AuditEntry.action == SECURITY_CLASSIFICATION_OVERRIDDEN,
                AuditEntry.target_type == "capability_item",
                AuditEntry.target_id.in_(item_ids),
            )
            .group_by(AuditEntry.target_id)
        ).all()
    }
    added = scenario.tools_added_since(
        kept_offers, membership.lists, created, base.approved_at, overridden
    )
    # Slice B: the admin's added tools are offered beside the client's and
    # may be credited, but they are NOT the client's list: the drift check
    # above judges only `membership`, so they never read as drift.
    tools_you_added = _added_tools(s)
    inputs = scenario.batch_inputs(
        base_rows,
        affected,
        spellings,
        _capability_payload(kept),
        size=scenario.BATCH_SIZE,
        added=tools_you_added,
    )
    remaining = [Candidate(name=c.name, vendor=c.vendor) for c in kept] + [
        Candidate(name=t.name, vendor=t.vendor) for t in tools_you_added
    ]
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
                opened=inputs[i]["open_functions"],
                added=tools_you_added,
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
    # Copy 18 counts only rises credited to a REMAINING tool; a rise from a
    # tool the admin added is B11's result, derived at the GET.
    higher, _from_added = scenario.split_higher(
        base,
        base_rows,
        merged.lists,
        comparison,
        affected,
        added_names=[t.name for t in tools_you_added],
    )
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
