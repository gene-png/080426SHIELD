"""What a capability item's cost and licence count may hold (#833, #879).

ONE statement of the bounds, called by every writer: the extraction
(`tech_debt/extract.py`), the item PATCH and the include-row route
(`routes/tech_debt.py`). Before #879 the routes had none, so a consultant's
cost of 1e13 or licence count of 2**31 overflowed the column on Postgres as an
untyped 500 -- a failure SQLite never shows -- and a negative was stored.

* `annual_cost_usd` is `Numeric(14, 2)`: 0 to 999,999,999,999.99. The range and
  sign are judged on the exact value FIRST: quantizing a value like 1e30 to
  cents needs more than the default 28-digit decimal context and raises, and
  -0.004 quantizes to -0.00 (#878 narrow review).
* `license_count` is `Integer`: 0 to 2**31 - 1.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

#: `Numeric(14, 2)` holds below 10**12.
COST_LIMIT = Decimal(10**12)
CENT = Decimal("0.01")
#: A 32-bit `Integer` column.
INT_MAX = 2**31 - 1

OUT_OF_RANGE = "out_of_range"
NOT_WHOLE_CENTS = "not_whole_cents"


def _exact(value: float) -> Decimal | None:
    return Decimal(repr(float(value))) if math.isfinite(value) else None


def cost_problem(value: float) -> str | None:
    """Why `value` cannot be stored as an annual cost, or None when it can.

    `NOT_WHOLE_CENTS` is a value the column would round: the extraction rounds
    it and records that; a consultant's edit is refused, so they see why.
    """
    exact = _exact(value)
    if exact is None or not 0 <= exact < COST_LIMIT:
        return OUT_OF_RANGE
    cents = exact.quantize(CENT, rounding=ROUND_HALF_UP)
    if cents >= COST_LIMIT:
        # 999999999999.995 is below the limit exactly and rounds up onto it.
        return OUT_OF_RANGE
    if cents != exact:
        return NOT_WHOLE_CENTS
    return None


def cost_in_cents(value: float) -> float:
    """`value` quantized to cents. Call only when `cost_problem` is None or
    `NOT_WHOLE_CENTS`."""
    exact = _exact(value)
    if exact is None:
        raise ValueError(f"not a finite cost: {value!r}")
    return float(exact.quantize(CENT, rounding=ROUND_HALF_UP))


def license_problem(value: int) -> str | None:
    """Why `value` cannot be stored as a licence count, or None when it can."""
    return None if 0 <= value <= INT_MAX else OUT_OF_RANGE
