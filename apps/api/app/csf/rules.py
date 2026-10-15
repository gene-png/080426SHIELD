"""Which Enterprise roll-up rule a CSF assessment renders under (#1031).

Ruling 3 (#736 6116519635): released numbers freeze. An assessment approved
before #1031 keeps rolling up every in-scope tier, unscored seed tiers
included; only new or re-approved versions roll up the scored tiers alone,
and take their target from those tiers (ruling 2, option (a)).

`csf_assessments.rollup_rules` records it (migration 0070), as ATT&CK's
`status_rules` does (`attack/rules.py`). This is the ONLY reader.
"""

from __future__ import annotations

from typing import Any

import structlog

_log = structlog.get_logger(__name__)

#: Approved before #1031; the migration backfilled every APPROVED and RELEASED
#: row to this.
EVERY_TIER = 1
#: Approved under #1031; written at approve.
SCORED_TIERS = 2


class UnknownRollupRules(RuntimeError):
    """A stored `rollup_rules` this code does not know. Never defaulted:
    guessing either rule would render a delivered report differently from how
    it was delivered, or a new one under a rule it was not approved under."""


def scored_tiers_only(assessment: Any) -> bool:
    """True when `assessment` rolls up its scored tiers only (#1031).

    NULL is not yet approved, and reads as the new rule: it is approved under
    it. Any value other than NULL, 1 or 2 raises."""
    value = assessment.rollup_rules
    if value is None:
        return True
    # `type(...) is int`, not `==`: `True == 1` in Python.
    if type(value) is int and value == SCORED_TIERS:
        return True
    if type(value) is int and value == EVERY_TIER:
        return False
    _log.error(
        "csf.rollup_rules.unknown",
        assessment_id=str(getattr(assessment, "id", None)),
        value=repr(value),
    )
    raise UnknownRollupRules(
        f"CSF assessment {getattr(assessment, 'id', '?')} has rollup_rules={value!r}; "
        f"expected NULL, {EVERY_TIER} or {SCORED_TIERS}."
    )
