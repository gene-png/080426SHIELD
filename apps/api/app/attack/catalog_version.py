"""Refuse to compute, change or publish an assessment scored against a different catalog (#556).

An assessment's coverage rows are keyed by technique code and pre-seeded from
whatever catalog existed when it was created. The catalog is now generated from
MITRE's STIX (D-091), and the list it replaced matched no ATT&CK version, so an
older assessment holds codes the catalog no longer has and lacks rows for
techniques it never saw. The readers used to DROP unknown codes silently
(`if r.technique_code in valid`), which after a catalog change reports a
percentage over an undisclosed, mixed set.

THREE STATES, for every site that calls this:
  * `catalog_version == SOURCE_VERSION`: current; proceed.
  * a different recorded version: refuse, naming both versions.
  * NULL, i.e. created before migration 0052: refuse. The catalog it was scored
    against was never recorded, and missing data defaults to unconfirmed.

WHERE IT IS CALLED, and so what "refused" covers. Not every reader: every
reader that COMPUTES a number from coverage rows, CHANGES them, or PUBLISHES
them. In routes/attack.py: coverage PATCH, confirm-citations, the AI request
builder, the heatmap, approve, finalize, and a FIRST release. Re-releasing an
already-released deliverable is not guarded: it is `release_deliverable`'s
idempotent repair path and publishes nothing new; a stale one is instead
withheld from the client, below. In routes/clients.py: the client dashboard
(`require_current_catalog_for_client`) and the value-summary card (which
reports the kind unresolved, and withheld, via `is_current`). In routes/risk.py:
risk synthesis, and the gate that offers it, through the same sentence
(`catalog_mismatch_message`).
A document already RELEASED over a stale assessment is withheld from the client
by `is_stale_attack_deliverable`: in the deliverable list (routes/clients.py),
the file download (routes/artifacts.py, typed), and the admin deliverables page,
which counts it as not visible to the client (routes/admin.py). A Risk Register
built from one is withheld from the client dashboard by `is_stale_risk_register`.
Readers that neither compute nor
publish -- the assessment GET, which reports `catalog_current`, and the discard
summary's row count -- are deliberately unguarded.

The consultant message names only controls that exist (D-076): "Discard draft"
and "Start assessment", and "Start assessment" only when discarding would leave
NO assessment. An approved or released assessment has no control that starts a
new version (#558), so for it, and for a draft that sits on top of one, the
message states the fact and names no action.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.attack.catalog import SOURCE_VERSION
from app.models.attack_assessment import AttackAssessment, AttackAssessmentStatus
from app.models.deliverable import Deliverable
from app.models.service import Service, ServiceKind

REASON = "attack_catalog_mismatch"


def is_current(assessment: AttackAssessment) -> bool:
    return assessment.catalog_version == SOURCE_VERSION


def _scored_against(assessment: AttackAssessment) -> str:
    if assessment.catalog_version is None:
        return "an ATT&CK catalog that was never recorded"
    return f"ATT&CK v{assessment.catalog_version}"


def _has_earlier_version(db: Session, assessment: AttackAssessment) -> bool:
    """Would discarding this draft leave an earlier assessment behind?"""
    earlier = db.execute(
        select(AttackAssessment.id)
        .where(
            AttackAssessment.service_id == assessment.service_id,
            AttackAssessment.version < assessment.version,
            AttackAssessment.status != AttackAssessmentStatus.DISCARDED,
        )
        .limit(1)
    ).first()
    return earlier is not None


def require_current_catalog(db: Session, assessment: AttackAssessment) -> None:
    """Consultant-facing refusal (typed 409) for an assessment on another catalog."""
    message = catalog_mismatch_message(db, assessment)
    if message is None:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"reason": REASON, "message": message},
    )


def catalog_mismatch_message(db: Session, assessment: AttackAssessment) -> str | None:
    """The consultant sentence for a stale assessment, or None when it is current.

    Shared by the refusal above and by any surface that must say the same thing
    BEFORE a refusal is reached (the Risk Register gate), so the two cannot drift.
    """
    if is_current(assessment):
        return None
    message = (
        f"This assessment was scored against {_scored_against(assessment)}, not the "
        f"current ATT&CK v{SOURCE_VERSION} catalog, so its coverage cannot be computed, "
        "changed or published."
    )
    if assessment.status == AttackAssessmentStatus.DRAFT and not _has_earlier_version(
        db, assessment
    ):
        message += (
            f" Discard the draft and start a new assessment to score it against "
            f"v{SOURCE_VERSION}."
        )
    else:
        message += (
            " It cannot be rescored from the workspace yet: there is no control that "
            "starts a new version after an assessment has been approved."
        )
    return message


def attack_parent(db: Session, deliv: Deliverable) -> AttackAssessment | None:
    """The ATT&CK assessment `deliv` was built from, or None when it cannot be
    traced (NULL `parent_version`, finalized before 0041, or no such row)."""
    if deliv.parent_version is None:
        return None
    return db.execute(
        select(AttackAssessment).where(
            AttackAssessment.service_id == deliv.service_id,
            AttackAssessment.version == deliv.parent_version,
        )
    ).scalar_one_or_none()


def is_stale_attack_deliverable(db: Session, deliv: Deliverable) -> bool:
    """An ATT&CK deliverable whose assessment is untraceable or on another catalog.

    ONE predicate for every client path to a released document: the list
    (`routes/clients.py`, which withholds the summary and files and says why)
    and the file download (`routes/artifacts.py`). Released before 0052, such a
    document states a percentage the client dashboard now refuses, so it is
    withheld the same way. Another kind's deliverable is never stale here.
    """
    svc = db.get(Service, deliv.service_id)
    if svc is None or svc.kind != ServiceKind.ATTACK_COVERAGE:
        return False
    parent = attack_parent(db, deliv)
    return parent is None or not is_current(parent)


def is_stale_risk_register(db: Session, provenance: dict | None) -> bool:
    """A Risk Register NOT provably built from current-catalog ATT&CK input.

    Readable ONLY when `provenance["inputs"]` is a list holding at least one
    ATT&CK input and EVERY ATT&CK input names an assessment that exists and is
    current. Everything else is stale, because missing data defaults to
    unconfirmed:

      * None -- a pre-0047 register, which records no inputs;
      * a dict with no `inputs` list -- `seed_demo.py` writes `{"excluded": []}`,
        the "reassuring bucket" `routes/risk.py` warns about: it looks like a
        clean record and names nothing it was built from;
      * no ATT&CK input -- generating requires one (`_gate`), so a register
        without it records nothing to vouch for;
      * an ATT&CK input with a bad id, a missing assessment, or a stale one.

    `_provenance_snapshot` writes at most one input per kind, so one ATT&CK input
    is the only shape the writer produces; every one is checked anyway, so a
    second can never be vouched for by the first.
    """
    if not isinstance(provenance, dict):
        return True
    inputs = provenance.get("inputs")
    if not isinstance(inputs, list):
        return True
    attack_inputs = [e for e in inputs if isinstance(e, dict) and e.get("kind") == "attack"]
    if not attack_inputs:
        return True
    for entry in attack_inputs:
        try:
            assessment_id = uuid.UUID(str(entry.get("assessment_id")))
        except ValueError:
            return True
        a = db.get(AttackAssessment, assessment_id)
        if a is None or not is_current(a):
            return True
    return False


#: What the client reads wherever a stale ATT&CK report is withheld. It states
#: the fact and names no action: nothing rescores an approved assessment yet
#: (#558), so a promise of one would name a control that does not exist (D-076).
CLIENT_WITHHELD_MESSAGE = (
    "This ATT&CK coverage report was produced against an earlier version of the "
    f"ATT&CK framework than the current one (v{SOURCE_VERSION}), so its figures "
    "are withheld."
)

#: The same, for a Risk Register built from one. States the fact, names no action.
RISK_REGISTER_WITHHELD_MESSAGE = (
    "This Risk Register was built from an ATT&CK coverage report produced against an "
    "earlier version of the ATT&CK framework than the current one "
    f"(v{SOURCE_VERSION}), so it is withheld."
)


def require_current_catalog_for_client(assessment: AttackAssessment) -> None:
    """Client-facing refusal: states the fact, names no internal control."""
    if is_current(assessment):
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "reason": REASON,
            "message": CLIENT_WITHHELD_MESSAGE,
        },
    )
