"""Which rule set an ATT&CK assessment renders under (#620, D-094).

Gene's condition, 2026-09-25: a released assessment keeps rendering what was
delivered. #620's presentation rules -- a computed parent's pending state
derived from its children, its own tools and rationale withheld, the client
triad and blind spots counted through sub-techniques, and the Risk Register
skipping parents -- apply only to assessments approved after #620 lands.

`attack_assessments.parent_rules` records it (migration 0054). This is the
ONLY reader, so every surface asks the same question the same way.
"""

from __future__ import annotations

from typing import Any

import structlog

_log = structlog.get_logger(__name__)

#: Approved before #620; the migration backfilled every APPROVED and RELEASED
#: row to this.
OLD_RULES = 1
#: Approved under D-094; written at approve.
NEW_RULES = 2


class UnknownParentRules(RuntimeError):
    """A stored value this code does not know. Never defaulted: guessing either
    rule set would render a delivered report differently from how it was
    delivered, or a new one under rules it was not approved under."""


def parents_computed(assessment: Any) -> bool:
    """True when `assessment` renders under D-094's rules for computed parents.

    NULL is a draft, not yet approved, and reads as the NEW rules (Gene's
    addition 1): a draft is edited and approved under them. Any value other
    than NULL, 1 or 2 raises.
    """
    value = assessment.parent_rules
    if value is None:
        return True
    # `type(...) is int`, not `==`: `True == 1` in Python, and a bool or a
    # float that compares equal is still not the integer the column stores.
    if type(value) is int and value == NEW_RULES:
        return True
    if type(value) is int and value == OLD_RULES:
        return False
    _log.error(
        "attack.parent_rules.unknown",
        assessment_id=str(getattr(assessment, "id", None)),
        value=repr(value),
    )
    raise UnknownParentRules(
        f"ATT&CK assessment {getattr(assessment, 'id', '?')} has parent_rules={value!r}; "
        f"expected NULL, {OLD_RULES} or {NEW_RULES}."
    )


#: #554 R3 (migration 0059): approved before R3, so the stored statuses render.
#: The migration backfilled every APPROVED and RELEASED row to this.
STORED_STATUSES = 1
#: Approved under R3: statuses are computed from Detect / Prevent / Respond.
COMPUTED_STATUSES = 2


class UnknownStatusRules(RuntimeError):
    """A stored `status_rules` this code does not know. Never defaulted, for
    the same reason as `UnknownParentRules`."""


def statuses_computed(assessment: Any) -> bool:
    """True when `assessment`'s statuses are computed from Detect / Prevent /
    Respond (#554 R3), not read as stored.

    The advisor's decision (d), 2026-10-02: R3 applies only to assessments
    approved after it ships. NULL is a draft, which is approved under R3, so it
    reads as computed. Any value other than NULL, 1 or 2 raises.
    """
    value = assessment.status_rules
    if value is None:
        return True
    if type(value) is int and value == COMPUTED_STATUSES:
        return True
    if type(value) is int and value == STORED_STATUSES:
        return False
    _log.error(
        "attack.status_rules.unknown",
        assessment_id=str(getattr(assessment, "id", None)),
        value=repr(value),
    )
    raise UnknownStatusRules(
        f"ATT&CK assessment {getattr(assessment, 'id', '?')} has status_rules={value!r}; "
        f"expected NULL, {STORED_STATUSES} or {COMPUTED_STATUSES}."
    )


__all__ = [
    "COMPUTED_STATUSES",
    "NEW_RULES",
    "OLD_RULES",
    "STORED_STATUSES",
    "UnknownParentRules",
    "UnknownStatusRules",
    "parents_computed",
    "statuses_computed",
]
