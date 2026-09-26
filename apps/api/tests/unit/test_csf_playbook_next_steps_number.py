"""#682: the playbook's next steps agree in number with their counts.

`_next_steps` said "Remediate the 1 Priority 1 gap(s) first — these are
Core-metric, high-impact, multi-system weaknesses." A client reading one gap is
told "these are ... weaknesses". Both the PDF and the Word renderers call this
one function, so testing it covers both deliverables.

The expected sentences are written out, not built from the function's own
pieces: a test that derives its expectation from the thing it tests agrees by
construction.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.csf.playbook_export import _next_steps


def _rows(p1: int, p2: int, p3: int) -> list[SimpleNamespace]:
    return (
        [SimpleNamespace(priority="P1")] * p1
        + [SimpleNamespace(priority="P2")] * p2
        + [SimpleNamespace(priority="P3")] * p3
    )


@pytest.mark.unit
def test_one_gap_per_priority_is_singular() -> None:
    assert _next_steps(_rows(1, 1, 1)) == [
        "Remediate the 1 Priority 1 gap first — this is a Core-metric, high-impact, "
        "multi-system weakness.",
        "Schedule the 1 Priority 2 gap into the next planning cycle.",
        "Track the 1 Priority 3 gap for continuous improvement.",
    ]


@pytest.mark.unit
def test_several_gaps_per_priority_are_plural() -> None:
    assert _next_steps(_rows(2, 3, 4)) == [
        "Remediate the 2 Priority 1 gaps first — these are Core-metric, high-impact, "
        "multi-system weaknesses.",
        "Schedule the 3 Priority 2 gaps into the next planning cycle.",
        "Track the 4 Priority 3 gaps for continuous improvement.",
    ]


@pytest.mark.unit
def test_no_gaps_keeps_its_own_sentence() -> None:
    # The branch this change does not touch, pinned so a reword cannot drop it.
    assert _next_steps(_rows(0, 0, 0)) == [
        "No gaps were identified — maintain current controls and re-assess on the next cycle."
    ]
