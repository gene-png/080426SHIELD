"""Which Enterprise roll-up rule a CSF assessment renders under (#1031).

Ruling 3 (#736 6116519635): released numbers freeze. An assessment approved
before #1031 keeps rolling up every in-scope tier, unscored seed tiers
included; only new or re-approved versions roll up the scored tiers alone,
and take their target from those tiers (ruling 2, option (a)).

`csf_assessments.rollup_rules` records it (migration 0070), as ATT&CK's
`status_rules` does (`attack/rules.py`). This is the ONLY reader.

Options 1 and 3 (Gene, #736 6200638511; Q2 approved in 6201691989) add rules
3: no evidence cap, and a subcategory with no scored tier gets no level
(#1073). Q2 freezes released numbers the way ruling 3 did: an assessment
approved under 1 or 2 keeps the cap and the every-row fallback.
"""

from __future__ import annotations

from typing import Any

import structlog

_log = structlog.get_logger(__name__)

#: Approved before #1031; the migration backfilled every APPROVED and RELEASED
#: row to this.
EVERY_TIER = 1
#: Approved under #1031, before Options 1 and 3.
SCORED_TIERS = 2
#: Approved under Options 1 and 3; written at approve.
UNCAPPED = 3


class UnknownRollupRules(RuntimeError):
    """A stored `rollup_rules` this code does not know. Never defaulted:
    guessing either rule would render a delivered report differently from how
    it was delivered, or a new one under a rule it was not approved under."""


def _rules(assessment: Any) -> int | None:
    """The stored value, checked. NULL is not yet approved, and reads as the
    newest rules: it is approved under them. Any other unknown value raises."""
    value = assessment.rollup_rules
    if value is None:
        return None
    # `type(...) is int`, not `==`: `True == 1` in Python.
    if type(value) is int and value in (EVERY_TIER, SCORED_TIERS, UNCAPPED):
        return value
    _log.error(
        "csf.rollup_rules.unknown",
        assessment_id=str(getattr(assessment, "id", None)),
        value=repr(value),
    )
    raise UnknownRollupRules(
        f"CSF assessment {getattr(assessment, 'id', '?')} has rollup_rules={value!r}; "
        f"expected NULL, {EVERY_TIER}, {SCORED_TIERS} or {UNCAPPED}."
    )


def scored_tiers_only(assessment: Any) -> bool:
    """True when `assessment` rolls up its scored tiers only (#1031): every
    rule but the frozen every-tier one."""
    return _rules(assessment) != EVERY_TIER


def evidence_cap_applies(assessment: Any) -> bool:
    """True when `assessment` was approved before Option 3 (rules 1 or 2), so
    a level without evidence on file stays capped as it was delivered."""
    return _rules(assessment) in (EVERY_TIER, SCORED_TIERS)


def unscored_has_no_level(assessment: Any) -> bool:
    """True when a subcategory with no scored tier gets no level (Option 1,
    #1073). Frozen assessments keep rolling up its seed rows, as delivered."""
    return _rules(assessment) in (None, UNCAPPED)
