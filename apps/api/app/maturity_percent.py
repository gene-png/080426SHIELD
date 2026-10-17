"""A maturity average as a percentage of the scale (#1183, Gene's decision on
#736 6204217058, narrowed by the advisor in 6225264951):

    (avg - 1) / (top - 1), one decimal, ROUNDED DOWN.

The bottom of the scale is 0%, not 1/top: before this, a client at the lowest
tier everywhere read 25% (CSF, avg / top). Shared by the CSF and Zero Trust
client dashboards, so the two cannot compute it differently.
"""

from __future__ import annotations

from fractions import Fraction


def maturity_percent(avg: float | Fraction, top: int) -> float:
    """`avg` on a 1..`top` scale as a percentage, floored to one decimal.

    Computed exactly: `avg` is read through its decimal string
    (`Fraction(str(avg))`), so 2.33 is 233/100 and a float product cannot shave
    a tenth off the floor. Pass the EXACT average where one exists (`Fraction`):
    flooring a displayed
    average that was rounded up can print a figure above the truth (#1183,
    advisor 6228351462). A float is read as displayed (CSF rounds
    it to two decimals in `csf/scoring.py`).

    An average outside 1..`top`, or a scale with no width, is a defect
    upstream: it raises rather than print a negative or impossible figure."""
    if top < 2:
        raise ValueError(f"maturity scale 1..{top} has no width")
    exact = avg if isinstance(avg, Fraction) else Fraction(str(avg))
    if not 1 <= exact <= top:
        raise ValueError(f"maturity average {avg!r} is outside 1..{top}")
    tenths = (exact - 1) * 1000 // (top - 1)
    return int(tenths) / 10
