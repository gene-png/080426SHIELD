"""ATT&CK Coverage deliverable renderers - PDF + XLSX.

XLSX sheets:
  - Heatmap Summary: tactic rollup (counts + coverage %)
  - Coverage:        per-technique status, rationale, the three tool lists
                     (unconfirmed citations marked) and notes (all 600+ rows)
  - Gaps:            techniques flagged as Gap, ordered by technique code
  - Unscored:        techniques with no usable status, listed by code

PDF:
  Executive page with overall coverage % + per-tactic table, then the
  Gap list (top 50 entries).
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.attack.analytics import CoverageRollup, TacticCoverage
from app.attack.catalog import TACTICS, TECHNIQUES, technique_by_id
from app.attack.coverage import CoverageStatus, coverage_label
from app.attack.pending import pending_codes as attack_pending_codes
from app.attack.pending import uncleared_tools
from app.client_naming import org_display_name
from app.models.attack_assessment import AttackAssessment, AttackCoverage

if TYPE_CHECKING:
    from reportlab.platypus import TableStyle


@dataclass(frozen=True)
class AttackDeliverableContext:
    client_legal_name: str
    service_title: str
    assessment: AttackAssessment
    coverage: list[AttackCoverage]
    rollup: CoverageRollup
    #: Technique codes whose status the rollup is WITHHOLDING (#102).
    #:
    #: Derived once, here, and read by both the summary and the per-technique
    #: sheet. `rollup.pending_review` is only a count, so a renderer needing to
    #: mark individual rows would otherwise re-derive the set — a second source
    #: of truth for the same fact, which is the drift D-052 rejected.
    pending_codes: frozenset[str] = frozenset()


def build_context(
    *,
    client_legal_name: str | None,
    service_title: str,
    assessment: AttackAssessment,
    coverage: Iterable[AttackCoverage],
    rollup: CoverageRollup,
) -> AttackDeliverableContext:
    rows = list(coverage)
    return AttackDeliverableContext(
        client_legal_name=org_display_name(client_legal_name),
        service_title=service_title,
        assessment=assessment,
        coverage=rows,
        rollup=rollup,
        # The SAME function the caller used to build `rollup`, over the same
        # rows, so the sheet and the summary cannot disagree about which
        # techniques are withheld.
        pending_codes=attack_pending_codes(rows),
    )


def _status_or_unscored(value: str | None) -> str:
    if value is None:
        return "Unscored"
    try:
        return coverage_label(CoverageStatus(value))
    except ValueError:
        return "Unknown"


#: What the percentage IS, stated in every renderer beside it. The workbook
#: gave a bare `Coverage %` with no definition, and the formula is not the one a
#: reader would guess: partial counts half, and N/A, unscored and withheld
#: techniques sit outside the denominator (see `attack/analytics.py`).
COVERAGE_PCT_DEFINITION = (
    "Coverage % = (Covered + 0.5 x Partial) / (Covered + Partial + Gap). "
    "N/A, Outside control surface, Not verified, Unscored and Pending review "
    "techniques are outside it; Not verified and Outside control surface are "
    "counted beside it; "
    "'not measured' means no technique there has a Covered, Partial or Gap "
    "status, counting those pending review."
)

#: Rendered where nothing is Covered, Partial, Gap or pending review (`_measured`).
#: Where Covered + Partial + Gap is zero, `_pct` in
#: `attack/analytics.py` returns 0.0 there, which is the same figure a tactic
#: that is ALL gaps earns -- so "nothing to measure" and "nothing covered" were
#: one number. NOT "n/a": that is the N/A (not applicable) status two columns to
#: the left, and a tactic whose techniques were never assessed would read as
#: "not applicable to us" -- the reassuring misreading. The rollup is left
#: alone (it also feeds the dashboards); what this deliverable prints, and the
#: deliverable's stored summary line (`coverage_pct_text`), change.
NOT_ADDRESSABLE = "not measured"

#: Suffix on a tool whose citation was INFERRED (a near-match to the client's
#: tool list) and not yet cleared by a consultant (#102, `attack/pending.py`).
#: A row with one confirmed tool is not pending, so without this mark an
#: inferred tool beside a confirmed one printed exactly like a confirmed one.
UNCONFIRMED_MARK = " (unconfirmed)"


def _measured(t: CoverageRollup | TacticCoverage) -> bool:
    """Whether any status-bearing claim exists here, INCLUDING withheld ones.

    `pending_review` rows are Covered/Partial claims #102 holds out of
    `covered`/`partial`. A tactic whose claims are all withheld has
    covered + partial + gap == 0, but it was assessed: it reads 0.0% beside its
    pending count, as the #102 note in `render_xlsx` intends -- not "never
    assessed", which is what "not measured" says."""
    return t.covered + t.partial + t.gap + t.pending_review > 0


def _pct_value(t: CoverageRollup | TacticCoverage) -> float | str:
    """The XLSX cell: the number, or NOT_ADDRESSABLE where nothing was claimed."""
    return t.coverage_pct if _measured(t) else NOT_ADDRESSABLE


def _pct_text(t: CoverageRollup | TacticCoverage) -> str:
    """The DOCX/PDF text: `12.5%`, or NOT_ADDRESSABLE where nothing was claimed."""
    return f"{t.coverage_pct}%" if _measured(t) else NOT_ADDRESSABLE


def coverage_pct_text(rollup: CoverageRollup) -> str:
    """The overall percentage as every surface of the deliverable states it --
    the renderers AND the stored `Deliverable.summary` line, so the results list
    cannot say 0.0% beside a PDF that says "not measured"."""
    return _pct_text(rollup)


def outside_assessed_text(rollup: CoverageRollup) -> str:
    """The two counts outside the assessed denominator, as every surface states
    them BESIDE the percentage (#554, the owner's decision): "Not verified" is
    never dropped, even at zero, so a reader can tell "none" from "not shown"."""
    return (
        f"Not verified {rollup.unable_to_determine}, "
        f"Outside control surface {rollup.outside_control_surface}"
    )


def _tools(value: list | None, unconfirmed: frozenset[str]) -> str:
    return "; ".join(
        f"{t}{UNCONFIRMED_MARK}" if t in unconfirmed else str(t) for t in (value or [])
    )


def _safe_text_row(ws, values: list) -> None:
    """Append a row whose strings may be model output or client input.

    openpyxl stores any string starting with "=" as a FORMULA, and raises on
    control characters -- so a rationale of `=HYPERLINK(...)` would become a
    live formula in a Kentro-branded workbook, and one stray control byte
    would fail the whole finalize. Illegal characters are dropped and a
    leading "=" is kept as text.
    """
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

    ws.append([ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v for v in values])
    for cell in ws[ws.max_row]:
        if isinstance(cell.value, str) and cell.value.startswith("="):
            cell.data_type = "s"


def _is_unscored(cov: AttackCoverage | None) -> bool:
    """The rollup's predicate (`analytics._validated`): no row, no status, or a
    status that is not a CoverageStatus. The Unscored sheet may not use a
    narrower one than the count it sits beside."""
    if cov is None or cov.status is None:
        return True
    try:
        CoverageStatus(cov.status)
    except ValueError:
        return True
    return False


def _tactic_name(tactic_id: str) -> str:
    for t in TACTICS:
        if t.id == tactic_id:
            return t.name
    return tactic_id


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------


def render_xlsx(ctx: AttackDeliverableContext) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    default = wb.active
    if default is not None:
        wb.remove(default)

    header_fill = PatternFill(start_color="FFEEF2F7", end_color="FFEEF2F7", fill_type="solid")
    bold = Font(bold=True)
    italic = Font(italic=True)

    # --- Heatmap Summary ---
    ws = wb.create_sheet("Heatmap Summary")
    # Client- and consultant-entered text, so through the same guard as the
    # model's rationale.
    _safe_text_row(ws, ["Engagement", ctx.client_legal_name])
    _safe_text_row(ws, ["Service", ctx.service_title])
    ws.append(["Assessment version", ctx.assessment.version])
    r = ctx.rollup
    ws.append(["Coverage %", _pct_value(r)])
    ws.append(
        [
            "Scored / Total",
            f"{ctx.rollup.scored_count}/{ctx.rollup.scored_count + ctx.rollup.unscored_count}",
        ]
    )
    # #102. Beside the percentage, never instead of it and never omitted: the
    # percentage is a ratio over what can currently be CLAIMED, so a withheld row
    # leaves both sides of it. An assessment whose every positive claim is
    # withheld renders 0.0% here, which without this line is indistinguishable
    # from a client who owns no controls at all.
    ws.append(["Pending review", ctx.rollup.pending_review])
    # #554: outside the assessed denominator, and beside it, never omitted.
    ws.append(["Not verified", ctx.rollup.unable_to_determine])
    ws.append(["Outside control surface", ctx.rollup.outside_control_surface])
    ws.append(["Coverage % means", COVERAGE_PCT_DEFINITION])
    ws.append(
        [
            f"Tools marked{UNCONFIRMED_MARK}",
            "Inferred from a near-match to the client's tool list and not yet "
            "confirmed by a consultant.",
        ]
    )
    for row in ws.iter_rows(min_row=1, max_row=10, min_col=1, max_col=1):
        for cell in row:
            cell.font = bold
    ws.append([])
    headers = [
        "Tactic",
        "Name",
        "Techniques",
        "Sub-techniques",
        "Covered",
        "Partial",
        "Gap",
        "N/A",
        "Outside control surface",
        "Not verified",
        "Unscored",
        "Pending review",
        "Coverage %",
    ]
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=ws.max_row, column=col)
        cell.font = bold
        cell.fill = header_fill
    for tc in ctx.rollup.by_tactic:
        ws.append(
            [
                tc.tactic_id,
                tc.tactic_name,
                tc.technique_count,
                tc.sub_technique_count,
                tc.covered,
                tc.partial,
                tc.gap,
                tc.not_applicable,
                tc.outside_control_surface,
                tc.unable_to_determine,
                tc.unscored,
                tc.pending_review,
                _pct_value(tc),
            ]
        )
    widths = [10, 28, 12, 14, 10, 10, 8, 8, 22, 13, 12, 15, 14]
    for w, col in zip(widths, range(1, len(widths) + 1), strict=True):
        ws.column_dimensions[get_column_letter(col)].width = w

    # --- Coverage (per-technique) ---
    ws2 = wb.create_sheet("Coverage")
    # `Pending review` sits beside `Status`, not instead of it. #102 withholds
    # the CLAIM while the status survives underneath — clearing the citation puts
    # the technique back into it — so a sheet that overwrote the status would
    # destroy the thing the rule is built on. Before this column the summary tab
    # read `Covered 0 / Pending review N` while this tab listed those same N rows
    # as `Covered`: one workbook, two answers, on adjacent tabs.
    # Rationale and the three tool lists are what the run actually produced --
    # measured 2026-09-23, 632 of 633 rows carried a rationale -- and the sheet
    # printed none of them. Notes stays: it has its own writer (the technique
    # panel's PATCH) and a consultant's note is not the model's rationale.
    headers2 = [
        "Technique",
        "Name",
        "Tactic(s)",
        "Type",
        "Status",
        "Pending review",
        "Rationale",
        "Detection tools",
        "Prevention tools",
        "Response tools",
        "Notes",
    ]
    ws2.append(headers2)
    for col in range(1, len(headers2) + 1):
        cell = ws2.cell(row=1, column=col)
        cell.font = bold
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="left", vertical="center")

    cov_by_code = {c.technique_code: c for c in ctx.coverage}
    for tech in TECHNIQUES:
        cov = cov_by_code.get(tech.id)
        tactic_str = ", ".join(_tactic_name(t) for t in tech.tactics)
        unconfirmed = uncleared_tools(cov.unconfirmed_citations) if cov else frozenset()
        _safe_text_row(
            ws2,
            [
                tech.id,
                tech.name,
                tactic_str,
                "sub" if tech.is_sub_technique else "parent",
                _status_or_unscored(cov.status if cov else None),
                "Yes" if tech.id in ctx.pending_codes else "",
                (cov.rationale if cov else None) or "",
                _tools(cov.detection_tools if cov else None, unconfirmed),
                _tools(cov.prevention_tools if cov else None, unconfirmed),
                _tools(cov.response_tools if cov else None, unconfirmed),
                (cov.notes if cov else None) or "",
            ],
        )
    widths2 = [14, 38, 28, 8, 12, 15, 60, 30, 30, 30, 40]
    for w, col in zip(widths2, range(1, len(widths2) + 1), strict=True):
        ws2.column_dimensions[get_column_letter(col)].width = w

    # --- Gaps ---
    ws3 = wb.create_sheet("Gaps")
    headers3 = ["Technique", "Name", "Tactic(s)", "Rationale", "Notes"]
    ws3.append(headers3)
    for col in range(1, len(headers3) + 1):
        cell = ws3.cell(row=1, column=col)
        cell.font = bold
        cell.fill = header_fill
    gap_rows = [c for c in ctx.coverage if c.status == CoverageStatus.GAP.value]
    gap_rows.sort(key=lambda c: c.technique_code)
    for cov in gap_rows:
        try:
            tech = technique_by_id(cov.technique_code)
            tactic_str = ", ".join(_tactic_name(t) for t in tech.tactics)
            name = tech.name
        except KeyError:
            tactic_str = ""
            name = cov.technique_code
        _safe_text_row(
            ws3, [cov.technique_code, name, tactic_str, cov.rationale or "", cov.notes or ""]
        )
    if not gap_rows:
        ws3.append(["—", "No gaps recorded", "", "", ""])
        ws3.cell(row=2, column=2).font = italic
    widths3 = [14, 38, 28, 60, 40]
    for w, col in zip(widths3, range(1, len(widths3) + 1), strict=True):
        ws3.column_dimensions[get_column_letter(col)].width = w

    # --- Unscored ---
    # Iterates the CATALOGUE, as the rollup does, so a technique with no row at
    # all is listed too and the row count equals `rollup.unscored_count`.
    ws4 = wb.create_sheet("Unscored")
    headers4 = ["Technique", "Name", "Tactic(s)"]
    ws4.append(headers4)
    for col in range(1, len(headers4) + 1):
        cell = ws4.cell(row=1, column=col)
        cell.font = bold
        cell.fill = header_fill
    unscored = [t for t in TECHNIQUES if _is_unscored(cov_by_code.get(t.id))]
    for tech in unscored:
        ws4.append([tech.id, tech.name, ", ".join(_tactic_name(t) for t in tech.tactics)])
    if not unscored:
        ws4.append(["—", "No unscored techniques", ""])
        ws4.cell(row=2, column=2).font = italic
    for w, col in zip([14, 38, 28], range(1, 4), strict=True):
        ws4.column_dimensions[get_column_letter(col)].width = w

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def render_docx(ctx: AttackDeliverableContext) -> bytes:
    """Word deliverable mirroring the PDF (Work Order C4)."""
    from app.docx_export import (
        add_heading,
        add_paragraphs,
        add_table,
        add_title,
        new_document,
        to_bytes,
    )

    doc = new_document(f"{ctx.service_title} — {ctx.client_legal_name}")
    add_title(doc, ctx.service_title, ctx.client_legal_name)

    add_heading(doc, "Coverage summary")
    add_paragraphs(
        doc,
        [
            "Overall coverage: " + coverage_pct_text(ctx.rollup),
            COVERAGE_PCT_DEFINITION,
            f"Scored: {ctx.rollup.scored_count}/"
            f"{ctx.rollup.scored_count + ctx.rollup.unscored_count}",
            f"Covered {ctx.rollup.covered}, Partial {ctx.rollup.partial}, "
            f"Gap {ctx.rollup.gap}, N/A {ctx.rollup.not_applicable}, "
            f"Pending review {ctx.rollup.pending_review}, " + outside_assessed_text(ctx.rollup),
        ],
    )

    add_heading(doc, "Per-tactic rollup")
    add_table(
        doc,
        # `Pending review` sits BEFORE `Coverage %` in all three renderers.
        # Withholding a row narrows `addressable`, so a per-tactic percentage can
        # read 100% over two withheld claims -- the count is what stops the
        # number being a lie, and XLSX carried it while these two did not.
        [
            "Tactic",
            "Name",
            "Covered",
            "Partial",
            "Gap",
            "N/A",
            "Outside",
            "Not verified",
            "Pending review",
            "Coverage %",
        ],
        [
            [
                tc.tactic_id,
                tc.tactic_name,
                tc.covered,
                tc.partial,
                tc.gap,
                tc.not_applicable,
                tc.outside_control_surface,
                tc.unable_to_determine,
                tc.pending_review,
                _pct_text(tc),
            ]
            for tc in ctx.rollup.by_tactic
        ],
    )

    gap_rows = [c for c in ctx.coverage if c.status == CoverageStatus.GAP.value]
    gap_rows.sort(key=lambda c: c.technique_code)
    gap_rows = gap_rows[:50]
    # THE HEADING SAYS WHAT THE TABLE IS, and the one it replaced asserted two
    # properties the table does not have (#480).
    #
    # It read `Top remediation gaps (N of M shown)`. "Top" implies a ranking, and
    # the sort key is `technique_code` -- alphabetical, so the first fifty codes
    # win and nothing about coverage, severity, tactic or effort enters the order.
    # "remediation" implies a plan, and the table has two columns, Code and
    # Technique, with no owner, effort, control or next step in it.
    # `routes/attack.py` records a real run at 607 gaps, so a client could receive
    # "Top remediation gaps (50 of 607 shown)" over fifty alphabetically-first
    # codes and reasonably conclude those were the ones that mattered most.
    #
    # Ranked remediation is real work, designed separately and blocked on making
    # long AI runs survive the browser. A false claim does not wait for it.
    #
    # The replacement says the three things the old one hid: the order, the
    # truncation, and that this is an inventory rather than a plan. It also says
    # WHICH FORMAT truncates -- the XLSX `Gaps` tab builds from the same list with
    # the same sort and NO slice, so the deliverable set does not withhold these
    # rows, this format does.
    #
    # THE TWINS ARE DELIBERATELY LEFT ALONE, and this is the checked answer rather
    # than the assumed one. `csf/exporters.py` and `zt/exporters.py` carry the
    # SAME heading text, so a sweep by string would have changed all three. They
    # are not the same defect:
    #
    #   ATT&CK  sorts by `technique_code` (alphabetical); columns Code, Technique.
    #   CSF     sorts by `-priority_score` then code; columns Code, Function,
    #           Subcategory, Current -> Target, Priority.
    #   ZT      sorts by `-priority_score` then code; columns Code, Pillar,
    #           Capability, Current -> Target, Priority.
    #
    # CSF and ZT genuinely rank, and their tables carry a target and a priority --
    # so "Top remediation gaps" describes what is there. ATT&CK ranks by nothing
    # and offers no remediation column, which is why it alone is wrong on BOTH
    # halves of its own heading. They also disclose their truncation in
    # `_gap_plan_caption` on the line below the heading; ATT&CK discloses its own
    # in the heading, which is why the count survives the rewording here.
    add_heading(
        doc,
        f"Gap techniques, first {len(gap_rows)} of {ctx.rollup.gap} by technique code"
        " (alphabetical, not ranked; the Gaps tab of the XLSX carries all of them)",
    )
    if not gap_rows:
        add_paragraphs(doc, ["No techniques flagged as Gap."])
    else:
        rows = []
        for cov in gap_rows:
            try:
                name = technique_by_id(cov.technique_code).name
            except KeyError:
                name = ""
            rows.append([cov.technique_code, name])
        add_table(doc, ["Code", "Technique"], rows)

    return to_bytes(doc)


def render_pdf(ctx: AttackDeliverableContext) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
    )

    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=f"{ctx.service_title} — {ctx.client_legal_name}",
        author="SHIELD by Kentro",
    )
    styles = getSampleStyleSheet()
    h1 = styles["Title"]
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], spaceBefore=14, spaceAfter=6)
    body = styles["BodyText"]

    story: list = []
    story.append(Paragraph(ctx.service_title, h1))
    story.append(Paragraph(ctx.client_legal_name, body))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Coverage summary", h2))
    story.append(
        Paragraph(
            f"Overall coverage: <b>{coverage_pct_text(ctx.rollup)}</b> · "
            f"Scored: <b>{ctx.rollup.scored_count}/"
            f"{ctx.rollup.scored_count + ctx.rollup.unscored_count}</b> · "
            f"Covered <b>{ctx.rollup.covered}</b>, "
            f"Partial <b>{ctx.rollup.partial}</b>, "
            f"Gap <b>{ctx.rollup.gap}</b>, "
            f"N/A <b>{ctx.rollup.not_applicable}</b>, "
            f"Pending review <b>{ctx.rollup.pending_review}</b>, "
            f"Not verified <b>{ctx.rollup.unable_to_determine}</b>, "
            f"Outside control surface <b>{ctx.rollup.outside_control_surface}</b>",
            body,
        )
    )
    story.append(Paragraph(COVERAGE_PCT_DEFINITION, body))

    story.append(Paragraph("Per-tactic rollup", h2))
    tactic_table_data: list[list] = [
        # See the DOCX table above: the count travels with the percentage.
        [
            "Tactic",
            "Name",
            "Covered",
            "Partial",
            "Gap",
            "N/A",
            "Outside",
            "Not verified",
            "Pending review",
            "Coverage %",
        ]
    ]
    for tc in ctx.rollup.by_tactic:
        tactic_table_data.append(
            [
                tc.tactic_id,
                tc.tactic_name,
                tc.covered,
                tc.partial,
                tc.gap,
                tc.not_applicable,
                tc.outside_control_surface,
                tc.unable_to_determine,
                tc.pending_review,
                _pct_text(tc),
            ]
        )
    # Ten columns since #554 added `Outside` and `Not verified` (eight since #102
    # added `Pending review`). A width list shorter than the header list silently
    # drops the last column's sizing in reportlab, so this has to move with the
    # table above it. The name column gave up the room.
    tactic_col_widths = [
        0.7 * inch,
        1.25 * inch,
        0.6 * inch,
        0.6 * inch,
        0.5 * inch,
        0.45 * inch,
        0.6 * inch,
        0.7 * inch,
        0.8 * inch,
        0.75 * inch,
    ]
    tactic_table = Table(
        tactic_table_data,
        colWidths=tactic_col_widths,
        repeatRows=1,
    )
    tactic_table.setStyle(_table_style())
    story.append(tactic_table)

    story.append(PageBreak())

    # Top-50 gap list.
    gap_rows = [c for c in ctx.coverage if c.status == CoverageStatus.GAP.value]
    gap_rows.sort(key=lambda c: c.technique_code)
    gap_rows = gap_rows[:50]
    story.append(
        Paragraph(
            # Same heading as the DOCX path, and they MUST move together -- see
            # the note at the DOCX site. Half-fixing one format is how #79 got
            # worse than the defect it replaced.
            f"Gap techniques, first {len(gap_rows)} of {ctx.rollup.gap} by technique"
            " code (alphabetical, not ranked; the Gaps tab of the XLSX carries all"
            " of them)",
            h2,
        )
    )
    if not gap_rows:
        story.append(Paragraph("No techniques flagged as Gap.", body))
    else:
        gap_table_data: list[list] = [["Code", "Technique"]]
        for cov in gap_rows:
            try:
                name = technique_by_id(cov.technique_code).name
            except KeyError:
                name = cov.technique_code
            gap_table_data.append([cov.technique_code, name])
        gap_table = Table(
            gap_table_data,
            colWidths=[1.1 * inch, 4.6 * inch],
            repeatRows=1,
        )
        gap_table.setStyle(_table_style())
        story.append(gap_table)

    doc.build(story)
    return out.getvalue()


def _table_style() -> TableStyle:
    from reportlab.lib import colors
    from reportlab.platypus import TableStyle

    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0e1220")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d6dae3")),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ]
    )


__all__ = ["AttackDeliverableContext", "build_context", "render_pdf", "render_xlsx"]
