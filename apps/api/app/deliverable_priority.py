"""A gap's priority as a deliverable shows it: one decimal, ROUNDED DOWN
(advisor, #736 6220638526 item 3, option (A): every new render floors;
a released file is stored bytes and is never re-rendered, so it keeps the
numbers it was delivered with without any check here).

Shared by the CSF self-assessment deliverable (`csf/exporters.py`) and its
Zero Trust twin, so the two cannot round differently. The web gap list
computes the same way (`lib/csf/ratingCopy.ts::priorityWorking`).
"""

from __future__ import annotations


def floored_priority(gap_size: int, weight: float) -> float:
    """`gap_size x weight` to one decimal, rounded down, computed in INTEGER
    HUNDREDTHS of the weight, so the floor is exact by construction: a float
    product can sit just below a tenth (3 x 1.2 is 3.5999...). Measured: over
    today's CSF weights and gaps of 1 to 3, `floor(gap * weight * 10)` happens
    to agree, so this guards a weight change rather than a case reachable now.

    A weight with more than two decimals is rounded to hundredths first; a
    caller passes the stored weight as is."""
    tenths = (gap_size * round(weight * 100)) // 10
    return tenths / 10


def priority_text(gap_size: int, weight: float) -> str:
    """The PDF/DOCX Priority cell, e.g. `3.4`."""
    return f"{floored_priority(gap_size, weight):.1f}"
