"""The CSF Playbook says when in-scope subcategories have NO target (#762).

`routes/csf.py::_enterprise_subcategories` sets `gap=False` for a row with no
target, and nothing ever sets one except the per-row Target select: seeding and
Run AI leave every row untargeted. So the five Playbook files told the client
"No gaps — every in-scope subcategory meets its target." about an assessment
nobody had set a single target on, and told them to "maintain current
controls". Three states, not two (`CLAUDE.md`'s three-value CHECK): below
target, meets target, NO TARGET.

Every case reads all five rendered files back: the XLSX Enterprise Profile,
the executive PDF and DOCX, and the full PDF and DOCX. Three worlds: every row
untargeted, a mix, and every row targeted (the control, where the old wording
is still the true one).
"""

from __future__ import annotations

import io
import re
from types import SimpleNamespace

import pytest

from app.csf.playbook_export import (
    render_exec_docx,
    render_exec_pdf,
    render_full_docx,
    render_full_pdf,
    render_xlsx,
)

ALL_MET = "No gaps — every in-scope subcategory meets its target."
MAINTAIN = "maintain current controls"


def _row(code: str, fn: str, level: int, target: int | None) -> SimpleNamespace:
    gap = target is not None and level < target
    return SimpleNamespace(
        subcategory_code=code,
        name=f"Outcome {code}",
        function=fn,
        tier_levels={"moderate": level},
        enterprise_level=level,
        rollup_rule=1,
        target_level=target,
        gap=gap,
        priority="P2" if gap else None,
    )


def _untargeted_world() -> list[SimpleNamespace]:
    return [
        _row("GV.OC-01", "GV", 2, None),
        _row("ID.AM-02", "ID", 1, None),
        _row("PR.AA-01", "PR", 4, None),
    ]


def _mixed_world() -> list[SimpleNamespace]:
    return [
        _row("GV.OC-01", "GV", 2, 4),  # a gap
        _row("ID.AM-02", "ID", 4, 3),  # meets its target
        _row("PR.AA-01", "PR", 1, None),  # no target
        _row("PR.AA-02", "PR", 3, None),  # no target
    ]


def _targeted_world() -> list[SimpleNamespace]:
    return [
        _row("GV.OC-01", "GV", 4, 3),
        _row("ID.AM-02", "ID", 4, 4),
    ]


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader

    return _flat("".join(p.extract_text() for p in PdfReader(io.BytesIO(raw)).pages))


def _docx_text(raw: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(raw))
    parts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for row in t.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n".join(parts)


def _xlsx_gap_column(raw: bytes) -> dict[str, str]:
    """Subcategory -> its Gap cell, from the Enterprise Profile sheet."""
    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(raw))["Enterprise Profile"]
    header_row = next(
        r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == "Subcategory"
    )
    headers = [c.value for c in ws[header_row]]
    gap_col = headers.index("Gap") + 1
    return {
        ws.cell(row=r, column=1).value: ws.cell(row=r, column=gap_col).value or ""
        for r in range(header_row + 1, ws.max_row + 1)
        if ws.cell(row=r, column=1).value
    }


def _render(rows: list[SimpleNamespace]) -> dict[str, object]:
    kw = {"client_name": "Atlas", "version": 1, "enterprise_rows": rows, "approved": True}
    return {
        "xlsx": _xlsx_gap_column(render_xlsx(**kw, tier_profiles={}, gap_actions={})),
        "exec_pdf": _pdf_text(render_exec_pdf(**kw)),
        "exec_docx": _flat(_docx_text(render_exec_docx(**kw))),
        "full_pdf": _pdf_text(render_full_pdf(**kw)),
        "full_docx": _flat(_docx_text(render_full_docx(**kw))),
    }


TEXT_FILES = ("exec_pdf", "exec_docx", "full_pdf", "full_docx")


# ---------------------------------------------------------------------------
# Every in-scope row untargeted: the default after seed + Run AI
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_file_says_every_subcategory_meets_its_target_when_none_has_a_target() -> None:
    out = _render(_untargeted_world())
    expected = "No in-scope subcategory has a target set, so none is assessed for gaps."
    for name in TEXT_FILES:
        text = out[name]
        assert ALL_MET not in text, f"{name} claims every subcategory meets a target"
        assert expected in text, f"{name} does not say no target was set: {text[:800]!r}"


@pytest.mark.unit
def test_the_exec_next_steps_state_the_untargeted_rows_and_never_say_maintain() -> None:
    out = _render(_untargeted_world())
    statement = "3 in-scope subcategories have no target set; this plan does not cover them."
    for name in ("exec_pdf", "exec_docx"):
        assert statement in out[name], f"{name}: {out[name][-600:]!r}"
        assert MAINTAIN not in out[name], f"{name} advises maintaining controls"


@pytest.mark.unit
def test_the_overview_counts_the_untargeted_rows() -> None:
    out = _render(_untargeted_world())
    for name in TEXT_FILES:
        assert "3 in-scope subcategories have no target set." in out[name], name


@pytest.mark.unit
def test_every_gap_cell_of_an_untargeted_row_says_no_target() -> None:
    out = _render(_untargeted_world())
    assert out["xlsx"] == {
        "GV.OC-01": "No target",
        "ID.AM-02": "No target",
        "PR.AA-01": "No target",
    }
    for name in ("full_pdf", "full_docx"):
        # Two tables per row (by-function and appendix), so twice per row.
        assert out[name].count("No target") >= 6, f"{name}: {out[name].count('No target')}"


# ---------------------------------------------------------------------------
# A mix: one gap, one met, two untargeted
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_exec_caption_names_the_untargeted_rows_beside_the_gaps() -> None:
    out = _render(_mixed_world())
    caption = (
        "All 1 gap listed. 2 in-scope subcategories have no target set and are not "
        "assessed for gaps."
    )
    for name in ("exec_pdf", "exec_docx"):
        assert caption in out[name], f"{name}: {out[name][:1200]!r}"


@pytest.mark.unit
def test_a_mixed_assessment_states_both_counts_everywhere() -> None:
    out = _render(_mixed_world())
    for name in TEXT_FILES:
        assert "2 in-scope subcategories have no target set." in out[name], name
        assert ALL_MET not in out[name], name
    for name in ("exec_pdf", "exec_docx"):
        assert (
            "2 in-scope subcategories have no target set; this plan does not cover them."
            in out[name]
        ), name
        assert MAINTAIN not in out[name], name
    assert out["xlsx"] == {
        "GV.OC-01": "Yes",
        "ID.AM-02": "",
        "PR.AA-01": "No target",
        "PR.AA-02": "No target",
    }


@pytest.mark.unit
def test_the_full_playbook_roadmap_names_the_untargeted_rows_beside_its_gaps() -> None:
    # Review of #764, F3: the full PDF and DOCX "5. Prioritized roadmap" lists
    # the targeted gaps, and said nothing about the rows never measured.
    out = _render(_mixed_world())
    for name in ("full_pdf", "full_docx"):
        assert (
            "2 in-scope subcategories have no target set and are not assessed for gaps."
            in out[name]
        ), f"{name}: {out[name][-1500:]!r}"


@pytest.mark.unit
def test_one_untargeted_row_is_one_subcategory() -> None:
    rows = _mixed_world()[:3]
    out = _render(rows)
    for name in ("exec_pdf", "exec_docx"):
        assert (
            "1 in-scope subcategory has no target set; this plan does not cover it." in out[name]
        ), name
        assert (
            "All 1 gap listed. 1 in-scope subcategory has no target set and is not "
            "assessed for gaps." in out[name]
        ), name
    for name in TEXT_FILES:
        assert "1 in-scope subcategory has no target set." in out[name], name


@pytest.mark.unit
def test_targeted_rows_with_no_gap_beside_untargeted_ones_are_not_called_complete() -> None:
    # No gap among the targeted rows, but two rows have no target: "No gaps"
    # may only be said of the rows that have one.
    rows = [_row("ID.AM-02", "ID", 4, 3), _row("PR.AA-01", "PR", 1, None)]
    out = _render(rows)
    expected = (
        "No gaps among the 1 subcategory with a target. 1 in-scope subcategory has no "
        "target set, so it is not assessed for gaps."
    )
    for name in TEXT_FILES:
        assert expected in out[name], f"{name}: {out[name][:1200]!r}"
        assert ALL_MET not in out[name], name


# ---------------------------------------------------------------------------
# Control: every row targeted. The original wording is the true one here.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_fully_targeted_assessment_keeps_the_original_wording() -> None:
    out = _render(_targeted_world())
    for name in TEXT_FILES:
        assert ALL_MET in out[name], f"{name}: {out[name][:800]!r}"
        assert "no target" not in out[name].lower(), name
    for name in ("exec_pdf", "exec_docx"):
        assert MAINTAIN in out[name], name
    assert set(out["xlsx"].values()) == {""}
