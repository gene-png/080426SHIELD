"""The ATT&CK security subset — who is in it, and who decides.

Tech Debt covers the whole software portfolio since migration 0038, so these
rules decide which capabilities the ATT&CK mapping is allowed to cite. Getting
them wrong is asymmetric: `valid_tools` in routes/attack.py is an allow-list, so
a security tool missing from this subset cannot be named by the model at all,
and the technique it covers reads as uncovered rather than unassessed.

Every test below is really one assertion: nothing leaves the subset without a
human saying so.
"""

from __future__ import annotations

import pytest

from app.models.capability import CapabilityItem, SecurityFunction
from app.tech_debt.security_scope import (
    awaiting_security_signoff,
    in_security_scope,
)


def _item(**kw) -> CapabilityItem:
    """An unattached row. Column defaults do NOT apply until INSERT, so
    `security_class_confirmed` is None here unless set — which is exactly the
    state the scope rule has to survive."""
    return CapabilityItem(name=kw.pop("name", "Thing"), **kw)


@pytest.mark.unit
def test_security_related_row_is_in_scope() -> None:
    assert in_security_scope(_item(security_related=True)) is True


@pytest.mark.unit
def test_unclassified_row_is_in_scope() -> None:
    """Every row written before 0038 has NULL here. None is the absence of a
    decision, not a negative one — reading it as False would silently drop the
    entire pre-migration inventory out of ATT&CK."""
    assert in_security_scope(_item(security_related=None)) is True


@pytest.mark.unit
def test_unconfirmed_negative_stays_in_scope() -> None:
    """The core safeguard. The model says "not security"; nobody has agreed yet,
    so the call is not acted on."""
    item = _item(security_related=False, security_class_confirmed=False)
    assert in_security_scope(item) is True
    assert awaiting_security_signoff(item) is True


@pytest.mark.unit
def test_negative_with_null_confirmed_flag_stays_in_scope() -> None:
    """Defensive: an unattached or pre-default row has None, not False. It must
    behave as "not signed off", never as "signed off"."""
    assert in_security_scope(_item(security_related=False)) is True


@pytest.mark.unit
def test_confirmed_negative_leaves_scope() -> None:
    """The only exit. A human agreed with the model."""
    item = _item(security_related=False, security_class_confirmed=True)
    assert in_security_scope(item) is False
    # Signed off, so it is no longer outstanding work for the review queue.
    assert awaiting_security_signoff(item) is False


@pytest.mark.unit
def test_confirmation_on_a_positive_row_does_not_remove_it() -> None:
    """A stale sign-off flag left on a row later reclassified as security-related
    must not evict it. `security_related` wins."""
    item = _item(security_related=True, security_class_confirmed=True)
    assert in_security_scope(item) is True
    assert awaiting_security_signoff(item) is False


@pytest.mark.unit
def test_only_negatives_are_queued_for_signoff() -> None:
    assert awaiting_security_signoff(_item(security_related=True)) is False
    assert awaiting_security_signoff(_item(security_related=None)) is False


@pytest.mark.unit
def test_security_function_values_match_attack_citation_buckets() -> None:
    """These three strings are the contract with AttackCoverage's
    prevention_tools / detection_tools / response_tools columns. Renaming one
    silently decouples the classification from the mapping it feeds."""
    assert [f.value for f in SecurityFunction] == ["prevent", "detect", "respond"]
