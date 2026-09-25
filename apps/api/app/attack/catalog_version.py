"""Refuse to compute or change an assessment scored against a different catalog (#556).

An assessment's coverage rows are keyed by technique code and pre-seeded from
whatever catalog existed when it was created. The catalog is now generated from
MITRE's STIX (D-091), and the list it replaced matched no ATT&CK version, so an
older assessment holds codes the catalog no longer has and lacks rows for
techniques it never saw. The readers used to DROP unknown codes silently
(`if r.technique_code in valid`), which after a catalog change reports a
percentage over an undisclosed, mixed set.

THREE STATES, ALL HANDLED:
  * `catalog_version == SOURCE_VERSION`: current; compute.
  * a different recorded version: refuse, naming both versions.
  * NULL, i.e. created before migration 0052: refuse. The catalog it was scored
    against was never recorded, and missing data defaults to unconfirmed.

The consultant message names only controls that exist: "Discard draft" and
"Start assessment", and only for a DRAFT. An approved or released assessment
has no control that starts a new version (#558), so its message names none.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.attack.catalog import SOURCE_VERSION
from app.models.attack_assessment import AttackAssessment, AttackAssessmentStatus

REASON = "attack_catalog_mismatch"


def is_current(assessment: AttackAssessment) -> bool:
    return assessment.catalog_version == SOURCE_VERSION


def _scored_against(assessment: AttackAssessment) -> str:
    if assessment.catalog_version is None:
        return "an ATT&CK catalog that was never recorded"
    return f"ATT&CK v{assessment.catalog_version}"


def require_current_catalog(assessment: AttackAssessment) -> None:
    """Consultant-facing refusal (typed 409) for an assessment on another catalog."""
    if is_current(assessment):
        return
    message = (
        f"This assessment was scored against {_scored_against(assessment)}, not the "
        f"current ATT&CK v{SOURCE_VERSION} catalog, so its coverage cannot be computed "
        "or changed."
    )
    if assessment.status == AttackAssessmentStatus.DRAFT:
        message += (
            f" Discard the draft and start a new assessment to score it against "
            f"v{SOURCE_VERSION}."
        )
    else:
        message += " It has to be rescored in a new assessment version."
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"reason": REASON, "message": message},
    )


def require_current_catalog_for_client(assessment: AttackAssessment) -> None:
    """Client-facing refusal: states the fact, names no internal control."""
    if is_current(assessment):
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "reason": REASON,
            "message": (
                "This ATT&CK coverage report was produced against an earlier version of "
                "the ATT&CK framework and is withheld until it is rescored against "
                f"ATT&CK v{SOURCE_VERSION}."
            ),
        },
    )
