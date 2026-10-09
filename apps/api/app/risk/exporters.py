"""Risk Register exporters (Work Order E): XLSX + PDF + Word.

Pure renderers over the register + entries. The XLSX carries every field plus
the blank client-governance columns; the PDF/Word are an executive snapshot
(KPI cards, axis counts, the 5x5 matrix, the tier/cadence legend) plus the full
table. Tool bytes are written by the route layer.
"""

from __future__ import annotations

import html
import io
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.client_naming import org_display_name
from app.mode_stamp import (
    UNKNOWN_AI_MODE_REGISTER,
    AiModeStamp,
    add_docx_paragraph,
    add_xlsx_sheet,
    pdf_paragraph,
)
from app.risk.engine import (
    IMPACT_ORDER,
    LIKELIHOOD_ORDER,
    Impact,
    Likelihood,
    RecommendedAction,
    RiskAxis,
    RiskTier,
    action_counts,
    axis_counts,
    cadence_for,
    matrix_counts,
    tier_counts,
)

#: #737, Gene's ruling (#736, 5986057990 item 13), verbatim.
DRAFT_MARKER = "Draft: not published"

# Blank columns the client uses for governance — SHIELD does not populate these.
_GOVERNANCE_COLUMNS = [
    "Owner",
    "Decision-maker",
    "Approval Date",
    "Acceptance Expiry",
    "Next Review",
    "Status",
]


@dataclass(frozen=True)
class RiskExportContext:
    client_legal_name: str
    version: int
    entries: list[Any]  # RiskEntry rows
    #: #403. `(service, scored, total)` per assessment feeding this register --
    #: how much of each was scored, and therefore how much the synthesis model
    #: was permitted to cite.
    #:
    #: THE CLIENT'S COPY IS WHY THIS IS HERE. The consultant's screen carries
    #: the same disclosure, and it is the deliverable that leaves the building:
    #: after #403 the Linked Techniques and Linked Controls columns go sparse
    #: wherever an assessment is largely unscored, which is CORRECT and reads
    #: as missing work. A register whose links thinned with no statement of why
    #: trades a silently wrong citation for a silently missing one.
    #:
    #: DEFAULTED EMPTY so every existing `build_context` caller keeps working,
    #: and empty renders NOTHING rather than a zero -- "0 of 0 scored" would be
    #: a concrete false claim about a client's assessments, where silence is
    #: merely an absence. `CLAUDE.md`: missing data defaults to UNCONFIRMED.
    #:
    #: #415: each row is `(service, scored, total, pending_review)`, the fourth
    #: the count of scored codes pending review (`attack/pending.py`), or None
    #: where the service has no review queue or the register predates the
    #: count. `build_context` accepts the older three-value rows as None.
    link_scope: tuple[tuple[str, int, int, int | None], ...] = ()
    #: #646: ALWAYS "not recorded" today, deliberately. `risk_synthesize` runs
    #: synchronously, with no `ai_runs` row, and the register records no
    #: correlation id, so nothing ties a register to the calls that drafted it;
    #: selecting the client's calls by purpose would read every register ever
    #: generated (the population defect #646's review rejected). It becomes a
    #: real answer when Risk runs through the run framework (#504).
    ai_mode: AiModeStamp = UNKNOWN_AI_MODE_REGISTER
    #: #844. `(findings, without_entry, with_several)` from the register's
    #: provenance, or None when nothing was recorded. None prints nothing --
    #: "every finding has one entry" over a register nobody counted would be a
    #: claim, where silence is only an absence.
    finding_counts: tuple[int, int, int] | None = None
    #: #737: True for every file rendered while the register is unpublished.
    #: Such a file is the consultant's copy, and says so on its face, because a
    #: file that leaves by email otherwise reads as final.
    draft: bool = False
    #: #737: `source_id -> state` for findings drafted from an input that was
    #: not released at generate; the source cell names it.
    source_states: dict[str, str] = field(default_factory=dict)
    #: #554 R3, option (b): ATT&CK codes whose computed status awaited review
    #: at generate; the source cell says so.
    review_pending: frozenset[str] = frozenset()
    #: #474. `(kind, framework, target, source, origin)` per service, sorted by
    #: `(kind, framework)` (`app/risk/baseline.py`), or None when the
    #: register did not record them -- which the summary STATES, because a
    #: deliverable that silently omits its baseline reads as having none.
    targets: tuple[tuple[str, str | None, int, str, str], ...] | None = None
    #: #915 (S3): the approved sentence for the DoD target cap, from
    #: `risk/zt_capped.py`, or None when nothing was lowered or recorded.
    zt_capped_target_note: str | None = None


def _enum_list(values, enum_cls):
    out = []
    for v in values:
        if not v:
            continue
        try:
            out.append(enum_cls(v))
        except (ValueError, KeyError):
            continue
    return out


def build_context(
    *,
    client_legal_name: str | None,
    version: int,
    entries: Sequence[Any],
    link_scope: Sequence[tuple[str, int, int] | tuple[str, int, int, int | None]] = (),
    finding_counts: tuple[int, int, int] | None = None,
    draft: bool = False,
    source_states: dict[str, str] | None = None,
    review_pending: frozenset[str] = frozenset(),
    targets: Sequence[tuple[str, str | None, int, str, str]] | None = None,
    zt_capped_target_note: str | None = None,
) -> RiskExportContext:
    return RiskExportContext(
        client_legal_name=org_display_name(client_legal_name),
        version=version,
        entries=list(entries),
        link_scope=tuple(
            (row[0], row[1], row[2], row[3] if len(row) > 3 else None) for row in link_scope
        ),
        finding_counts=finding_counts,
        draft=draft,
        source_states=dict(source_states or {}),
        review_pending=review_pending,
        targets=tuple(targets) if targets is not None else None,
        zt_capped_target_note=zt_capped_target_note,
    )


#: #844. What an unrated half prints as, in every cell of every format. A blank
#: cell reads as a value nobody filled in; this says no rating exists.
NOT_RATED = "Not rated"


def _rating(value: str | None) -> str:
    return value.replace("_", " ").title() if value else NOT_RATED


def _li(e: Any) -> str:
    return f"{_rating(e.likelihood)} x {_rating(e.impact)}"


def _consultant_rated(e: Any) -> bool:
    """A consultant EDITED this entry's rating and at least one half is present.

    Gene's ruling (a) on the half-set case (#736, 5986057990 item 10): an entry
    whose likelihood a consultant set, impact still unrated, is marked -- the
    half they set must not read as the model's. A FULLY cleared rating (both
    halves null) is unrated and carries no consultant credit (#854 review,
    F2). ONE predicate for the count line and the Origin column, so the two
    cannot disagree; the admin marker uses the same rule.
    """
    # `getattr`, because the renderers take duck-typed rows (`entries: list[Any]`)
    # and a row built before 0061's field existed carries no attribute. Absent
    # reads as "not edited", which is what every such row is: the edit path is
    # the field's only writer.
    return getattr(e, "rating_edited_at", None) is not None and (
        e.likelihood is not None or e.impact is not None
    )


def _origin(e: Any) -> str:
    """#844. `origin` describes who drafted the ENTRY; once a consultant has set
    the rating, printing `ai_generated` alone credits the model with a rating it
    never gave."""
    return f"{e.origin}; rating edited by consultant" if _consultant_rated(e) else e.origin


def _entries_noun(n: int) -> str:
    return "entry" if n == 1 else "entries"


def _joined(v) -> str:
    return ", ".join(v) if isinstance(v, list) else ""


def _source(
    e: Any, states: dict[str, str] | None = None, pending: frozenset[str] = frozenset()
) -> str:
    if e.source and e.source_id:
        cell = f"{e.source}:{e.source_id}"
    else:
        cell = e.source_id or e.source or ""
    # #737, Gene's ruling: a finding drafted from an unreleased input says so.
    # DRAFT copy, with the advisor.
    state = (states or {}).get(e.source_id or "")
    if state:
        # "an" before a vowel: "from an approved assessment" (coordinator,
        # #860). {state} is the input's stored status -- draft, submitted or
        # approved; a released input carries no label.
        article = "an" if state[:1].lower() in "aeiou" else "a"
        cell = f"{cell} (from {article} {state} assessment)"
    # #554 R3, option (b). DRAFT copy, with the advisor.
    if (e.source_id or "") in pending:
        cell = f"{cell} (computed status awaiting review)"
    return cell


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------


def render_xlsx(ctx: RiskExportContext) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    if ws is None:
        raise RuntimeError("openpyxl returned no active worksheet")
    ws.title = "Risk Register"

    header = [
        "ID",
        "Weakness",
        "Description",
        "Axis",
        "Source",
        "Linked Techniques",
        "Linked Controls",
        "Likelihood",
        "Impact",
        "Tier",
        "Compensating Controls",
        "Residual Risk",
        "Recommended Action",
        "Rationale",
        "Origin",
        "Trust",
        *_GOVERNANCE_COLUMNS,
    ]
    ws.append(header)
    fill = PatternFill(start_color="FFEEF2F7", end_color="FFEEF2F7", fill_type="solid")
    for col in range(1, len(header) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True)
        cell.fill = fill

    for i, e in enumerate(ctx.entries, start=1):
        ws.append(
            [
                i,
                e.title,
                e.description or "",
                (e.axis or "").title(),
                _source(e, ctx.source_states, ctx.review_pending),
                _joined(e.linked_techniques),
                _joined(e.linked_controls),
                _rating(e.likelihood),
                _rating(e.impact),
                _rating(e.tier),
                e.compensating_controls or "",
                e.residual_risk or "",
                (e.recommended_action or "").title(),
                e.rationale or "",
                _origin(e),
                e.trust or "",
                # Blank governance columns for the client.
                *["" for _ in _GOVERNANCE_COLUMNS],
            ]
        )

    # #403, the XLSX half. The PDF and Word carry this in `_summary_lines`;
    # it also appears in the XLSX "Summary" sheet above (#854 F6), because that
    # sheet IS `_summary_lines`. Kept here as well, deliberately: this sheet is
    # the per-assessment TABLE (scored, total, not citable) the prose line
    # summarises, and dropping either loses something the other cannot show.
    #
    # A SEPARATE SHEET, not extra columns: the disclosure is per ASSESSMENT and
    # the table is per ENTRY, so a column would repeat one assessment-level fact
    # on every row and invite reading it as a property of the entry beside it.
    #
    # Omitted entirely when nothing was recorded -- an empty sheet headed
    # "Scored coverage" with no rows reads as "nothing was scored", which is a
    # false claim rather than an absence.
    # #854 review, F6. The PDF and Word carry the summary disclosures (unrated,
    # consultant-rated, axis and action gaps, finding coverage, baseline); the
    # spreadsheet had none, while the admin copy says "the exported documents"
    # state them. The SAME `_summary_lines`, one line per row, so the three
    # formats cannot drift apart.
    summary = wb.create_sheet("Summary")
    if ctx.draft:
        summary.append([DRAFT_MARKER])
    summary.append(["Summary"])
    summary.cell(row=1, column=1).font = Font(bold=True)
    for line in _summary_lines(ctx):
        summary.append([line])

    if ctx.link_scope:
        sheet = wb.create_sheet("Scored coverage")
        sheet.append(["Assessment", "Rows scored", "Rows total", "Not citable", "Pending review"])
        for col in range(1, 6):
            cell = sheet.cell(row=1, column=col)
            cell.font = Font(bold=True)
            cell.fill = fill
        for service, scored, total, pending in sorted(ctx.link_scope):
            sheet.append(
                [
                    scope_label(service),
                    scored,
                    total,
                    total - scored,
                    _pending_cell(service, pending),
                ]
            )
        sheet.append([])
        sheet.append(
            [
                # #554: "Not verified" is the ATT&CK deliverable's word for
                # these rows. Two client documents naming the same rows two
                # ways would read as two different populations.
                "Technique and control links are drawn only from rows an "
                "assessment has scored, so unscored rows and techniques marked "
                "Not verified cannot appear in the Linked Techniques or Linked "
                "Controls columns."
            ]
        )
        # #415: the pending-review sentence, or that it was not recorded.
        for line in _pending_review_lines(ctx):
            sheet.append([line])

    out = io.BytesIO()
    add_xlsx_sheet(wb, ctx.ai_mode)  # #646: the LAST sheet
    wb.save(out)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Shared summary used by PDF + DOCX
# ---------------------------------------------------------------------------


#: Service tokens as the API spells them, for the #403 scored-coverage
#: disclosure.
#:
#: DUPLICATED, unavoidably: `SERVICE_LABELS` in
#: `apps/web/src/lib/risk/labels.ts` is the one web copy of the target and
#: scope-key labels; `lib/risk/inputs.ts` and `components/admin/zt/ZtWorkspace.tsx`
#: repeat these strings (#946). There is no way to share a Python
#: dict with TSX, so this is a synchronization rather than a derivation --
#: which `CLAUDE.md` says to avoid where possible and otherwise to NAME, with
#: the window stated.
#:
#: The window: a label changed in one place and not the other makes the client's
#: PDF and the screens disagree about which assessment a count belongs to.
#: Cosmetic rather than numeric -- the counts themselves come from one parser --
#: but it is the kind of drift nobody notices. Change both.
_SERVICE_LABELS = {
    "attack": "ATT&CK coverage",
    "csf": "NIST CSF",
    "zt": "Zero Trust",
}

#: The ZT frameworks by the names the ZT deliverable already prints
#: (`app/zt/exporters.py`), so the Risk Register names a framework the way the
#: client's own Zero Trust report does (advisor, #736 6019425290, Q3).
#: `ZT_FRAMEWORK_NAMES` in `apps/web/src/lib/risk/labels.ts` is the one web copy
#: of the target and scope-key labels; `lib/risk/inputs.ts` and
#: `components/admin/zt/ZtWorkspace.tsx` repeat these strings (#946). Change
#: both.
ZT_FRAMEWORK_NAMES = {
    "cisa_ztmm_2_0": "CISA ZTMM 2.0",
    "dod_ztra": "DoD ZT Reference Architecture",
}


def scope_label(key: str) -> str:
    """A scored-coverage row's label (#876). "zt" while a kind has one source;
    "zt:cisa_ztmm_2_0" -> "Zero Trust (CISA ZTMM 2.0)" when it has two. An
    unknown key renders as itself, for the reason `_link_scope_lines` gives."""
    if key in _SERVICE_LABELS:
        return _SERVICE_LABELS[key]
    kind, _, qualifier = key.partition(":")
    if kind in _SERVICE_LABELS and qualifier in ZT_FRAMEWORK_NAMES:
        return f"{_SERVICE_LABELS[kind]} ({ZT_FRAMEWORK_NAMES[qualifier]})"
    return key


def _link_scope_lines(ctx: RiskExportContext) -> list[str]:
    """The #403 disclosure, for the client's PDF and Word deliverable.

    Reads as prose beside the other summary lines rather than as a table: the
    reader is a client executive, and "23 of 106 subcategories scored" is the
    sentence that explains why the Linked Controls column is mostly empty.

    An unknown service token renders as itself. The alternative -- skipping a
    row this dict has no label for -- would drop a whole assessment out of a
    disclosure, which is the failure the disclosure exists to prevent; an ugly
    token is merely ugly. Same call as the web banner makes.

    Returns `[]` for an empty scope, so a register built before this was
    recorded prints nothing instead of a fabricated zero.
    """
    if not ctx.link_scope:
        return []
    parts = [
        f"{scope_label(service)} {scored} of {total}"
        for service, scored, total, _pending in sorted(ctx.link_scope)
    ]
    return [
        "Scored coverage available to link — " + ", ".join(parts),
        (
            # #554: the same word the ATT&CK deliverable uses; see the XLSX.
            "Technique and control links are drawn only from rows an assessment "
            "has scored, so unscored rows and techniques marked Not verified "
            "cannot appear in the two Linked columns."
        ),
    ]


#: #415, ruling (b) (#736 6072976838): a register whose record holds no
#: pending-review count says so, rather than reading as "none pending".
PENDING_REVIEW_NOT_RECORDED = (
    "Whether any linked technique was pending review was not recorded for this register."
)


def _is_attack_scope(service: str) -> bool:
    """The ATT&CK row of a scope record, by the kind its scope key names (the
    same reading `scope_label` makes). Only ATT&CK has a review queue."""
    return service.partition(":")[0] == "attack"


def _attack_pending(ctx: RiskExportContext) -> int | None:
    """#415. The ATT&CK pending-review count, or None when not recorded: a
    register with no ATT&CK scope row (one generated before #403) or one whose
    ATT&CK row predates the count."""
    for service, _scored, _total, pending in ctx.link_scope:
        if _is_attack_scope(service):
            return pending
    return None


def _pending_review_lines(ctx: RiskExportContext) -> list[str]:
    """#415, the approved copy (#736 6069843323 C1; (a) and (b) in 6072976838).

    Nothing at n = 0; the count when some are pending; the not-recorded
    sentence when the register holds no count."""
    n = _attack_pending(ctx)
    if n is None:
        return [PENDING_REVIEW_NOT_RECORDED]
    if n == 0:
        return []
    if n == 1:
        return [
            "1 scored ATT&CK technique is pending review and is not linked: its status "
            "rests on evidence not yet confirmed."
        ]
    return [
        f"{n} scored ATT&CK techniques are pending review and are not linked: their "
        "status rests on evidence not yet confirmed."
    ]


def _pending_cell(service: str, pending: int | None) -> int | str:
    """#415, C2: the "Pending review" column. ATT&CK shows its count, 0
    included (ruling (a)); CSF and ZT have no review queue and read "n/a"; an
    ATT&CK row from before the count reads "not recorded" (#736 6073312727),
    because a blank cell in a column that always shows a number reads as 0."""
    if not _is_attack_scope(service):
        return "n/a"
    return "not recorded" if pending is None else pending


def _summary_lines(ctx: RiskExportContext) -> list[str]:
    tiers = _enum_list((e.tier for e in ctx.entries), RiskTier)
    axes = _enum_list((e.axis for e in ctx.entries), RiskAxis)
    actions = _enum_list((e.recommended_action for e in ctx.entries), RecommendedAction)
    tc = tier_counts(tiers)
    ac = axis_counts(axes)
    acts = action_counts(actions)
    crit_high = tc["critical"] + tc["high"]
    total = len(ctx.entries)
    return [
        # #330 TWIN, DELIBERATELY NOT FOLLOWED HERE -- and the reason is the ranking,
        # not the effort.
        #
        # `RiskRegisterDashboard` (admin) now discloses when the generate loop intended
        # more rows than reached storage, dividing by the INTENDED tally. This surface
        # still divides by the post-loss count and says nothing.
        #
        # Unreachable today, re-measured rather than inherited: `RiskEntry` is
        # constructed in exactly one place (`generate` in routes/risk.py) and deleted
        # nowhere under `apps/api/app`, so no writer can produce the divergent state.
        # No client is misled.
        #
        # Recorded because the ratchet went to the CONSULTANT and not to the CLIENT,
        # which inverts this repo's stated priority -- a false assurance delivered to a
        # client is the unrecoverable one. Tracked in #355; an unstated exemption reads
        # as an oversight to whoever runs the twin sweep next.
        f"Total entries: {total}",
        f"Critical + High: {crit_high}",
        # #844. The count `Critical + High` cannot see. Untiered is counted as
        # `total - len(tiers)`, the SAME filter the tier counts above use, so
        # the two cannot disagree about which rows were left out.
        *_unrated_lines(total, total - len(tiers)),
        *_consultant_rated_lines(ctx),
        f"By axis — detection {ac['detection']}, prevention "
        f"{ac['prevention']}, response {ac['response']}",
        *_missing_line(total, total - len(axes), "no axis"),
        "By recommended action — " + ", ".join(f"{k} {v}" for k, v in acts.items() if v),
        *_missing_line(total, total - len(actions), "no recommended action"),
        *_finding_lines(ctx.finding_counts),
        *_target_lines(ctx.targets),
        *_link_scope_lines(ctx),
        *_pending_review_lines(ctx),
        # #915 (S3), beside the scored-coverage disclosure; one line, or none.
        *([ctx.zt_capped_target_note] if ctx.zt_capped_target_note else []),
    ]


#: #474. Which word each kind's target takes.
_TARGET_UNITS = {"csf": "tier", "zt": "stage"}


def target_label(kind: str, framework: str | None, *, name_framework: bool) -> str:
    """#474. What a target line calls a service: its kind's label, and the ZT
    framework only when `name_framework` (the record holds more than one ZT
    entry, Q3, ruling 2a). Built from the record's `kind` and `framework`,
    never from a scope key.

    `kind` and `framework` are the reader's validated values, so a missing
    label raises rather than printing a token. Two services of one kind AND
    framework cannot reach here (generate refuses them, 409
    `risk_register_duplicate_inputs`, and the reader refuses a record holding
    two). If per-service keying (post-MVP) lifts that refusal, a third
    discriminator, the service title, is needed here.
    """
    label = _SERVICE_LABELS[kind]
    if name_framework and framework is not None:
        return f"{label} ({ZT_FRAMEWORK_NAMES[framework]})"
    return label


def _target_lines(
    targets: tuple[tuple[str, str | None, int, str, str], ...] | None,
) -> list[str]:
    """#474. Which target each service's findings were measured against.

    Two states: recorded (one line per service, in the reader's order) and not
    recorded (one line saying so). A record with no CSF or ZT entry cannot
    occur: generate requires a CSF or ZT input, and the reader reads an empty
    record as not recorded (ruling 2d). ATT&CK has no target and never
    appears here.
    """
    if targets is None:
        return [
            "The targets these findings were measured against were not recorded for "
            "this register."
        ]
    name_framework = sum(1 for kind, *_ in targets if kind == "zt") > 1
    lines = []
    for kind, framework, target, source, _origin in targets:
        label = target_label(kind, framework, name_framework=name_framework)
        unit = _TARGET_UNITS[kind]
        if source == "client":
            why = "the engagement target when this register was generated"
        elif source == "default":
            why = "SHIELD's default: no engagement target was set"
        else:
            why = "SHIELD's default: the engagement target could not be used"
        lines.append(f"{label} findings are measured against target {unit} {target}, {why}.")
    return lines


def _finding_lines(counts: tuple[int, int, int] | None) -> list[str]:
    """#844. Printed only when a finding has no entry or several: the register
    is drafted one entry per finding, so the normal case needs no sentence."""
    if counts is None:
        return []
    total, without, several = counts
    if without == 0 and several == 0:
        return []
    return [
        f"{total} {'finding' if total == 1 else 'findings'} went into this register; "
        f"{without} {'has' if without == 1 else 'have'} no entry and "
        f"{several} {'has' if several == 1 else 'have'} more than one."
    ]


def _unrated_lines(total: int, unrated: int) -> list[str]:
    """#844, three values: some unrated (stated with its population), none
    unrated (stated, so it is not the same as nobody counting), and an empty
    register (nothing to say either way)."""
    if total == 0:
        return []
    if unrated == 0:
        return ["Every entry is rated."]
    one = unrated == 1
    return [
        f"Not rated: {unrated} of {total} entries "
        f"{'has' if one else 'have'} no likelihood or impact, so "
        f"{'it has' if one else 'they have'} no tier and "
        f"{'is' if one else 'are'} not in the matrix or in Critical + High."
    ]


def _consultant_rated_lines(ctx: RiskExportContext) -> list[str]:
    edited = sum(1 for e in ctx.entries if _consultant_rated(e))
    if edited == 0:
        return []
    return [f"Ratings edited by a consultant: {edited} of {len(ctx.entries)} entries."]


def _missing_line(total: int, missing: int, phrase: str) -> list[str]:
    """#313's twin in the deliverable. The axis and action lines filter
    independently of the tier, so each states its own gap; the client
    dashboard has said this since #313 and the exports did not."""
    if missing == 0:
        return []
    one = missing == 1
    return [
        f"{missing} of {total} entries {'has' if one else 'have'} {phrase} and "
        f"{'is' if one else 'are'} not in the line above."
    ]


def _legend_rows() -> list[list[str]]:
    return [[t.value.title(), cadence_for(t)] for t in RiskTier]


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def render_pdf(ctx: RiskExportContext) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=f"Risk Register — {ctx.client_legal_name}",
        author="SHIELD by Kentro",
    )
    styles = getSampleStyleSheet()
    h1 = styles["Title"]
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], spaceBefore=14, spaceAfter=6)
    body = styles["BodyText"]

    def _grid(data, widths):
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d6dae3")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return t

    def _text(s: str, style) -> Paragraph:
        """#862. `Paragraph` parses its input as markup: unescaped, "ATT&CK"
        printed as "ATT&CK;", "<Labs>" was dropped in silence, and "</b>" in a
        client's name made the export fail. `html.escape(s, quote=False)`
        escapes exactly `&`, `<` and `>`, the three characters the markup
        reads, so every string prints as itself. Here and not in
        `_summary_lines`, which also feeds the DOCX and XLSX: those are plain
        text and would print `&amp;`."""
        return Paragraph(html.escape(s, quote=False), style)

    story: list = [
        _text(f"Risk Register (v{ctx.version})", h1),
        _text(ctx.client_legal_name, body),
        pdf_paragraph(ctx.ai_mode, body),  # #646, under the title
        *([_text(DRAFT_MARKER, body)] if ctx.draft else []),
        Spacer(1, 0.2 * inch),
        _text("Summary", h2),
    ]
    for line in _summary_lines(ctx):
        story.append(_text(line, body))

    story.append(_text("Likelihood x Impact matrix", h2))
    matrix = matrix_counts(
        [
            (Likelihood(e.likelihood), Impact(e.impact))
            for e in ctx.entries
            if e.likelihood in Likelihood._value2member_map_
            and e.impact in Impact._value2member_map_
        ]
    )
    # Build a 5x5 grid of counts (rows = likelihood high->low, cols = impact).
    grid: list[list] = [[""] + [im.value.title() for im in IMPACT_ORDER]]
    for lk in reversed(LIKELIHOOD_ORDER):
        row = [lk.value.replace("_", " ").title()]
        for im in IMPACT_ORDER:
            cell = next(c for c in matrix if c.likelihood == lk.value and c.impact == im.value)
            row.append(str(cell.count))
        grid.append(row)
    story.append(_grid(grid, [1.1 * inch] + [0.9 * inch] * 5))
    # #844. Counted from the SAME predicate the matrix filters on, so the note
    # and the grid cannot disagree about which entries are missing from it.
    left_out = len(ctx.entries) - sum(c.count for c in matrix)
    if left_out:
        story.append(
            _text(
                f"{left_out} unrated {_entries_noun(left_out)} "
                f"{'is' if left_out == 1 else 'are'} not in this matrix.",
                body,
            )
        )

    story.append(_text("Tier legend (review cadence)", h2))
    story.append(_grid([["Tier", "Suggested cadence"], *_legend_rows()], [1.2 * inch, 5.0 * inch]))

    story.append(PageBreak())
    story.append(_text("Register", h2))
    table = [["ID", "Weakness", "Axis", "L x I", "Tier", "Recommended", "Linked Source"]]
    for i, e in enumerate(ctx.entries, start=1):
        table.append(
            [
                str(i),
                e.title,
                (e.axis or "").title(),
                _li(e),
                _rating(e.tier),
                (e.recommended_action or "").title(),
                _source(e, ctx.source_states, ctx.review_pending),
            ]
        )
    story.append(
        _grid(
            table,
            [0.4 * inch, 2.0 * inch, 0.8 * inch, 1.1 * inch, 0.8 * inch, 1.0 * inch, 1.2 * inch],
        )
    )
    doc.build(story)
    return out.getvalue()


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def render_docx(ctx: RiskExportContext) -> bytes:
    from app.docx_export import (
        add_heading,
        add_paragraphs,
        add_table,
        add_title,
        new_document,
        to_bytes,
    )

    doc = new_document(f"Risk Register — {ctx.client_legal_name}")
    add_title(doc, f"Risk Register (v{ctx.version})", ctx.client_legal_name)
    add_docx_paragraph(doc, ctx.ai_mode)  # #646, under the title
    if ctx.draft:
        add_paragraphs(doc, [DRAFT_MARKER])

    add_heading(doc, "Summary")
    add_paragraphs(doc, _summary_lines(ctx))

    add_heading(doc, "Tier legend (review cadence)")
    add_table(doc, ["Tier", "Suggested cadence"], _legend_rows())

    add_heading(doc, "Register")
    rows = [
        [
            str(i),
            e.title,
            (e.axis or "").title(),
            _li(e),
            _rating(e.tier),
            (e.recommended_action or "").title(),
            _source(e, ctx.source_states, ctx.review_pending),
        ]
        for i, e in enumerate(ctx.entries, start=1)
    ]
    add_table(
        doc, ["ID", "Weakness", "Axis", "L x I", "Tier", "Recommended", "Linked Source"], rows
    )

    return to_bytes(doc)
