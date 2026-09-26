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


def _scored(n: int, gaps: int) -> list[SimpleNamespace]:
    """`n` subcategories in ONE function (so no strongest/weakest line), the
    first `gaps` of them short of target at Priority 1."""
    return [
        SimpleNamespace(
            function="GV",
            enterprise_level=2,
            target_level=3,
            gap=i < gaps,
            priority="P1" if i < gaps else None,
        )
        for i in range(n)
    ]


@pytest.mark.unit
def test_the_overview_is_singular_for_one_subcategory() -> None:
    """#692 round 1: `_overview_sentences`, which all four renderers call, said
    "1 subcategories fall short of their target maturity" directly above the
    next steps -- and "covers 1 in-scope NIST CSF 2.0 subcategories"."""
    from app.csf.playbook_export import _overview_sentences

    assert _overview_sentences(_scored(1, 1)) == [
        "This assessment covers 1 in-scope NIST CSF 2.0 subcategory. Enterprise "
        "maturity, rolled up across the impact tiers in use, averages Level 2 of 5.",
        "1 subcategory falls short of its target maturity — 1 Priority 1 (critical), "
        "0 Priority 2, and 0 Priority 3.",
    ]


@pytest.mark.unit
def test_the_overview_is_plural_for_several_subcategories() -> None:
    from app.csf.playbook_export import _overview_sentences

    assert _overview_sentences(_scored(3, 2)) == [
        "This assessment covers 3 in-scope NIST CSF 2.0 subcategories. Enterprise "
        "maturity, rolled up across the impact tiers in use, averages Level 2 of 5.",
        "2 subcategories fall short of their target maturity — 2 Priority 1 "
        "(critical), 0 Priority 2, and 0 Priority 3.",
    ]


@pytest.mark.unit
def test_the_overview_counts_subcategories_and_gaps_separately() -> None:
    """#692 round 2. At (1, 1) and (3, 2) the two counts agree in number, so a
    switch keyed on the WRONG count passed both. Three subcategories with one
    gap separates them."""
    from app.csf.playbook_export import _overview_sentences

    lines = _overview_sentences(_scored(3, 1))
    assert lines[0].startswith("This assessment covers 3 in-scope NIST CSF 2.0 subcategories.")
    assert lines[1] == (
        "1 subcategory falls short of its target maturity — 1 Priority 1 (critical), "
        "0 Priority 2, and 0 Priority 3."
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("n", "gaps", "expected"),
    [
        (1, 1, "1 subcategory · average Level 2 · 1 gap."),
        (3, 2, "3 subcategories · average Level 2 · 2 gaps."),
        (3, 1, "3 subcategories · average Level 2 · 1 gap."),
        (1, 0, "1 subcategory · average Level 2 · 0 gaps."),
    ],
)
def test_the_function_detail_line_agrees_in_number(n, gaps, expected) -> None:
    """#692 round 2: the full PDF and DOCX printed '1 subcategories … 1 gap(s).'
    One helper builds the line for both renderers."""
    from app.csf.playbook_export import _function_detail

    assert _function_detail(_scored(n, gaps)) == expected


@pytest.mark.unit
def test_both_full_deliverables_print_the_singular_function_line() -> None:
    """The helper, through the SURFACE: a renderer that went back to its own
    inline copy would pass the helper test and fail here. The shared fixture
    has one subcategory per function (GV with a gap, PR without)."""
    from app.csf.playbook_export import render_full_docx, render_full_pdf
    from tests.unit.test_playbook_export_content import (
        _docx_paragraphs,
        _enterprise_rows,
        _pdf_text,
    )

    args = {"client_name": "Client", "version": 1, "approved": False}
    rows = _enterprise_rows()
    paragraphs = _docx_paragraphs(render_full_docx(enterprise_rows=rows, **args))
    assert "1 subcategory · average Level 2 · 1 gap." in paragraphs
    assert "1 subcategory · average Level 5 · 0 gaps." in paragraphs
    pdf = " ".join(_pdf_text(render_full_pdf(enterprise_rows=rows, **args)).split())
    assert "1 subcategory · average Level 2 · 1 gap." in pdf
    assert "1 subcategories" not in pdf and "gap(s)" not in pdf
