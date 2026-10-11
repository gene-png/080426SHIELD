"""#419: the ATT&CK deliverable names its own denominator.

"Scored: 412/697" beside the Risk register's "ATT&CK coverage 12 of 700" read as
two different counts of one thing. Neither is wrong; the pair was unexplained.
The deliverable now says what it divides by: "412 of 697 techniques in the
ATT&CK 19.2 catalog this assessment was scored against".

Under #620's rules only (option (a)). An assessment approved before #620 renders
what was delivered, byte for byte -- `tests/golden/outside_counts_rule1/` pins
that, unchanged -- and its "Scored: X/Y" is asserted here as well, so neither
branch can be lost to the other.

The expected counts come from the WORLD -- its rows and the catalogue -- not
from the rollup the renderer reads.
"""

from __future__ import annotations

import pytest

from app.attack.catalog import SOURCE_VERSION, TECHNIQUES
from app.attack.exporters import render_docx, render_pdf, render_xlsx
from tests.unit.test_attack_outside_counts_follow_the_rule_set import (
    docx_text,
    pdf_text,
    world,
    xlsx_cells,
)

pytestmark = pytest.mark.unit

XLSX_LABEL = "Scored, of the techniques in the catalog this assessment was scored against"


def _flat(lines: list[str]) -> str:
    return " ".join(" ".join(lines).split())


def _counts(ctx) -> tuple[int, int]:
    scored = sum(1 for c in ctx.coverage if c.status is not None)
    return scored, len(TECHNIQUES)


def _summary(ctx) -> dict:
    return {r[0]: r[1] for r in xlsx_cells(render_xlsx(ctx))["Heatmap Summary"] if r}


@pytest.mark.parametrize("parent_rules", [2, None], ids=["rule-2", "draft"])
def test_under_the_new_rules_the_deliverable_names_its_catalog(parent_rules) -> None:
    ctx = world(parent_rules)
    ctx.assessment.catalog_version = SOURCE_VERSION
    scored, total = _counts(ctx)
    sentence = (
        f"Scored: {scored} of {total} techniques in the ATT&CK {SOURCE_VERSION} "
        "catalog this assessment was scored against"
    )
    assert sentence in _flat(docx_text(render_docx(ctx)))
    assert sentence in _flat(pdf_text(render_pdf(ctx)))
    summary = _summary(ctx)
    assert summary.get(XLSX_LABEL) == f"{scored} of {total}"
    assert "Scored / Total" not in summary


def test_with_no_recorded_catalog_it_names_the_catalog_without_a_version() -> None:
    """Unreachable through the routes -- finalize calls `require_current_catalog`
    before `build_context`, and a NULL `catalog_version` is never current -- so
    pinned at the renderer, where the context could still be built with one."""
    ctx = world(2)
    ctx.assessment.catalog_version = None
    scored, total = _counts(ctx)
    sentence = (
        f"Scored: {scored} of {total} techniques in the catalog this assessment was "
        "scored against"
    )
    assert sentence in _flat(docx_text(render_docx(ctx)))
    assert sentence in _flat(pdf_text(render_pdf(ctx)))
    assert "ATT&CK None" not in _flat(docx_text(render_docx(ctx)))


def test_under_rule_1_the_delivered_wording_stands() -> None:
    ctx = world(1)
    ctx.assessment.catalog_version = SOURCE_VERSION
    scored, total = _counts(ctx)
    docx = _flat(docx_text(render_docx(ctx)))
    assert f"Scored: {scored}/{total}" in docx
    assert "this assessment was scored against" not in docx
    assert "this assessment was scored against" not in _flat(pdf_text(render_pdf(ctx)))
    assert _summary(ctx).get("Scored / Total") == f"{scored}/{total}"
