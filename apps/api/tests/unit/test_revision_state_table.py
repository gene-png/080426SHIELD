"""#1120: `decide_revision` against the reviewed expectation, for every element
of the enum product.

The product is built HERE from the model enums (`ServiceKind` and each kind's
status enum), never from the module under test, and every element must be a
key of `_revision_state_table.STATE_TABLE` (generated from the design note's
generator, not from `app/`). A rule changed without the table, or the table
without the rule, goes red; so does a new `ServiceKind` or a new status.
"""

from __future__ import annotations

import itertools

import pytest

from app.models.attack_assessment import AttackAssessmentStatus
from app.models.capability import CapabilityListStatus
from app.models.csf_assessment import CsfAssessmentStatus
from app.models.service import ServiceKind
from app.models.zt_assessment import ZtAssessmentStatus
from app.services.revisions import Decision, decide_revision
from tests.unit._revision_state_table import STATE_TABLE

pytestmark = pytest.mark.unit

#: Each kind's status enum, from the models.
KIND_SPEC = {
    ServiceKind.ATTACK_COVERAGE: AttackAssessmentStatus,
    ServiceKind.NIST_CSF: CsfAssessmentStatus,
    ServiceKind.ZERO_TRUST_CISA: ZtAssessmentStatus,
    ServiceKind.ZERO_TRUST_DOD: ZtAssessmentStatus,
    ServiceKind.TECH_DEBT: CapabilityListStatus,
}


def _product() -> set[tuple[str, str, str, bool]]:
    out = set()
    for kind, enum in KIND_SPEC.items():
        statuses = [m.value for m in enum]
        newers = ["none"] + [s for s in statuses if s != "discarded"]
        for st, newer, archived in itertools.product(statuses, newers, (False, True)):
            out.add((kind.name, st, newer, archived))
    return out


def test_every_service_kind_has_a_row_set() -> None:
    assert set(KIND_SPEC) == set(ServiceKind)


def test_the_table_covers_the_enum_product_exactly() -> None:
    product = _product()
    assert product - set(STATE_TABLE) == set(), "states with no expected outcome"
    assert set(STATE_TABLE) - product == set(), "expected outcomes for no state"


@pytest.mark.parametrize("key", sorted(STATE_TABLE), ids=lambda k: "-".join(map(str, k)))
def test_the_decision_matches_the_table(key: tuple[str, str, str, bool]) -> None:
    kind, st, newer, archived = key
    allowed, reason, copy = STATE_TABLE[key]
    got = decide_revision(
        kind=ServiceKind[kind], target_status=st, newer_status=newer, archived=archived
    )
    assert got == Decision(allowed, reason, copy), (key, got)
