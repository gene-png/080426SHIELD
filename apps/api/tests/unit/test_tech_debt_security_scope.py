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

from dataclasses import dataclass

import pytest

from app.models.capability import CapabilityItem, SecurityFunction
from app.tech_debt.security_scope import (
    awaiting_security_signoff,
    in_security_scope,
)


@dataclass
class _ScopeFakeList:
    """Minimal stand-in for CapabilityList — build_context reads only these."""

    source_rows_total: int | None
    excluded_rows: list | None


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


# ---------------------------------------------------------------------------
# The boundary itself: "not cyber" must mean "out of ATT&CK", never "out of the
# Technical Debt review". Tech Debt covers the WHOLE software portfolio since
# migration 0038 — a design tool is still a licence the client pays for, and
# dropping it from the cost base would understate spend in a client deliverable
# (the N-010 failure, in a different disguise).
#
# These two halves live in different modules and nothing forces them to agree,
# so they are asserted together here.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_confirmed_non_security_row_still_counts_toward_tech_debt_cost() -> None:
    from app.tech_debt.exporters import build_context

    figma = _item(name="Figma", security_related=False, security_class_confirmed=True)
    figma.annual_cost_usd = 40_000
    falcon = _item(name="CrowdStrike Falcon", security_related=True)
    falcon.annual_cost_usd = 120_000

    # Out of the ATT&CK subset...
    assert in_security_scope(figma) is False
    assert in_security_scope(falcon) is True

    # ...but still in the Technical Debt review, and still in its money.
    ctx = build_context(
        client_legal_name="Acme",
        service_title="Technical Debt Review",
        cap_list=_ScopeFakeList(source_rows_total=2, excluded_rows=[]),
        items=[figma, falcon],
    )
    assert ctx.total_cost == 160_000.0, "a non-security licence is still spend"
    assert len(ctx.items) == 2, "the row stays in the inventory the client sees"
    assert figma in ctx.items


@pytest.mark.unit
def test_security_classification_is_not_consulted_by_the_deliverable_at_all() -> None:
    """The strong form: flipping the flag changes nothing on the Tech Debt side.

    If this ever fails, marking a row "not cyber" has started silently editing
    the client's cost base — which is a billing error, not a scoping one.
    """
    from app.tech_debt.exporters import build_context

    def _cost_with(security_related, confirmed):  # noqa: ANN001 - local helper
        row = _item(name="Thing", security_related=security_related)
        row.security_class_confirmed = confirmed
        row.annual_cost_usd = 10_000
        return build_context(
            client_legal_name="Acme",
            service_title="Technical Debt Review",
            cap_list=_ScopeFakeList(source_rows_total=1, excluded_rows=[]),
            items=[row],
        ).total_cost

    assert (
        _cost_with(True, False)
        == _cost_with(False, False)
        == _cost_with(False, True)
        == _cost_with(None, False)
        == 10_000.0
    )
