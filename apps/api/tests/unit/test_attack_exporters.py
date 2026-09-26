"""ATT&CK PDF + XLSX exporter smokes."""

from __future__ import annotations

import io
import uuid

import pytest

from app.attack.analytics import compute as compute_heatmap
from app.attack.catalog import TECHNIQUES
from app.attack.coverage import CoverageStatus
from app.attack.exporters import build_context, render_docx, render_pdf, render_xlsx
from app.attack.pending import pending_codes as attack_pending_codes
from app.models.attack_assessment import (
    AttackAssessment,
    AttackAssessmentStatus,
    AttackCoverage,
)
from tests._attack_rows import standalone_rows

# Built with chr() rather than written as an escape. A tab typed as an
# escape into this file arrived as a REAL control byte and broke the parse --
# CLAUDE.md's control-character rule, and what check_no_control_chars.py
# exists to catch. chr(9) survives whatever writes the file.
_TAB_NEWLINE = chr(9) + chr(10) + " "


def _build_inputs(*, default_status: str | None = "covered"):
    a = AttackAssessment(
        id=uuid.uuid4(),
        service_id=uuid.uuid4(),
        version=1,
        status=AttackAssessmentStatus.APPROVED,
    )
    coverage: list[AttackCoverage] = []
    for t in TECHNIQUES:
        coverage.append(
            AttackCoverage(
                id=uuid.uuid4(),
                assessment_id=a.id,
                technique_code=t.id,
                status=default_status,
            )
        )
    coverage_map = {c.technique_code: c.status for c in coverage}
    rollup = compute_heatmap(coverage_map)
    return a, coverage, rollup


def _ctx(*, default_status: str | None = "covered"):
    a, coverage, rollup = _build_inputs(default_status=default_status)
    return build_context(
        client_legal_name="Atlas Defense Solutions",
        service_title="MITRE ATT&CK Coverage",
        assessment=a,
        coverage=coverage,
        rollup=rollup,
    )


@pytest.mark.unit
def test_xlsx_has_four_sheets() -> None:
    from openpyxl import load_workbook

    raw = render_xlsx(_ctx())
    assert raw[:2] == b"PK"
    wb = load_workbook(io.BytesIO(raw))
    # Four since the Unscored sheet: an unscored technique used to be one
    # "Unscored" cell among 600+ rows, findable only by filtering.
    assert set(wb.sheetnames) == {"Heatmap Summary", "Coverage", "Gaps", "Unscored"}


@pytest.mark.unit
def test_xlsx_coverage_sheet_has_one_row_per_technique() -> None:
    from openpyxl import load_workbook

    raw = render_xlsx(_ctx())
    wb = load_workbook(io.BytesIO(raw))
    ws = wb["Coverage"]
    assert ws.max_row == len(TECHNIQUES) + 1


@pytest.mark.unit
def test_xlsx_gap_sheet_lists_only_gaps() -> None:
    from openpyxl import load_workbook

    ctx = _ctx(default_status=CoverageStatus.GAP.value)
    raw = render_xlsx(ctx)
    wb = load_workbook(io.BytesIO(raw))
    ws = wb["Gaps"]
    # Header + every technique.
    assert ws.max_row == len(TECHNIQUES) + 1


@pytest.mark.unit
def test_xlsx_gap_placeholder_when_no_gaps() -> None:
    from openpyxl import load_workbook

    ctx = _ctx(default_status=CoverageStatus.COVERED.value)
    raw = render_xlsx(ctx)
    wb = load_workbook(io.BytesIO(raw))
    ws = wb["Gaps"]
    assert ws.max_row == 2  # header + single placeholder
    assert ws.cell(row=2, column=2).value == "No gaps recorded"


@pytest.mark.unit
def test_pdf_renders_valid_bytes() -> None:
    raw = render_pdf(_ctx())
    assert raw.startswith(b"%PDF-")
    assert len(raw) > 2000


def _pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    return "".join(page.extract_text() for page in reader.pages)


@pytest.mark.unit
def test_pdf_carries_title_client_and_a_known_tactic() -> None:
    # SMOKE §10: upgrade from %PDF- magic to real content — the title prefix
    # (the "&" in "ATT&CK" is reportlab-escaped, so match the stable "MITRE"),
    # the client name, and one known per-tactic rollup row.
    text = _pdf_text(render_pdf(_ctx()))
    assert "MITRE" in text  # service title prefix
    assert "Atlas Defense Solutions" in text  # client name
    assert "Reconnaissance" in text  # a known tactic rollup row


@pytest.mark.unit
def test_pdf_handles_zero_gaps() -> None:
    ctx = _ctx(default_status=CoverageStatus.COVERED.value)
    raw = render_pdf(ctx)
    assert raw.startswith(b"%PDF-")


@pytest.mark.unit
@pytest.mark.parametrize("unnamed", [None, "", "   ", _TAB_NEWLINE])
def test_build_context_falls_back_for_every_spelling_of_unnamed(unnamed: str | None) -> None:
    """A BLANK name must reach the fallback, not the document.

    `None` was the only arm here, and it is the only arm a bare
    `client_legal_name or "Client"` passes. `"   "` is TRUTHY, so under that
    expression it skipped the fallback entirely and rendered as EMPTY on the
    organisation line of the client's DOCX, PDF and XLSX -- the precise outcome
    #254 names as its motivation, left live at all five exporters while the
    write side was being fixed.

    Whitespace is reachable: `ClientProfilePatch` carried no validator before
    D-080, and migration 0049's three backfill predicates match a mapped
    domain, a display name and the old sentinel -- none of them whitespace.
    Migration 0050 clears the stored ones; this pins the read.
    """
    a, coverage, rollup = _build_inputs()
    ctx = build_context(
        client_legal_name=unnamed,
        service_title="x",
        assessment=a,
        coverage=coverage,
        rollup=rollup,
    )
    assert ctx.client_legal_name == "Client"


@pytest.mark.unit
def test_build_context_strips_a_padded_client_name() -> None:
    """A stored `"  Acme  "` reaches the document trimmed.

    The organisation line is not slugified, so padding that `deliverable_filename`
    would collapse survives into the rendered DOCX and PDF.
    """
    a, coverage, rollup = _build_inputs()
    ctx = build_context(
        client_legal_name="  Atlas Defense Solutions  ",
        service_title="x",
        assessment=a,
        coverage=coverage,
        rollup=rollup,
    )
    assert ctx.client_legal_name == "Atlas Defense Solutions"


# ---------------------------------------------------------------------------
# #102: pending review must reach the client-facing document
# ---------------------------------------------------------------------------


def _pending_ctx():
    """Half the catalogue `covered` and withheld, the other half a plain gap.

    This reports **0.0% coverage** -- every positive claim is withheld, so the
    numerator empties while the gaps hold the denominator open. Without the
    pending count beside it, that document is indistinguishable from one saying
    the client owns no controls at all, which is N-033's 607 fabricated gaps
    arriving by a new route.

    So the omission this fixture catches is not a cosmetic one in either
    direction: drop `pending_review` and the same number reads as a finding.
    """
    a, coverage, _ = _build_inputs(default_status=None)
    half = len(coverage) // 2
    for row in coverage[:half]:
        row.status = CoverageStatus.COVERED.value
    for row in coverage[half:]:
        row.status = CoverageStatus.GAP.value
    coverage_map = {c.technique_code: c.status for c in coverage}
    withheld = {c.technique_code for c in coverage[:half]}
    rollup = compute_heatmap(coverage_map, withheld)
    assert rollup.pending_review == half and rollup.covered == 0
    return (
        build_context(
            client_legal_name="Atlas Defense Solutions",
            service_title="MITRE ATT&CK Coverage",
            assessment=a,
            coverage=coverage,
            rollup=rollup,
        ),
        rollup,
    )


@pytest.mark.unit
def test_pdf_states_the_pending_count_beside_the_coverage_percentage() -> None:
    """The percentage is a ratio over what can be CLAIMED, so it is not
    self-describing -- see the analytics test of the same name. The PDF is the
    artifact that reaches the client, so it is the one place a bare percentage
    over withheld rows is a false assurance rather than a UI nit.
    """
    ctx, rollup = _pending_ctx()
    text = _pdf_text(render_pdf(ctx))
    assert f"Pending review {rollup.pending_review}" in text


@pytest.mark.unit
def test_docx_states_the_pending_count_beside_the_coverage_percentage() -> None:
    """The twin. CLAUDE.md: a defect found in one renderer exists in the others
    until checked -- #75 truncated identically in three of them, and #79 exists
    because an earlier change fixed one surface and not its sibling."""
    import io as _io

    from docx import Document

    ctx, rollup = _pending_ctx()
    doc = Document(_io.BytesIO(render_docx(ctx)))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert f"Pending review {rollup.pending_review}" in text


@pytest.mark.unit
def test_every_renderer_carries_pending_review_per_tactic_not_only_overall() -> None:
    """The per-tactic tables, where withholding can push a percentage UP.

    `_pending_ctx` withholds every positive claim, which drives the OVERALL
    figure down to 0% -- an omission there looks obviously wrong. The upward
    direction is the dangerous one and was not covered: a tactic holding one
    confirmed `covered` beside two withheld `partial`s reads 66.7% unwithheld
    and **100%** withheld, so a table without the count states a bare 100% over
    two claims nobody has vouched for.

    XLSX carried the column; the DOCX and PDF twins did not, with nothing saying
    why. That is the unstated-exemption shape CLAUDE.md records for #75/#79, and
    the §14 audit found it here.
    """
    import io as _io

    from docx import Document
    from openpyxl import load_workbook

    ctx, rollup = _pending_ctx()
    assert rollup.pending_review > 0, "the fixture withholds nothing"

    header = "Pending review"
    wb = load_workbook(io.BytesIO(render_xlsx(ctx)))
    ws = wb["Heatmap Summary"]
    tactic_header = next(
        r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == "Tactic"
    )
    assert header in [ws.cell(row=tactic_header, column=c).value for c in range(1, 14)]

    doc = Document(_io.BytesIO(render_docx(ctx)))
    docx_tables = [
        [c.text for c in t.rows[0].cells] for t in doc.tables if t.rows and t.rows[0].cells
    ]
    per_tactic = [h for h in docx_tables if h and h[0] == "Tactic"]
    assert per_tactic, "no per-tactic table in the DOCX"
    assert header in per_tactic[0], f"DOCX per-tactic header lacks the count: {per_tactic[0]}"

    # The PDF table is drawn, so assert on extracted text rather than a cell.
    assert header in _pdf_text(render_pdf(ctx))


@pytest.mark.unit
def test_xlsx_states_the_pending_count_and_carries_it_per_tactic() -> None:
    """The third renderer, plus the per-tactic sheet a consultant actually reads."""
    from openpyxl import load_workbook

    ctx, rollup = _pending_ctx()
    wb = load_workbook(io.BytesIO(render_xlsx(ctx)))
    ws = wb["Heatmap Summary"]
    labels = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value for r in range(1, 12)}
    assert labels.get("Pending review") == rollup.pending_review

    header_row = next(
        r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == "Tactic"
    )
    headers = [ws.cell(row=header_row, column=col).value for col in range(1, 13)]
    assert "Pending review" in headers


@pytest.mark.unit
def test_the_gap_truncation_disclosure_is_actually_printed() -> None:
    """D-049 rests on "ATT&CK has always disclosed this in its heading" — and
    until now nothing checked.

    Found by the item-3b audit. Both narrative renderers cap the gap list at 50
    and say so; deleting the `(N of M shown)` half of the heading left the whole
    suite green. That is exactly #75's defect — a client-facing truncation with
    no disclosure — sitting unpinned in the service D-049 cited as the good
    example.

    Asserted with the literal words AND both numbers, per the test-integrity
    gate: `str(n) in blob` would be satisfied by any unrelated occurrence of the
    same digits, and this document is full of counts.
    """
    a, coverage, _ = _build_inputs(default_status=CoverageStatus.GAP.value)
    rollup = compute_heatmap({c.technique_code: c.status for c in coverage})
    ctx = build_context(
        client_legal_name="Atlas Defense Solutions",
        service_title="MITRE ATT&CK Coverage",
        assessment=a,
        coverage=coverage,
        rollup=rollup,
    )
    total = rollup.gap
    assert total > 50, "fixture must exceed the cap or this proves nothing"
    # THE WORDING CHANGED AT #480 AND THE PROPERTY DID NOT. The heading read
    # "Top remediation gaps (50 of N shown)", which disclosed the truncation
    # correctly and, in the same breath, claimed a ranking the alphabetical sort
    # does not provide and a remediation the two-column table does not contain.
    # This pins the DISCLOSURE -- both numbers and the literal words -- so it
    # moves with the rewording rather than being deleted.
    expected = f"first 50 of {total} by technique code"

    assert expected in _pdf_text(render_pdf(ctx))

    import io as _io

    from docx import Document

    doc = Document(_io.BytesIO(render_docx(ctx)))
    docx_text = "\n".join(p.text for p in doc.paragraphs)
    assert expected in docx_text
    assert "alphabetical, not ranked" in docx_text, (
        "the heading must say the order is NOT a ranking -- that half is the "
        "#480 defect, and a reword keeping the counts while dropping it would "
        "pass the assertion above"
    )
    assert "Top remediation gaps" not in docx_text, (
        "the claim #480 removed is back: an alphabetical two-column list under "
        "a heading asserting a prioritisation"
    )


@pytest.mark.unit
def test_the_xlsx_gap_sheet_does_not_truncate_and_so_makes_no_claim() -> None:
    """The deliberate asymmetry, stated so it is not read as an oversight.

    The workbook is the machine-readable artifact and lists every gap, so it
    carries no "of M shown" heading — there is nothing withheld to disclose.
    """
    from openpyxl import load_workbook

    ctx = _ctx(default_status=CoverageStatus.GAP.value)
    ws = load_workbook(io.BytesIO(render_xlsx(ctx)))["Gaps"]
    assert ws.max_row == len(TECHNIQUES) + 1


@pytest.mark.unit
def test_the_per_technique_sheet_marks_a_withheld_row() -> None:
    """#102's rule reached the summary and stopped at the sheet beside it.

    Found by the item-3b audit. `Heatmap Summary` reported `Covered 0 /
    Pending review N` while the `Coverage` sheet in the SAME workbook listed
    those N techniques as `Covered`, because it printed `cov.status` raw. One
    document, two answers, and the contradiction is visible on adjacent tabs.

    The status still prints — it must, because clearing a citation puts the
    technique back into it. What is added is the column saying the claim is
    being withheld.
    """
    from openpyxl import load_workbook

    ctx, rollup = _pending_ctx()
    wb = load_workbook(io.BytesIO(render_xlsx(ctx)))
    ws = wb["Coverage"]
    headers = [ws.cell(row=1, column=c).value for c in range(1, 9)]
    assert "Pending review" in headers, headers
    col = headers.index("Pending review") + 1
    status_col = headers.index("Status") + 1

    flagged = [
        r
        for r in range(2, ws.max_row + 1)
        if (ws.cell(row=r, column=col).value or "").strip().lower() == "yes"
    ]
    assert (
        len(flagged) == rollup.pending_review
    ), "the sheet disagrees with the summary about how many rows are withheld"
    # And the underlying status survives on those rows, as its rendered label
    # (`coverage_label`), which is what a reader sees.
    assert {ws.cell(row=r, column=status_col).value for r in flagged} == {"Covered"}


# --------------------------------------------------------------------------- #
# The workbook says what the assessment knows.
#
# Measured on the dev stack 2026-09-23, on the one live-run assessment there:
# 632 of 633 rows carried a rationale and 515 a detection-tool list, and the
# workbook exported neither; its only free-text column, Notes, was empty on
# every row. One technique was unscored and appeared as a single cell among
# 633. And a tactic with nothing addressable exported 0.0% -- the same figure
# as a tactic that is all gaps.
# --------------------------------------------------------------------------- #

_RECON = "TA0043"


#: STANDALONE techniques (#554, D-094). These tests each need a row that
#: stands on its own evidence; `TECHNIQUES[0]` and `[4]` are computed parents,
#: whose pending state derives from their children, which `_ctx_from` builds at
#: `covered` with NULL citations -- so a parent there is always pending.
_CODES = [
    r["technique_code"] for r in standalone_rows([{"technique_code": t.id} for t in TECHNIQUES], 8)
]


def _ctx_from(rows: dict[str, dict], *, default_status: str | None = "covered"):
    """Every catalogue technique at `default_status`, with per-code overrides."""
    a, coverage, _ = _build_inputs(default_status=default_status)
    for cov in coverage:
        for field, value in rows.get(cov.technique_code, {}).items():
            setattr(cov, field, value)
    # Pending codes as production computes them, so a withheld row is withheld
    # here too (routes/attack.py builds the rollup the same way).
    rollup = compute_heatmap(
        {c.technique_code: c.status for c in coverage}, attack_pending_codes(coverage)
    )
    ctx = build_context(
        client_legal_name="Atlas Defense Solutions",
        service_title="MITRE ATT&CK Coverage",
        assessment=a,
        coverage=coverage,
        rollup=rollup,
    )
    return ctx, rollup


def _sheet_rows(ws) -> list[dict]:
    headers = [c.value for c in ws[1]]
    return [
        dict(zip(headers, (c.value for c in row), strict=True)) for row in ws.iter_rows(min_row=2)
    ]


def _xlsx(ctx):
    from openpyxl import load_workbook

    return load_workbook(io.BytesIO(render_xlsx(ctx)))


@pytest.mark.unit
def test_the_coverage_sheet_carries_the_rationale_and_all_three_tool_lists() -> None:
    code = _CODES[0]
    ctx, _ = _ctx_from(
        {
            code: {
                "rationale": "EDR telemetry detects the process tree.",
                "detection_tools": ["CrowdStrike Falcon", "Splunk"],
                "prevention_tools": ["Zscaler"],
                "response_tools": ["Cortex XSOAR"],
            }
        }
    )
    row = next(r for r in _sheet_rows(_xlsx(ctx)["Coverage"]) if r["Technique"] == code)
    assert row["Rationale"] == "EDR telemetry detects the process tree."
    assert row["Detection tools"] == "CrowdStrike Falcon; Splunk"
    assert row["Prevention tools"] == "Zscaler"
    assert row["Response tools"] == "Cortex XSOAR"
    # Notes stays: it has a writer (the technique panel's PATCH), and a
    # consultant's note is not the model's rationale.
    assert "Notes" in row


@pytest.mark.unit
def test_the_gaps_sheet_carries_the_rationale_for_each_gap() -> None:
    code = _CODES[1]
    ctx, _ = _ctx_from(
        {code: {"status": CoverageStatus.GAP.value, "rationale": "No tool observes this."}}
    )
    rows = _sheet_rows(_xlsx(ctx)["Gaps"])
    assert [r["Technique"] for r in rows] == [code]
    assert rows[0]["Rationale"] == "No tool observes this."


@pytest.mark.unit
def test_every_unscored_technique_is_listed_by_code_and_agrees_with_the_summary() -> None:
    # A null status and an unrecognised one are both unscored to the rollup
    # (`_validated`), so both must be listed -- the sheet may not use a
    # narrower predicate than the number it sits beside.
    null_code, bogus_code = _CODES[2], _CODES[3]
    ctx, rollup = _ctx_from({null_code: {"status": None}, bogus_code: {"status": "bogus"}})
    listed = [r["Technique"] for r in _sheet_rows(_xlsx(ctx)["Unscored"])]
    assert sorted(listed) == sorted([null_code, bogus_code])
    assert len(listed) == rollup.unscored_count == 2


@pytest.mark.unit
def test_the_unscored_sheet_says_so_when_there_are_none() -> None:
    ctx, rollup = _ctx_from({})
    assert rollup.unscored_count == 0
    rows = _sheet_rows(_xlsx(ctx)["Unscored"])
    assert len(rows) == 1
    assert rows[0]["Name"] == "No unscored techniques"


def _recon_unscored_rest_gap():
    """Reconnaissance has nothing addressable; every other tactic is all gaps.

    The pair is the point: a gap-only tactic legitimately reads 0.0%, and the
    defect was that a nothing-addressable tactic read the SAME.
    """
    recon = {t.id for t in TECHNIQUES if _RECON in t.tactics}
    others = {t.id for t in TECHNIQUES if _RECON not in t.tactics}
    assert recon and others
    rows = {code: {"status": None} for code in recon}
    return _ctx_from(rows, default_status=CoverageStatus.GAP.value)


@pytest.mark.unit
def test_a_tactic_with_nothing_addressable_reads_not_measured_not_zero_in_the_xlsx() -> None:
    ctx, _ = _recon_unscored_rest_gap()
    ws = _xlsx(ctx)["Heatmap Summary"]
    header_row = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == "Tactic")
    headers = [c.value for c in ws[header_row]]
    pct = headers.index("Coverage %")
    by_tactic = {
        row[0].value: row[pct].value for row in ws.iter_rows(min_row=header_row + 1) if row[0].value
    }
    other = next(t for t in by_tactic if t != _RECON)
    assert by_tactic[other] == 0.0  # the positive half first: a real zero stays zero
    assert by_tactic[_RECON] == "not measured"


@pytest.mark.unit
def test_a_tactic_with_nothing_addressable_reads_not_measured_not_zero_in_docx_and_pdf() -> None:
    from docx import Document

    ctx, _ = _recon_unscored_rest_gap()
    doc = Document(io.BytesIO(render_docx(ctx)))
    table = next(t for t in doc.tables if t.rows[0].cells[0].text == "Tactic")
    header = [c.text for c in table.rows[0].cells]
    pct = header.index("Coverage %")
    by_tactic = {r.cells[0].text: r.cells[pct].text for r in table.rows[1:]}
    other = next(t for t in by_tactic if t != _RECON)
    assert by_tactic[other] == "0.0%"
    assert by_tactic[_RECON] == "not measured"

    # The PDF table is drawn; assert the Recon row's text rather than a cell.
    text = " ".join(_pdf_text(render_pdf(ctx)).split())
    assert "TA0043 Reconnaissance" in text
    recon_row = text.split("TA0043 Reconnaissance", 1)[1].split("TA", 1)[0]
    assert "not measured" in recon_row, recon_row
    assert "0.0%" not in recon_row, recon_row


@pytest.mark.unit
def test_nothing_addressable_overall_reads_not_measured_in_every_renderer() -> None:
    from docx import Document

    ctx, rollup = _ctx_from({}, default_status=CoverageStatus.NOT_APPLICABLE.value)
    assert rollup.covered + rollup.partial + rollup.gap == 0

    ws = _xlsx(ctx)["Heatmap Summary"]
    labels = {r[0].value: r[1].value for r in ws.iter_rows(max_row=12)}
    assert labels["Coverage %"] == "not measured"

    paras = [p.text for p in Document(io.BytesIO(render_docx(ctx))).paragraphs]
    assert "Overall coverage: not measured" in paras
    assert "Overall coverage: not measured" in " ".join(_pdf_text(render_pdf(ctx)).split())


@pytest.mark.unit
def test_every_renderer_defines_the_coverage_percentage() -> None:
    from docx import Document

    ctx, _ = _ctx_from({})
    needle = "(Covered + 0.5 x Partial) / (Covered + Partial + Gap)"
    ws = _xlsx(ctx)["Heatmap Summary"]
    xlsx_cells = [c.value for row in ws.iter_rows(max_row=12) for c in row]
    assert any(isinstance(v, str) and needle in v for v in xlsx_cells)
    docx_text = "\n".join(p.text for p in Document(io.BytesIO(render_docx(ctx))).paragraphs)
    assert needle in docx_text
    assert needle in " ".join(_pdf_text(render_pdf(ctx)).split())


@pytest.mark.unit
def test_an_inferred_tool_is_marked_unconfirmed_beside_a_confirmed_one() -> None:
    """#102. A row with one confirmed tool is NOT pending review, so its
    inferred neighbour used to print exactly like a confirmed citation. The
    mark comes from `pending.uncleared_tools`: inferred and not cleared."""
    code = _CODES[4]
    ctx, _ = _ctx_from(
        {
            code: {
                "detection_tools": ["CrowdStrike Falcon", "Splunk"],
                "unconfirmed_citations": [
                    {"tool": "Splunk", "cited": "splunk es", "cleared_at": None}
                ],
            }
        }
    )
    row = next(r for r in _sheet_rows(_xlsx(ctx)["Coverage"]) if r["Technique"] == code)
    # The row itself is not withheld (an empty cell reads back as None)...
    assert not row["Pending review"]
    assert row["Detection tools"] == "CrowdStrike Falcon; Splunk (unconfirmed)"


@pytest.mark.unit
def test_a_cleared_citation_is_not_marked() -> None:
    code = _CODES[5]
    ctx, _ = _ctx_from(
        {
            code: {
                "detection_tools": ["Splunk"],
                "unconfirmed_citations": [
                    {"tool": "Splunk", "cited": "splunk es", "cleared_at": "2026-09-23T00:00:00"}
                ],
            }
        }
    )
    row = next(r for r in _sheet_rows(_xlsx(ctx)["Coverage"]) if r["Technique"] == code)
    assert row["Detection tools"] == "Splunk"


@pytest.mark.unit
def test_model_text_cannot_become_a_formula_or_break_the_workbook() -> None:
    """Rationale is model output and tool names come from a client upload.
    openpyxl stores a leading "=" as a formula and raises on control bytes."""
    code, gap_code = _CODES[6], _CODES[7]
    formula = '=HYPERLINK("http://example.test","click")'
    ctx, _ = _ctx_from(
        {
            code: {"rationale": formula, "detection_tools": ["=cmd|' /C calc'!A0"]},
            gap_code: {"status": CoverageStatus.GAP.value, "rationale": "bell" + chr(7)},
        }
    )
    wb = _xlsx(ctx)
    ws = wb["Coverage"]
    headers = [c.value for c in ws[1]]
    r = next(i for i in range(2, ws.max_row + 1) if ws.cell(i, 1).value == code)
    rationale = ws.cell(r, headers.index("Rationale") + 1)
    assert rationale.value == formula
    assert rationale.data_type == "s"
    assert ws.cell(r, headers.index("Detection tools") + 1).data_type == "s"
    gap = next(x for x in _sheet_rows(wb["Gaps"]) if x["Technique"] == gap_code)
    assert gap["Rationale"] == "bell"


@pytest.mark.unit
def test_a_tactic_whose_claims_are_all_pending_review_is_measured_not_unmeasured() -> None:
    """#102 withholds a Covered claim backed only by an inferred tool, moving it
    from `covered` into `pending_review`. Such a tactic has covered + partial +
    gap = 0, and read "not measured" -- while its Coverage tab listed the same
    techniques as Covered. Claims were made; they are withheld, which is 0.0%
    beside a pending count, not "never assessed"."""
    recon = [t.id for t in TECHNIQUES if _RECON in t.tactics]
    rows = {
        code: {
            "status": CoverageStatus.COVERED.value,
            "detection_tools": ["Inferred Tool"],
            "unconfirmed_citations": [
                {"tool": "Inferred Tool", "cited": "inferred", "cleared_at": None}
            ],
        }
        for code in recon
    }
    ctx, rollup = _ctx_from(rows, default_status=CoverageStatus.GAP.value)
    recon_tc = next(tc for tc in rollup.by_tactic if tc.tactic_id == _RECON)
    assert recon_tc.pending_review == len(recon)  # the setup withholds, as intended
    assert recon_tc.covered + recon_tc.partial + recon_tc.gap == 0

    ws = _xlsx(ctx)["Heatmap Summary"]
    header_row = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == "Tactic")
    headers = [c.value for c in ws[header_row]]
    pct = headers.index("Coverage %")
    by_tactic = {
        row[0].value: row[pct].value for row in ws.iter_rows(min_row=header_row + 1) if row[0].value
    }
    assert by_tactic[_RECON] == 0.0


@pytest.mark.unit
def test_the_client_entered_header_cells_are_safe_text() -> None:
    """Engagement (the client's legal name) and Service (a consultant-typed
    title) were written with a bare append, past the guard the rest of the
    workbook's free text goes through."""
    a, coverage, rollup = _build_inputs()
    ctx = build_context(
        client_legal_name="Atlas" + chr(7) + " Defense",
        service_title='=HYPERLINK("http://example.test","click")',
        assessment=a,
        coverage=coverage,
        rollup=rollup,
    )
    ws = _xlsx(ctx)["Heatmap Summary"]
    assert ws.cell(1, 2).value == "Atlas Defense"
    assert ws.cell(2, 2).value == '=HYPERLINK("http://example.test","click")'
    assert ws.cell(2, 2).data_type == "s"


@pytest.mark.unit
def test_a_computed_parent_delivers_no_rationale_or_tools_of_its_own() -> None:
    """#620 round 2, finding 4. A recomputed parent keeps whatever rationale and
    tools the model once wrote for it, and the workbook printed them beside a
    computed status they may contradict. Its evidence is its sub-techniques'.
    Stored data is left alone; only the deliverable stops emitting it. A child
    in the same world keeps its own, so this is not a blanket blank."""
    has_children = {t.parent_id for t in TECHNIQUES if t.parent_id is not None}
    parent = sorted(has_children)[0]
    child = next(t.id for t in TECHNIQUES if t.parent_id == parent)
    stale = {
        "status": "gap",
        "rationale": "Stale model text.",
        "detection_tools": ["Tool A"],
        "prevention_tools": ["Tool A"],
        "response_tools": ["Tool A"],
    }
    ctx, _ = _ctx_from({parent: stale, child: {**stale, "rationale": "Child text."}})
    wb = _xlsx(ctx)
    rows = {r["Technique"]: r for r in _sheet_rows(wb["Coverage"])}
    for col in ("Rationale", "Detection tools", "Prevention tools", "Response tools"):
        assert not rows[parent][col], (col, rows[parent][col])
    assert rows[child]["Rationale"] == "Child text."
    assert rows[child]["Detection tools"] == "Tool A"
    gaps = {r["Technique"]: r for r in _sheet_rows(wb["Gaps"])}
    assert not gaps[parent]["Rationale"]
    assert gaps[child]["Rationale"] == "Child text."
