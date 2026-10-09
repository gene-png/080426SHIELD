"""Which capabilities count as security tooling — the ATT&CK input subset.

Tech Debt covers the whole software portfolio (migration 0038), so the ATT&CK
mapping can no longer treat "everything in the capability list" as the security
inventory. It needs a subset, and getting that subset wrong is asymmetric.

``routes/attack.py`` turns these names into ``valid_tools``, which is not just
prompt input — it is a hard allow-list on the tools the model is permitted to
cite. Drop a real security tool from it and the model *cannot* name it, so the
technique it covers reads as uncovered. That is a fabricated gap: an absence the
report presents as assessed.

Hence the rule below. A row is in scope unless someone has actually decided it
is not:

===========================  ==========================  ====================
security_related             security_class_confirmed    In the ATT&CK subset?
===========================  ==========================  ====================
True                         (any)                       yes
None (never classified)      (any)                       yes — pre-0038 rows
False                        False (not signed off)      yes — provisional
False                        True (consultant agreed)    no
===========================  ==========================  ====================

The only way out of the subset is a human agreeing with the model. An
unreviewed negative costs a consultant one glance at a row that did not need it;
the failure it prevents is a blind spot nobody ever sees. We take the glance.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, or_

from app.models.capability import CapabilityItem


def in_security_scope(item: CapabilityItem) -> bool:
    """True when this capability belongs in the ATT&CK mapping subset."""
    if item.security_related is None or item.security_related:
        return True
    # Explicitly non-security — but only trusted once a consultant signs off.
    return not item.security_class_confirmed


def security_scope_filter() -> ColumnElement[bool]:
    """The same rule as a SQL predicate, for queries that must not load rows."""
    return or_(
        CapabilityItem.security_related.is_(None),
        CapabilityItem.security_related.is_(True),
        CapabilityItem.security_class_confirmed.is_(False),
    )


def awaiting_security_signoff(item: CapabilityItem) -> bool:
    """True when the model called this row non-security and nobody has agreed.

    These are what the review queue surfaces. They are still *in* the ATT&CK
    subset (see the table above) — the queue exists so that provisional state
    is visible and finite, not so it can be ignored.
    """
    return item.security_related is False and not item.security_class_confirmed


#: #845: Tech Debt v3.2 (issue 806, comment 5983838515) tells the model to
#: "Begin `notes` with exactly `Security tool not in use:`" for a security tool
#: the row describes as planned, not yet deployed, inactive or no longer used.
#: The ONE constant every reader matches; tests copy the string from the prompt.
NOT_IN_USE_PREFIX = "Security tool not in use:"

#: The extraction prompt versions that ask for the prefix. v3.2 is the in-tree
#: prompt since the #806 Tech Debt prompt PR, so a new extraction fills the
#: not-in-use group and measures the contradiction count. A list an earlier
#: prompt (v2) drafted never asked for it: its group fills only from a
#: consultant's own note, and its count stays not measured. Add a version here
#: only when its prompt asks for the prefix.
PROMPT_VERSIONS_WITH_PREFIX: frozenset[str] = frozenset({"v3.2"})


def _notes_carry_the_prefix(notes: object) -> bool:
    """Exact and case-sensitive, after leading whitespace: the prompt names one
    literal, so anything else is the ordinary wording, never a guess."""
    return isinstance(notes, str) and notes.lstrip().startswith(NOT_IN_USE_PREFIX)


def not_in_use_security_tool(item: object) -> bool:
    """A negative carrying the prefix: what confirming takes out of ATT&CK scope
    as "not in use" rather than as "not security-related"."""
    return getattr(item, "security_related", None) is False and _notes_carry_the_prefix(
        getattr(item, "notes", None)
    )


def signoff_kind(item: object) -> str | None:
    """How the sign-off queue words this row, or None when it is not queued.

    "not_in_use": a security tool the extraction marked not in use (the prefix).
    "not_security": any other negative awaiting sign-off -- today's wording. A
    row the prefix misses falls back here, and scope is the same either way:
    confirming removes it from the ATT&CK subset whichever kind it is.
    """
    if not awaiting_security_signoff(item):  # type: ignore[arg-type]
        return None
    return "not_in_use" if not_in_use_security_tool(item) else "not_security"


def not_in_use_contradiction(item: object) -> bool:
    """The prefix on a row that is security-related.

    v3.2 pairs the prefix with `security_related: false` and no functions. A row
    that also lists functions is kept security-related by the parser (the safe
    direction, `extract._coerce_item`), so it is stored this way. A consultant's
    override of a not-in-use row stores the same shape; the caller excludes those.
    """
    return getattr(item, "security_related", None) is True and _notes_carry_the_prefix(
        getattr(item, "notes", None)
    )
