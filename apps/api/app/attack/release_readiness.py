"""What keeps an ATT&CK assessment from being released (#622, #554 c3b).

D-092's release blocker, at the scope recorded on #622 on 2026-09-26 (#557's
gap dispositions stay post-MVP and are added when #557 is built):

* **Not verified** -- any row whose status is `unable_to_determine`. The
  threshold is zero and there is no override. A computed parent with a Not
  verified child is Not verified itself (D-094), so it is listed too.
* **A Partial with no reason** -- a `partial` row with no `reason_code`, under
  #620's rules only. There, a COMPUTED parent is judged through its children
  (D-094: "the release-readiness gate must read a computed parent's children,
  not demand a Partial reason of the parent"), so it is exempt and its children
  are held to the same predicate. An assessment approved before #620 predates
  reason codes, so none of its Partials carries one; holding it to the clause
  would refuse every such release, with nothing able to clear it (an approved
  assessment is locked).

ONE predicate, two forms: `blocking_condition` for the SQL that joins the
release flip's WHERE (`deliverable_release.ParentGuard`), and `blocking_rows`
for the Python that names the codes in a refusal and gates approve. Both read
`_is_blocking` / `_blocking_sql`, which state the same two clauses; the tests
drive both through the routes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.attack.coverage import CoverageStatus
from app.attack.parents import PARENT_CHILDREN
from app.attack.rules import parents_computed
from app.logging import get_logger
from app.models.attack_assessment import AttackAssessment, AttackCoverage

_log = get_logger(__name__)

_NOT_VERIFIED = CoverageStatus.UNABLE_TO_DETERMINE.value
_PARTIAL = CoverageStatus.PARTIAL.value
#: Codes the refusal names before it says "and N more".
_NAMED = 10


@dataclass(frozen=True)
class BlockingRows:
    not_verified: tuple[str, ...]
    partial_without_reason: tuple[str, ...]

    def __bool__(self) -> bool:
        return bool(self.not_verified or self.partial_without_reason)


def _is_blocking(row: AttackCoverage, *, new_rules: bool) -> tuple[bool, bool]:
    """(not verified, a Partial with no reason) for one row."""
    not_verified = row.status == _NOT_VERIFIED
    reasonless = (
        new_rules
        and row.status == _PARTIAL
        and row.reason_code is None
        and row.technique_code not in PARENT_CHILDREN
    )
    return not_verified, reasonless


def _blocking_sql(assessment_id: uuid.UUID, *, new_rules: bool) -> ColumnElement[bool]:
    clauses = [AttackCoverage.status == _NOT_VERIFIED]
    if new_rules:
        clauses.append(
            and_(
                AttackCoverage.status == _PARTIAL,
                AttackCoverage.reason_code.is_(None),
                AttackCoverage.technique_code.not_in(list(PARENT_CHILDREN)),
            )
        )
    return and_(AttackCoverage.assessment_id == assessment_id, or_(*clauses))


def blocking_rows(db: Session, assessment: AttackAssessment) -> BlockingRows:
    new_rules = parents_computed(assessment)
    not_verified: list[str] = []
    reasonless: list[str] = []
    for row in (
        db.execute(select(AttackCoverage).where(AttackCoverage.assessment_id == assessment.id))
        .scalars()
        .all()
    ):
        nv, rl = _is_blocking(row, new_rules=new_rules)
        if nv:
            not_verified.append(row.technique_code)
        if rl:
            reasonless.append(row.technique_code)
    found = BlockingRows(tuple(sorted(not_verified)), tuple(sorted(reasonless)))
    _log.info(
        "attack.release_readiness.checked",
        assessment_id=str(assessment.id),
        new_rules=new_rules,
        not_verified=len(found.not_verified),
        partial_without_reason=len(found.partial_without_reason),
    )
    return found


def blocking_condition(db: Session) -> object:
    """The `condition` for `deliverable_release.ParentGuard`: NOT EXISTS any
    blocking row, with the rule set read through `attack/rules.py` for the
    parent being flipped."""

    def condition(assessment_id: uuid.UUID) -> ColumnElement[bool]:
        a = db.get(AttackAssessment, assessment_id)
        if a is None:  # the flip's own WHERE would match nothing either
            raise RuntimeError(f"ATT&CK assessment {assessment_id} vanished mid-release")
        new_rules = parents_computed(a)
        return ~select(AttackCoverage.id).where(_blocking_sql(a.id, new_rules=new_rules)).exists()

    return condition


def _codes(codes: tuple[str, ...]) -> str:
    shown = ", ".join(codes[:_NAMED])
    more = len(codes) - _NAMED
    return shown if more <= 0 else f"{shown} and {more} more"


def _what(found: BlockingRows) -> str:
    parts = []
    if found.not_verified:
        n = len(found.not_verified)
        parts.append(
            f"{n} {'technique is' if n == 1 else 'techniques are'} Not verified "
            f"({_codes(found.not_verified)})"
        )
    if found.partial_without_reason:
        n = len(found.partial_without_reason)
        parts.append(
            f"{n} Partial {'technique has' if n == 1 else 'techniques have'} no reason "
            f"({_codes(found.partial_without_reason)})"
        )
    return " and ".join(parts)


def refuse_approve(found: BlockingRows) -> HTTPException:
    """At approve the draft is still editable, so the remedy is a control that
    exists: the technique panel's Reason select. Not verified has no writer
    yet (`coverage.WRITABLE`), so it carries no imperative."""
    remedy = (
        " Choose a reason for each Partial technique in its panel, then approve again."
        if found.partial_without_reason
        else ""
    )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "reason": "attack_not_release_ready",
            "message": f"This assessment cannot be approved: {_what(found)}.{remedy}",
            "not_verified": list(found.not_verified),
            "partial_without_reason": list(found.partial_without_reason),
        },
    )


def refuse_release(db: Session, assessment_id: uuid.UUID) -> HTTPException:
    """The release flip missed while the parent was still APPROVED. An approved
    assessment is locked, so there is no fix-it step to name: it says what
    blocks the release and that nothing was released."""
    a = db.get(AttackAssessment, assessment_id)
    found = blocking_rows(db, a) if a is not None else BlockingRows((), ())
    if not found:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "attack_assessment_changed_during_release",
                "message": (
                    "The assessment changed while the deliverable was being released, so "
                    "nothing was released. Reload the page and release again."
                ),
            },
        )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "reason": "attack_not_release_ready",
            "message": f"Nothing was released: {_what(found)}.",
            "not_verified": list(found.not_verified),
            "partial_without_reason": list(found.partial_without_reason),
        },
    )


__all__ = [
    "BlockingRows",
    "blocking_condition",
    "blocking_rows",
    "refuse_approve",
    "refuse_release",
]
