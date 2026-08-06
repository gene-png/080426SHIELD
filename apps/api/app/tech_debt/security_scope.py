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
