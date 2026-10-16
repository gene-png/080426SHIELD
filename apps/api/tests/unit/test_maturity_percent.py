"""`app/maturity_percent.py` (#1183): (avg - 1) / (top - 1), one decimal,
rounded down. Expected values are worked out by hand, never by the module."""

from __future__ import annotations

import pytest

from app.maturity_percent import maturity_percent

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("avg", "top", "expected"),
    [
        (1, 4, 0.0),  # the bottom of the scale is 0%, not 25%
        (4, 4, 100.0),
        (3, 4, 66.6),  # 66.66...: rounding to nearest would give 66.7
        (2.67, 4, 55.6),  # 1.67 / 3 = 55.66...
        (2.33, 4, 44.3),  # 1.33 / 3 = 44.33...
        (2.5, 5, 37.5),  # 1.5 / 4, exact
    ],
)
def test_the_percentage_is_floored_to_one_decimal(avg: float, top: int, expected: float) -> None:
    assert maturity_percent(avg, top) == expected


@pytest.mark.parametrize(("avg", "top"), [(0.5, 4), (4.01, 4), (1, 1)])
def test_an_impossible_average_or_scale_raises(avg: float, top: int) -> None:
    with pytest.raises(ValueError):
        maturity_percent(avg, top)
