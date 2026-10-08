"""The consistency measure under the approved ZT prompt (#806, C2 and C3).

`zt_no_result_count` counts the capabilities a run asked about that no entry
named; the expected value is the number of codes each test leaves out. The C2
caveat is stated in the report, because a v2 gap count rests on the engagement
stage and a v1 one on the model's own targets.
"""

from __future__ import annotations

import pytest
from scripts.measure_ai_consistency import ZT_DOWNSTREAM_TARGET_BASIS, zt_no_result_count

pytestmark = pytest.mark.unit

_ASKED = ["CISA.ID.01", "CISA.ID.02", "CISA.ID.03", "CISA.DV.01"]


@pytest.mark.parametrize(
    "left_out", [set(), {"CISA.ID.02"}, {"CISA.ID.01", "CISA.DV.01"}, set(_ASKED)]
)
def test_no_result_counts_the_codes_no_entry_named(left_out: set[str]) -> None:
    data = {"capabilities": [{"code": c, "current": 1} for c in _ASKED if c not in left_out]}
    assert zt_no_result_count({"capabilities": _ASKED}, data) == len(left_out)


def test_a_refused_entry_still_names_its_code() -> None:
    data = {"capabilities": [{"code": c, "current": 9} for c in _ASKED]}
    assert zt_no_result_count({"capabilities": _ASKED}, data) == 0


def test_the_report_states_what_the_gap_count_is_measured_against() -> None:
    assert "engagement stage" in ZT_DOWNSTREAM_TARGET_BASIS
    assert "not comparable" in ZT_DOWNSTREAM_TARGET_BASIS
