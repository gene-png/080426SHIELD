"""#1120 "Start a revision" (Option A, revision only).

An APPROVED or RELEASED record is never edited in place. A revision mints the
next version as a DRAFT, copies the prior version's values, notes and
consultant edits forward, and leaves the prior version and its deliverables
untouched. Design: the #1120 note rev 10, ruled by the advisor
(#736 6136101129).

Three parts, each its own function:

* `decide_revision` -- the ordered rules (note, section 3), evaluated from the
  record, its newest newer record and the service. NOT a table lookup: the
  reviewed expectation table lives in the tests, and the test asserts the two
  agree for every element of the enum product.
* `copy_forward` -- the model-driven copier: every column is copied except a
  per-table `NOT_CARRIED` set, each entry with its reason (note, section 4).
* `start_revision` -- the route body shared by ATT&CK, CSF and ZT.

The database is the guard, not the pre-check: `uq_<table>_one_draft`
(migration 0073) refuses a second draft, and a race that loses to it answers
V6 with the draft that won.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.runs import refuse_while_running
from app.audit import audit
from app.logging import get_logger
from app.models.attack_assessment import AttackAssessment, AttackAssessmentStatus
from app.models.capability import CapabilityList, CapabilityListStatus
from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus
from app.models.evidence_link import EvidenceLink, EvidenceTargetKind
from app.models.service import Service, ServiceKind, ServiceStatus
from app.models.user import User, UserRole
from app.models.zt_assessment import ZtAssessment, ZtAssessmentStatus
from app.services.revision_copy import COPY

_log = get_logger(__name__)

#: The record model and its status enum, per service kind. The test asserts
#: the keys equal `set(ServiceKind)`, so a new kind is red until it has rows.
KIND_RECORDS: dict[ServiceKind, tuple[type, type]] = {
    ServiceKind.ATTACK_COVERAGE: (AttackAssessment, AttackAssessmentStatus),
    ServiceKind.NIST_CSF: (CsfAssessment, CsfAssessmentStatus),
    ServiceKind.ZERO_TRUST_CISA: (ZtAssessment, ZtAssessmentStatus),
    ServiceKind.ZERO_TRUST_DOD: (ZtAssessment, ZtAssessmentStatus),
    ServiceKind.TECH_DEBT: (CapabilityList, CapabilityListStatus),
}

#: "none" when no newer non-discarded record exists.
NO_NEWER = "none"


@dataclass(frozen=True)
class Decision:
    """`allow` is True, or `reason` and `copy` name the typed 409."""

    allow: bool
    reason: str = ""
    copy: str = ""


ALLOW = Decision(allow=True)


def decide_revision(
    *,
    kind: ServiceKind,
    target_status: str,
    newer_status: str,
    archived: bool,
) -> Decision:
    """The ordered rules (note rev 10, section 3, plus Q14's X2); first match
    wins. Statuses are the enum VALUES (`"draft"`, ...); `newer_status` is the
    newest newer non-discarded record's, or `NO_NEWER`."""
    # 0. I1: a DRAFT is always the latest record. Logged by the caller.
    if target_status == "draft" and newer_status != NO_NEWER:
        return Decision(False, "state_invalid", "X0")
    # Q14 (advisor: yes): an archived service is not revised.
    if archived:
        return Decision(False, "service_archived", "X2")
    if target_status == "discarded":
        reason = (
            "capability_list_discarded" if kind == ServiceKind.TECH_DEBT else "assessment_discarded"
        )
        return Decision(False, reason, "X1")
    if newer_status == "draft":
        return Decision(False, "draft_open", "V6")
    if newer_status != NO_NEWER:
        return Decision(False, "not_latest", "V12")
    if target_status == "draft":
        return Decision(False, "draft_open", "V8")
    if target_status == "submitted":
        return Decision(False, "submitted_awaiting_review", "V10")
    if target_status in ("approved", "released"):
        return ALLOW
    # Any status the rules do not name fails closed.
    return Decision(False, "state_invalid", "X0")


# ---------------------------------------------------------------------------
# What is carried (note, section 4)
# ---------------------------------------------------------------------------

#: Columns of EVERY carried table that are never copied: the row's identity.
_IDENTITY = {"id": "a new row", "created_at": "the copy's own", "updated_at": "the copy's own"}

#: The record tables: what a new version starts with.
RECORD_NOT_CARRIED: dict[str, dict[str, str]] = {
    "attack_assessments": {
        **_IDENTITY,
        "version": "the next version",
        "status": "a revision starts as DRAFT",
        "approved_at": "not approved yet",
        "approved_by": "not approved yet",
        "documents_stale": "no documents yet",
        "revision_of": "set to the source record",
        "catalog_version": "the CURRENT catalog (ruling item 4)",
        "parent_rules": "NULL = the current rules (ruling item 4)",
        "status_rules": "NULL = the current rules (ruling item 4)",
    },
    "csf_assessments": {
        **_IDENTITY,
        "version": "the next version",
        "status": "a revision starts as DRAFT",
        "approved_at": "not approved yet",
        "approved_by": "not approved yet",
        "documents_stale": "no documents yet",
        "revision_of": "set to the source record",
    },
    "zt_assessments": {
        **_IDENTITY,
        "version": "the next version",
        "status": "a revision starts as DRAFT",
        "approved_at": "not approved yet",
        "approved_by": "not approved yet",
        "documents_stale": "no documents yet",
        "revision_of": "set to the source record",
    },
}

#: The child tables, keyed on the column naming the record.
_CHILD = {**_IDENTITY, "assessment_id": "remapped to the new record"}
CHILD_NOT_CARRIED: dict[str, dict[str, str]] = {
    "attack_coverage": dict(_CHILD),
    "csf_answers": dict(_CHILD),
    "csf_dimension_scores": {
        **_CHILD,
        "evidence_basis": "the Q9 manual-tick grace is the source's; the EV-1 rule applies",
    },
    "csf_gap_actions": dict(_CHILD),
    "zt_answers": dict(_CHILD),
    "evidence_links": dict(_CHILD),
}


def _copy_columns(row: Any, not_carried: dict[str, str]) -> dict[str, Any]:
    table = row.__table__
    return {c.key: getattr(row, c.key) for c in table.columns if c.key not in not_carried}


@dataclass
class ChildSpec:
    """One child table of a record: its model, the column holding its code
    (None when every row is copied as it is), and the extra filter."""

    model: type
    code_attr: str | None = None
    where: Callable[[Any], Any] | None = None


@dataclass
class CopyResult:
    record: Any
    dropped_codes: list[str] = field(default_factory=list)


def copy_forward(
    db: Session,
    *,
    source: Any,
    record_values: dict[str, Any],
    children: Iterable[ChildSpec],
    current_codes: frozenset[str] | None = None,
    blank_row: Callable[[Any, str], Any] | None = None,
    code_child: type | None = None,
    drop_retired: bool = False,
) -> CopyResult:
    """Insert the new record and copy every carried child row.

    `current_codes` / `code_child` / `blank_row` apply the CURRENT catalog to
    the one coded child table (ATT&CK coverage, CSF answers, ZT answers): a
    code new to the catalog gets a blank row, as `create_assessment` would
    give it. With `drop_retired` (ATT&CK, note section 3), a row whose code
    left the catalog is not copied and is returned in `dropped_codes` for V4;
    CSF and ZT keep retired rows, as their catalog migrations (0063-0065) do.
    Raises `IntegrityError` when the one-draft index refuses the record; the
    caller answers V6."""
    model = type(source)
    values = _copy_columns(source, RECORD_NOT_CARRIED[model.__tablename__])
    values.update(record_values)
    record = model(**values)
    db.add(record)
    db.flush()

    dropped: set[str] = set()
    seen_codes: set[str] = set()
    for spec in children:
        not_carried = CHILD_NOT_CARRIED[spec.model.__tablename__]
        q = select(spec.model).where(spec.model.assessment_id == source.id)
        if spec.where is not None:
            q = q.where(spec.where(spec.model))
        for row in db.execute(q).scalars():
            code = getattr(row, spec.code_attr) if spec.code_attr else None
            if drop_retired and code is not None and code not in (current_codes or frozenset()):
                dropped.add(code)
                continue
            if spec.model is code_child and code is not None:
                seen_codes.add(code)
            data = _copy_columns(row, not_carried)
            data["assessment_id"] = record.id
            db.add(spec.model(**data))
    if current_codes is not None and blank_row is not None:
        for code in sorted(current_codes - seen_codes):
            db.add(blank_row(record, code))
    db.flush()
    return CopyResult(record=record, dropped_codes=sorted(dropped))


# ---------------------------------------------------------------------------
# The route body
# ---------------------------------------------------------------------------


def _newest_newer(db: Session, model: type, target: Any) -> Any | None:
    discarded = model.status.type.enum_class.DISCARDED
    return (
        db.execute(
            select(model)
            .where(
                model.service_id == target.service_id,
                model.version > target.version,
                model.status != discarded,
            )
            .order_by(model.version.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def _open_draft(db: Session, model: type, service_id: uuid.UUID) -> Any | None:
    draft = model.status.type.enum_class.DRAFT
    return (
        db.execute(select(model).where(model.service_id == service_id, model.status == draft))
        .scalars()
        .first()
    )


def _refuse(decision: Decision, *, v: int, n: int | None) -> HTTPException:
    message = COPY[decision.copy].format(v=v, n=n if n is not None else "")
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"reason": decision.reason, "message": message},
    )


@dataclass
class KindPlan:
    """What differs per service kind when a revision starts."""

    audit_prefix: str
    children: list[ChildSpec]
    record_values: dict[str, Any] = field(default_factory=dict)
    current_codes: frozenset[str] | None = None
    code_child: type | None = None
    blank_row: Callable[[Any, str], Any] | None = None
    drop_retired: bool = False


def start_revision(
    db: Session,
    *,
    svc: Service,
    target: Any,
    user: User,
    reason: str,
    plan: KindPlan,
) -> CopyResult:
    """Decide, copy, audit and commit. Raises the typed 409 for every refusal."""
    model = type(target)
    refuse_while_running(db, svc.id)  # #645: no revision while a run writes
    newer = _newest_newer(db, model, target)
    decision = decide_revision(
        kind=svc.kind,
        target_status=target.status.value,
        newer_status=newer.status.value if newer is not None else NO_NEWER,
        archived=svc.status == ServiceStatus.ARCHIVED,
    )
    if not decision.allow:
        log = _log.error if decision.reason == "state_invalid" else _log.info
        log(
            "revision_refused",
            service_id=str(svc.id),
            target_id=str(target.id),
            target_version=target.version,
            target_status=target.status.value,
            newer_version=newer.version if newer is not None else None,
            reason=decision.reason,
        )
        raise _refuse(decision, v=target.version, n=newer.version if newer else None)

    max_version = db.execute(
        select(func.max(model.version)).where(model.service_id == svc.id)
    ).scalar_one()
    draft_status = model.status.type.enum_class.DRAFT
    values = {
        "version": (max_version or 0) + 1,
        "status": draft_status,
        "revision_of": target.id,
        **plan.record_values,
    }
    try:
        result = copy_forward(
            db,
            source=target,
            record_values=values,
            children=plan.children,
            current_codes=plan.current_codes,
            blank_row=plan.blank_row,
            code_child=plan.code_child,
            drop_retired=plan.drop_retired,
        )
    except IntegrityError as exc:
        # The one-draft index (or the version constraint) refused: a draft
        # was opened after the pre-check. Answer V6, naming that draft.
        db.rollback()
        winner = _open_draft(db, model, svc.id)
        if winner is None:
            raise
        _log.info(
            "revision_lost_race",
            service_id=str(svc.id),
            target_id=str(target.id),
            winner_version=winner.version,
        )
        raise _refuse(
            Decision(False, "draft_open", "V6"), v=target.version, n=winner.version
        ) from exc

    record = result.record
    audit(
        db,
        action=f"{plan.audit_prefix}.revision_started",
        target_type=model.__tablename__.rstrip("s"),
        target_id=record.id,
        actor_user_id=user.id,
        details={
            "service_id": str(svc.id),
            "from_id": str(target.id),
            "from_version": target.version,
            "to_version": record.version,
            "reason": reason,
            "from_rules": {
                k: getattr(target, k)
                for k in ("parent_rules", "status_rules")
                if hasattr(target, k)
            },
            **(
                {
                    "from_catalog_version": target.catalog_version,
                    "retired_codes": result.dropped_codes,
                }
                if hasattr(target, "catalog_version")
                else {}
            ),
        },
    )
    db.commit()
    db.refresh(record)
    _log.info(
        "revision_started",
        service_id=str(svc.id),
        from_version=target.version,
        to_version=record.version,
        retired_codes=len(result.dropped_codes),
    )
    return result


def is_revision_draft(record: Any) -> bool:
    """A DRAFT minted by "Start a revision": the consultant's, not the client's."""
    return record.status.value == "draft" and getattr(record, "revision_of", None) is not None


def client_facing(db: Session, record: Any, user: User) -> Any:
    """What a NON-ADMIN caller is shown in place of `record` (the client
    doors, note section 2): a revision draft reads as the record it revises.
    An admin, and every other record, read as they are."""
    if user.role == UserRole.ADMIN or not is_revision_draft(record):
        return record
    source = db.get(type(record), record.revision_of)
    if source is None:  # ON DELETE SET NULL makes this unreachable; fail closed
        raise RuntimeError(f"revision {record.id} names a missing source {record.revision_of}")
    return source


def evidence_links_for(kind: EvidenceTargetKind) -> ChildSpec:
    """The polymorphic evidence links of one record (no FK; keyed on
    `assessment_id` and the target kind)."""
    return ChildSpec(
        model=EvidenceLink,
        code_attr="target_code",
        where=lambda m: m.target_kind == kind,
    )
