"""#1343: the ZT deliverable discloses a gap row's target whose origin is not
recorded, with the approved sentence (#736 6220094031 item 5) and the approved
placement (6225462107): in the DOCX and PDF a line under the gap table,
`{code}: <sentence>`, one per code; in the XLSX Gap Plan, the sentence
appended to that row's Notes cell, never replacing what is there.

Two gaps against the same target: one whose per-capability target nobody
recorded (listed), and one the consultant set (not listed). Expected text is
written here from the ruling, never imported from the module under test.
"""

from __future__ import annotations

import io
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

SENTENCE = "Who set this target is not recorded. An earlier AI run may have set it."


def _ctx():
    """CISA at Stage 4 everywhere except two capabilities at Stage 1, each with
    a per-capability target of 3 against an engagement target of 2: `a`'s
    origin is not recorded, `b`'s was set by the consultant. Both are gaps only
    because of their per-capability target."""
    fw = ZtFrameworkCode.CISA_ZTMM_2_0
    caps = list(capabilities(fw))
    a, b = caps[0].code, caps[1].code
    assessment = ZtAssessment(
        id=uuid.uuid4(),
        service_id=uuid.uuid4(),
        framework=ZtFramework.CISA_ZTMM_2_0,
        version=1,
        status=ZtAssessmentStatus.APPROVED,
    )
    answers = []
    for cap in caps:
        if cap.code == a:
            ans = ZtAnswer(maturity_stage=1, target_stage=3, target_source=None, notes="kept")
        elif cap.code == b:
            ans = ZtAnswer(maturity_stage=1, target_stage=3, target_source="consultant")
        else:
            ans = ZtAnswer(maturity_stage=4)
        ans.id = uuid.uuid4()
        ans.assessment_id = assessment.id
        ans.capability_code = cap.code
        answers.append(ans)
    stages = {x.capability_code: x.maturity_stage for x in answers}
    targets = {x.capability_code: x.target_stage for x in answers}
    notes = {x.capability_code: x.notes for x in answers}
    gap = analyze_gaps(fw, stages, notes=notes, targets=targets, target_stage=2)
    assert sorted(g.code for g in gap.gaps) == sorted([a, b]), gap.gaps
    ctx = build_context(
        client_legal_name="Atlas Defense Solutions",
        service_title="Zero Trust Assessment",
        framework=fw,
        assessment=assessment,
        answers=answers,
        score=compute(fw, stages),
        gap=gap,
    )
    return ctx, a, b


def test_the_docx_lists_the_unrecorded_target_under_the_gap_table() -> None:
    from docx import Document

    ctx, a, b = _ctx()
    paragraphs = [p.text for p in Document(io.BytesIO(render_docx(ctx))).paragraphs]
    assert f"{a}: {SENTENCE}" in paragraphs, paragraphs
    assert f"{b}: {SENTENCE}" not in paragraphs


def test_the_pdf_lists_the_unrecorded_target() -> None:
    from pypdf import PdfReader

    ctx, a, b = _ctx()
    raw = render_pdf(ctx)
    text = " ".join(" ".join(p.extract_text() for p in PdfReader(io.BytesIO(raw)).pages).split())
    assert f"{a}: {SENTENCE}" in text, text
    assert f"{b}: {SENTENCE}" not in text


def test_the_xlsx_appends_the_sentence_to_that_rows_notes() -> None:
    from openpyxl import load_workbook

    ctx, a, b = _ctx()
    ws = load_workbook(io.BytesIO(render_xlsx(ctx)))["Gap Plan"]
    assert ws.cell(row=2, column=8).value == "Notes"
    notes = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=8).value for r in (3, 4)}
    # Appended, never replacing the row's own notes.
    assert notes[a] == f"kept {SENTENCE}", notes
    assert SENTENCE not in (notes[b] or ""), notes
