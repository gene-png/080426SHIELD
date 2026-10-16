"""`app/deliverable_priority.py`: a gap's priority to one decimal, rounded
DOWN (advisor, #736 6220638526 item 3, option (A)), shared by the CSF and Zero
Trust deliverables.

Expected values are typed from the arithmetic (gap x weight, then the floor),
never computed by the module under test.
"""

from __future__ import annotations

import pytest

from app.deliverable_priority import floored_priority, priority_text

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("gap", "weight", "expected"),
    [
        (3, 1.15, 3.4),  # 3.45: rounding to nearest would give 3.5
        (3, 1.2, 3.6),  # 3.6 exactly, not 3.5
        (2, 1.15, 2.3),
        (1, 1.0, 1.0),
        (0, 1.2, 0.0),
    ],
)
def test_the_priority_is_floored_to_one_decimal(gap: int, weight: float, expected: float) -> None:
    assert floored_priority(gap, weight) == expected


def test_the_text_has_exactly_one_decimal() -> None:
    assert priority_text(3, 1.15) == "3.4"
    assert priority_text(1, 1.0) == "1.0"
