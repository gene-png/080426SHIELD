"""`app/maturity_percent.py` (#1183): (avg - 1) / (top - 1), one decimal,
rounded down. Expected values are worked out by hand, never by the module."""

from __future__ import annotations

from fractions import Fraction

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


def test_an_exact_average_is_floored_from_its_own_value() -> None:
    # 215/106 = 2.0283..., (109/106) / 3 = 34.27...%: 34.2. The displayed
    # 2.03 would give 34.3.
    assert maturity_percent(Fraction(215, 106), 4) == 34.2
    assert maturity_percent(2.03, 4) == 34.3


def test_an_exact_average_outside_the_scale_raises() -> None:
    with pytest.raises(ValueError):
        maturity_percent(Fraction(9, 10), 4)


def test_a_float_average_is_read_by_its_decimal_text() -> None:
    # 1.9 is not exactly representable: Fraction(1.9) is 1.89999..., which
    # would floor (1.9 - 1) / 3 = 30% to 29.9.
    assert maturity_percent(1.9, 4) == 30.0


@pytest.mark.parametrize(("avg", "top", "expected"), [(1.15, 4, 5.0), (2.17, 4, 39.0)])
def test_a_float_product_cannot_shave_a_tenth_off_the_floor(
    avg: float, top: int, expected: float
) -> None:
    # (1.15 - 1) / 3 * 1000 is 49.99999999999999 in floats, so a float floor
    # reads 4.9; by hand, 0.15 / 3 = 5%.
    assert maturity_percent(avg, top) == expected
