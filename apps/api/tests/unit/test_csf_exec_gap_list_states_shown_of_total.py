"""The CSF executive briefing says how many gaps its list leaves out (#718).

`render_exec_pdf` and `render_exec_docx` list "Top priority gaps" through
`_gap_rows(..., limit=12)`, and said nothing when there were more: the
#75/#79 shape, a truncation with no "showing N of M". Driven through both exec
renderers, reading the rendered bytes back, with literal sentences.
"""

from __future__ import annotations

import io
import re
from types import SimpleNamespace

import pytest

from app.csf.playbook_export import render_exec_docx, render_exec_pdf


def _rows(gaps: int) -> list[SimpleNamespace]:
    rows = [
        SimpleNamespace(
            subcategory_code=f"GV.OC-{i:02d}",
            name=f"Outcome {i:02d}",
            function="GV",
            tier_levels={"moderate": 1},
            enterprise_level=1,
            rollup_rule=1,
            target_level=3,
            gap=True,
            priority="P2",
        )
        for i in range(1, gaps + 1)
    ]
    rows.append(
        SimpleNamespace(
            subcategory_code="PR.AA-01",
            name="Identity management",
            function="PR",
            tier_levels={"moderate": 4},
            enterprise_level=4,
            rollup_rule=1,
            target_level=3,
            gap=False,
            priority=None,
        )
    )
    return rows


def _pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader

    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(raw)).pages)
    return re.sub(r"\s+", " ", text)


def _docx_text(raw: bytes) -> str:
    from docx import Document

    return "\n".join(p.text for p in Document(io.BytesIO(raw)).paragraphs)


def _both(gaps: int) -> dict[str, str]:
    kwargs = {
        "client_name": "Atlas",
        "version": 1,
        "enterprise_rows": _rows(gaps),
        "approved": True,
    }
    return {
        "pdf": _pdf_text(render_exec_pdf(**kwargs)),
        "docx": _docx_text(render_exec_docx(**kwargs)),
    }


@pytest.mark.unit
def test_a_truncated_exec_list_says_how_many_it_shows_and_leaves_out() -> None:
    expected = "Showing the 12 highest-priority of 15 gaps; 3 further gaps not listed."
    for fmt, text in _both(15).items():
        assert expected in text, f"exec {fmt} truncates silently: {text[:600]!r}"


@pytest.mark.unit
def test_one_gap_left_out_is_one_gap() -> None:
    expected = "Showing the 12 highest-priority of 13 gaps; 1 further gap not listed."
    for fmt, text in _both(13).items():
        assert expected in text, f"exec {fmt}: {text[:600]!r}"


@pytest.mark.unit
def test_an_untruncated_exec_list_says_it_is_complete() -> None:
    for fmt, text in _both(12).items():
        assert "All 12 gaps listed." in text, f"exec {fmt}: {text[:600]!r}"
        assert "further gap" not in text, f"exec {fmt} claims a truncation that did not happen"
