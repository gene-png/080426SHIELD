"""(d), the Zero Trust twin of #1242: the ZT deliverable shows a gap's priority
as the admin screen does, one decimal ROUNDED DOWN (advisor, #736 6220638526
item 3, option (A): every new render floors).

Before this, `zt/exporters.py` printed `f"{g.priority_score:.2f}"` (3.45) in
the DOCX and PDF and the raw two-decimal score in the XLSX, while
`ZtGapList.tsx` showed 3.4 for the same gap -- the screen and the deliverable
disagreed. The case below is the one that tells the rules apart: a Data-pillar
gap of 3 weighs 3 x 1.15 = 3.45, which rounds DOWN to 3.4, where `.1f`,
`toFixed(1)` and round-half-up all give 3.5 and `.2f` gives 3.45.

The screen half is pinned by `ZtGapList.copy.test.tsx` ("rounds DOWN where
rounding to nearest would round up"), against the same literal 3.4. The value
is written here from that rule, never computed by the helper under test.
"""

from __future__ import annotations

import io
import re
import uuid

import pytest

from app.models.zt_assessment import (
    ZtAnswer,
    ZtAssessment,
    ZtAssessmentStatus,
    ZtFramework,
)
from app.zt.catalog import capabilities
from app.zt.exporters import build_context, render_docx, render_pdf, render_xlsx
from app.zt.maturity import ZtFrameworkCode
from app.zt.scoring import analyze_gaps, compute

pytestmark = pytest.mark.unit

#: 3 x 1.15 (the Data pillar's weight), rounded down to one decimal.
FLOORED = "3.4"
#: What the deliverable printed before: two decimals.
UNFLOORED = "3.45"


def _one_data_gap_ctx():
    """A CISA assessment at Stage 4 everywhere but ONE Data-pillar capability
    at Stage 1, against target 4: exactly one gap, of size 3, weighed 1.15."""
    framework = ZtFrameworkCode.CISA_ZTMM_2_0
    caps = list(capabilities(framework))
    data_cap = next(c for c in caps if c.pillar_code == "DT")
    a = ZtAssessment(
        id=uuid.uuid4(),
        service_id=uuid.uuid4(),
        framework=ZtFramework.CISA_ZTMM_2_0,
        version=1,
        status=ZtAssessmentStatus.APPROVED,
    )
    answers = [
        ZtAnswer(
            id=uuid.uuid4(),
            assessment_id=a.id,
            capability_code=c.code,
            maturity_stage=1 if c.code == data_cap.code else 4,
        )
        for c in caps
    ]
    stage_map = {ans.capability_code: ans.maturity_stage for ans in answers}
    gap = analyze_gaps(framework, stage_map, target_stage=4)
    assert [(g.code, g.gap_size) for g in gap.gaps] == [(data_cap.code, 3)], gap.gaps
    ctx = build_context(
        client_legal_name="Atlas Defense Solutions",
        service_title="Zero Trust Assessment",
        framework=framework,
        assessment=a,
        answers=answers,
        score=compute(framework, stage_map),
        gap=gap,
    )
    return ctx, data_cap.code


def _gap_row_cells(doc, code: str) -> list[str]:
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text for c in row.cells]
            if cells and cells[0] == code:
                return cells
    raise AssertionError(f"no gap-table row for {code}")


def test_the_docx_gap_table_floors_the_priority() -> None:
    from docx import Document

    ctx, code = _one_data_gap_ctx()
    cells = _gap_row_cells(Document(io.BytesIO(render_docx(ctx))), code)
    assert cells[-1] == FLOORED, cells


def test_the_pdf_gap_table_floors_the_priority() -> None:
    from pypdf import PdfReader

    ctx, code = _one_data_gap_ctx()
    raw = render_pdf(ctx)
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(raw)).pages)
    assert code in text
    assert UNFLOORED not in text, "the PDF still prints two decimals"
    # "3.4" not followed by another digit: present only once the cell floors.
    assert re.search(r"(?<![0-9.])3\.4(?![0-9])", text), text


def test_the_xlsx_gap_plan_floors_the_priority() -> None:
    from openpyxl import load_workbook

    ctx, code = _one_data_gap_ctx()
    ws = load_workbook(io.BytesIO(render_xlsx(ctx)))["Gap Plan"]
    # Row 1 is the caption, row 2 the header, row 3 the one gap.
    assert ws.cell(row=2, column=7).value == "Priority"
    assert ws.cell(row=3, column=1).value == code
    assert ws.cell(row=3, column=7).value == float(FLOORED)
