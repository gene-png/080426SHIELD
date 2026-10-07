"""`routes/zt.py::_validated_stage`: the one statement of what a zt_score stage
suggestion must be to be applied (#867 review B-4 extracted it from the inline
checks in `_zt_run_work` so the consistency measure can call it).

The expectations are the reasons `ZtDroppedSuggestion` records on the apply
path and the order `_zt_run_work` documented before the extraction (parse,
then RANGE 1..max_stage, then wholeness: "`4.9` on a 1-4 ladder is both out of
range and not whole, and out-of-range is the more useful thing to say"), not
values read from the function. The ROUTE surface is pinned separately, by
`test_zt_run_ai.py`, which is what proves the extraction preserved behaviour.
"""

from __future__ import annotations

import math

import pytest

from app.routes.zt import _validated_stage

pytestmark = pytest.mark.unit

CISA_MAX = 4  # CISA ZTMM 2.0: Traditional, Initial, Advanced, Optimal
DOD_MAX = 3


@pytest.mark.parametrize(
    ("raw", "max_stage", "expected"),
    [
        (1, CISA_MAX, (1, None)),
        (4, CISA_MAX, (4, None)),
        (2.0, CISA_MAX, (2, None)),
        ("2", CISA_MAX, (2, None)),
        (" 3 ", CISA_MAX, (3, None)),
        (0, CISA_MAX, (None, "out_of_range")),
        (5, CISA_MAX, (None, "out_of_range")),
        (4, DOD_MAX, (None, "out_of_range")),
        (4.9, CISA_MAX, (None, "out_of_range")),  # range BEFORE wholeness
        (2.5, CISA_MAX, (None, "unparseable")),
        (True, CISA_MAX, (None, "unparseable")),
        ("unknown", CISA_MAX, (None, "unparseable")),
        ("", CISA_MAX, (None, "unparseable")),
        (None, CISA_MAX, (None, "unparseable")),
        ([2], CISA_MAX, (None, "unparseable")),
        (math.inf, CISA_MAX, (None, "out_of_range")),
        (math.nan, CISA_MAX, (None, "out_of_range")),
    ],
)
def test_a_stage_is_applied_only_as_a_whole_number_on_the_ladder(raw, max_stage, expected) -> None:
    out = _validated_stage(raw, max_stage)
    assert out == expected
    if out[0] is not None:
        assert type(out[0]) is int, "the stored stage is an int, never a float or a str"
