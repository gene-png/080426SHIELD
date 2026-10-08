"""`routes/csf.py::_validated_dimension`: the one statement of what a csf_score
dimension suggestion must be to be applied (#867 extracted it from
`_apply_suggestions` so the consistency measure can call it).

The expectations are the reasons `CsfDroppedSuggestion` documents for the
apply path ("a whole number 0-2"; `unparseable` for a non-number or a
fraction, `out_of_range` outside 0-2, range judged before wholeness), not
values read from the function.
"""

from __future__ import annotations

import math

import pytest

from app.routes.csf import _validated_dimension

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, (0, None)),
        (1, (1, None)),
        (2, (2, None)),
        (2.0, (2, None)),
        ("2", (2, None)),
        (" 1 ", (1, None)),
        (3, (None, "out_of_range")),
        (-1, (None, "out_of_range")),
        (3.9, (None, "out_of_range")),  # range BEFORE wholeness
        (1.5, (None, "unparseable")),
        (True, (None, "unparseable")),
        ("N/A", (None, "unparseable")),
        ("", (None, "unparseable")),
        (None, (None, "unparseable")),
        ([1], (None, "unparseable")),
        (math.inf, (None, "out_of_range")),
        (math.nan, (None, "out_of_range")),
    ],
)
def test_a_dimension_is_applied_only_as_a_whole_number_from_0_to_2(raw, expected) -> None:
    assert _validated_dimension(raw) == expected
