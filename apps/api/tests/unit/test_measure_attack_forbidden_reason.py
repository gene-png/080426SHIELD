"""#806 C4 in the consistency measure: a partial the AI gives a reason only a
consultant may give is refused whole by the apply path, so the measure must
treat it as no answer, never as agreement (review of PR #951, F1).

The four codes are literals from the approved prompt's section 8 (#806 comment
5982555899), not the route's constant.
"""

from __future__ import annotations

import json

import pytest
from scripts.measure_ai_consistency import (
    attack_downstream,
    compare_pair,
    computed_status_agreement,
)

from tests.unit.test_measure_ai_consistency_attack_tech_debt import _VALID, FIELDS, _context

pytestmark = pytest.mark.unit

FORBIDDEN = [
    "reach_limited",
    "evasive_variant_uncovered",
    "periodic_not_continuous",
    "detection_weak",
]


def _run(reason: str) -> dict:
    return {"techniques": [dict(_VALID["mitre_map"], reason_code=reason)]}


@pytest.mark.parametrize("field", FIELDS["mitre_map"])
@pytest.mark.parametrize("reason", FORBIDDEN)
def test_a_partial_with_a_forbidden_reason_is_never_agreement(reason, field) -> None:
    a = _run(reason)
    f = compare_pair("mitre_map", a, json.loads(json.dumps(a)), context=_context("mitre_map"))[
        "fields"
    ][field]
    assert f["compared"] == 1, "a refused suggestion left the denominator"
    assert f["equal"] == 0, "a suggestion the apply path refuses counted as agreement"
    assert (f["both_absent"], f["one_absent"]) == (1, 0)


@pytest.mark.parametrize("reason", FORBIDDEN)
def test_a_partial_with_a_forbidden_reason_is_no_computed_status_agreement(reason) -> None:
    a = _run(reason)
    da = attack_downstream(a, _context("mitre_map"))
    db = attack_downstream(json.loads(json.dumps(a)), _context("mitre_map"))
    assert da["refused"] == ["K1"]
    d = computed_status_agreement(da, db)
    assert (d["compared"], d["equal"], d["refused"]) == (1, 0, 1)


def test_the_control_a_reason_the_prompt_offers_agrees() -> None:
    """The same row with `missing_control_category`, which the prompt offers,
    is an answer the apply path writes, so it agrees and is not refused."""
    a = _run("missing_control_category")
    f = compare_pair("mitre_map", a, json.loads(json.dumps(a)), context=_context("mitre_map"))[
        "fields"
    ]["reason_code"]
    assert (f["compared"], f["equal"], f["both_absent"]) == (1, 1, 0)
    assert attack_downstream(a, _context("mitre_map"))["refused"] == []
