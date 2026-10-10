"""ATT&CK Coverage deliverable renderers - PDF + XLSX.

XLSX sheets:
  - Heatmap Summary: tactic rollup (counts + coverage %)
  - Coverage:        per-technique status, rationale, the three tool lists
                     (unconfirmed citations marked) and notes (all 600+ rows)
  - Gaps:            techniques flagged as Gap, ordered by technique code
  - Unscored:        techniques with no usable status, listed by code
  Every catalogue technique code on the last three sheets links to its page on
  attack.mitre.org (#647).

PDF:
  Executive page with overall coverage % + per-tactic table, then the
  Gap list (top 50 entries).
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING

from app.attack.after import AFTER_LABEL, AFTER_LEGEND, AfterPlannedChanges, after_planned_changes
from app.attack.after import counts as after_counts
from app.attack.after import document_sentence as after_document_sentence
from app.attack.analytics import CoverageRollup, TacticCoverage
from app.attack.catalog import TACTICS, TECHNIQUES, all_codes, technique_by_id, technique_url
from app.attack.computed import (
    CANNOT_BE_PREVENTED_COLUMNS,
    CANNOT_BE_PREVENTED_HEADING,
    CANNOT_BE_PREVENTED_LEGEND,
    CANNOT_BE_PREVENTED_SENTENCE,
    IN_PLACE_LEGEND,
    IN_PLACE_TEXT,
    EffectiveRow,
    awaiting_review_count,
    awaiting_review_sentence,
)
from app.attack.coverage import ASSESSED, CoverageStatus, coverage_label
from app.attack.parents import PARENT_CHILDREN, is_computed_parent
from app.attack.partial_reasons import (
    TABLE_ORDER,
    WHY_PARTIAL_LEGEND,
    PartialReason,
    partial_reason_for_row,
)
from app.attack.pending import pending_codes as attack_pending_codes
from app.attack.pending import row_tools, uncleared_tools
from app.attack.retirement import (
    NO_PLAN,
    PLANNED_MARK,
    UNKNOWN_MARK,
    RetirementIndex,
    summarize,
    summary_sentences,
)
from app.attack.rules import parents_computed, statuses_computed
from app.attack.subset_drift import (
    OUTSIDE_LEGEND,
    OUTSIDE_MARK,
    SubsetCheck,
    fallback_sentence,
    not_checked_sentence,
    outside_rows_sentence,
    used_fallbacks,
)
from app.client_naming import org_display_name
from app.mode_stamp import (
    UNKNOWN_AI_MODE,
    AiModeStamp,
    add_docx_paragraph,
    add_xlsx_sheet,
    pdf_paragraph,
)
from app.models.attack_assessment import AttackAssessment, AttackCoverage
from app.pdf_export import pdf_escape, pdf_text
from app.xlsx_export import safe_text_row

if TYPE_CHECKING:
    from reportlab.platypus import TableStyle


@dataclass(frozen=True)
class AttackDeliverableContext:
    client_legal_name: str
    service_title: str
    assessment: AttackAssessment
    coverage: list[AttackCoverage]
    rollup: CoverageRollup
    #: #620 (D-094): whether this assessment renders under D-094's rules for
    #: computed parents (`attack/rules.py`). Derived once, in `build_context`,
    #: so both sheets read the same answer. Required: no default rule.
    parents_computed: bool
    #: Technique codes whose status the rollup is WITHHOLDING (#102).
    #:
    #: Derived once, here, and read by both the summary and the per-technique
    #: sheet. `rollup.pending_review` is only a count, so a renderer needing to
    #: mark individual rows would otherwise re-derive the set — a second source
    #: of truth for the same fact, which is the drift D-052 rejected.
    pending_codes: frozenset[str] = frozenset()
    #: #686 (D-105): which cited tools the client's Tech Debt consolidation plan
    #: retires, read at finalize. `NO_PLAN` marks nothing, which is also what an
    #: assessment for a client with no approved Tech Debt list renders.
    retirement: RetirementIndex = NO_PLAN
    #: #646: which mode drafted the AI suggestions behind this document. The
    #: default is "not recorded", never live: a context built without a lookup
    #: must not read as a clean one.
    ai_mode: AiModeStamp = UNKNOWN_AI_MODE
    #: #554 R3: whether `coverage` holds statuses computed from Detect / Prevent /
    #: Respond (`attack/rules.py::statuses_computed`). Derived in `build_context`.
    statuses_computed: bool = False
    #: #801: coverage after planned changes, from the retirement plan AS OF this
    #: context (finalize freezes it into the bytes); None where there is nothing
    #: to recount (`attack/after.py`). Derived in `build_context`.
    after: AfterPlannedChanges | None = None
    #: #851 / #889 (Q7): the security tool list check, read at finalize (the
    #: rendered bytes keep it) or live (the client dashboard). Not checked: the
    #: client has no list, only lists with no security tool, or only discarded
    #: lists, and every format says
    #: which (C5, C5b). Checked: the rows crediting a tool outside the list are
    #: counted (C1), each such tool is marked (C3), and a service that fell
    #: back to an earlier version is named with the version used (C9).
    #: None: nobody asked, and nothing is said either way.
    subset: SubsetCheck | None = None


def build_context(
    *,
    client_legal_name: str | None,
    service_title: str,
    assessment: AttackAssessment,
    coverage: Iterable[AttackCoverage],
    rollup: CoverageRollup,
    retirement: RetirementIndex = NO_PLAN,
    ai_mode: AiModeStamp = UNKNOWN_AI_MODE,
    subset: SubsetCheck | None = None,
) -> AttackDeliverableContext:
    rows = list(coverage)
    rule = parents_computed(assessment)
    computed = statuses_computed(assessment)
    # #554 R3: the caller's rollup was computed over `computed.effective_coverage`
    # rows, and these rows must be the SAME ones, or the per-technique sheet would
    # print stored statuses beside a percentage computed from the others.
    if computed and not all(isinstance(r, EffectiveRow) for r in rows):
        raise ValueError(
            "an assessment whose statuses are computed needs effective_coverage rows; "
            "build_context was given stored rows"
        )
    return AttackDeliverableContext(
        client_legal_name=org_display_name(client_legal_name),
        service_title=service_title,
        assessment=assessment,
        coverage=rows,
        rollup=rollup,
        # The SAME function the caller used to build `rollup`, over the same
        # rows, so the sheet and the summary cannot disagree about which
        # techniques are withheld.
        pending_codes=attack_pending_codes(rows, parents_computed=rule),
        parents_computed=rule,
        retirement=retirement,
        ai_mode=ai_mode,
        statuses_computed=computed,
        after=after_planned_changes(assessment, rows, retirement),
        subset=subset,
    )


def subset_sentences(ctx: AttackDeliverableContext) -> list[str]:
    """#851 / #889: the "not checked" sentence when the client has no security
    tool list to check against; the count of rows crediting a tool outside it
    (C1) when there are any; [] otherwise, and when nobody asked.

    The rows counted are this context's own rows, so the sentence counts the
    rows the document prints."""
    if ctx.subset is None:
        return []
    if not ctx.subset.checked:
        # R4: C5b where every list is empty, C5 otherwise.
        return [not_checked_sentence(ctx.subset.not_checked_reason)]
    rows = len(ctx.subset.outside_codes() & {c.technique_code for c in ctx.coverage})
    # R4 (C9): one sentence per Tech Debt service that fell back.
    return ([outside_rows_sentence(rows)] if rows else []) + [
        fallback_sentence(f) for f in used_fallbacks(ctx.subset.fallbacks)
    ]


def outside_tools(ctx: AttackDeliverableContext) -> frozenset[str]:
    """#889: the cited names to mark (C3); empty when nothing was checked."""
    return ctx.subset.outside_tools() if ctx.subset is not None else frozenset()


def _computed_leaf(cov: object) -> bool:
    """True for a row whose status #554 R3 computed (`EffectiveRow.is_computed`)."""
    return isinstance(cov, EffectiveRow) and cov.is_computed


def awaiting_review_text(ctx: AttackDeliverableContext) -> str | None:
    """#554 R3 (Q4): the disclosure every renderer prints beside the percentage,
    or None -- before R3, and when nothing awaits review."""
    if not ctx.statuses_computed:
        return None
    return awaiting_review_sentence(awaiting_review_count(ctx.coverage))


def in_place_cells(cov: object) -> list[str]:
    """#554 R3: the Coverage sheet's Detect / Prevent / Respond cells."""
    if not _computed_leaf(cov):
        return ["", "", ""]
    caps = cov.capabilities
    return [IN_PLACE_TEXT[caps.detect], IN_PLACE_TEXT[caps.prevent], IN_PLACE_TEXT[caps.respond]]


def cannot_be_prevented_counts(ctx: AttackDeliverableContext) -> list[tuple[str, int]]:
    """#554 R3: the "Techniques that cannot be prevented" table, by status in
    Covered / Partial / Gap order, zero rows omitted. Over the computed rows in
    the catalogue and not withheld: the population the rollup counts."""
    catalogue = {t.id for t in TECHNIQUES}
    counts: dict[str, int] = {}
    for cov in ctx.coverage:
        if (
            _computed_leaf(cov)
            and cov.capabilities.cannot_be_prevented
            and cov.technique_code in catalogue
            and cov.technique_code not in ctx.pending_codes
        ):
            counts[cov.status] = counts.get(cov.status, 0) + 1
    order = (CoverageStatus.COVERED, CoverageStatus.PARTIAL, CoverageStatus.GAP)
    return [(coverage_label(s), counts[s.value]) for s in order if counts.get(s.value)]


def _delivered_rows(ctx: AttackDeliverableContext) -> list[AttackCoverage]:
    """The rows whose tools the deliverable prints: a computed parent's own
    tools are not delivered (D-094), so they cannot carry a mark either."""
    return [
        c
        for c in ctx.coverage
        if not (ctx.parents_computed and is_computed_parent(c.technique_code))
    ]


#: The statuses that make a computed parent's coverage (#787 round 2, N2).
_COVERAGE_MAKING = frozenset({CoverageStatus.COVERED.value, CoverageStatus.PARTIAL.value})


def _evidence_rows(ctx: AttackDeliverableContext) -> list[SimpleNamespace]:
    """Each row with the tools its status rests on (#787 review, F4).

    `of_techniques` is the rollup's covered + partial, which COUNTS a computed
    parent (D-094). A parent has no tools of its own -- its status is its
    children's -- so its evidence is the union of its children's tools: when
    they retire, its coverage drops with theirs. Without this the numerator
    skipped parents while the denominator held them, a ratio over two
    populations.

    Only the children that MAKE its coverage: covered or partial, and not
    withheld -- the same population `summarize` counts for a standalone row
    (#787 round 2, N2). A gap, N/A or outside child can carry tools (the
    PATCH writes status and tools independently), and those tools are not
    what the parent's coverage rests on.

    The `pending_codes` clause CANNOT FIRE for a parent this sentence counts,
    and no test pins it: `attack/pending.py::pending_codes` withholds a
    covered or partial parent whenever ANY child is pending, so a counted
    parent has none. It is a ratchet against a looser parent rule there, and
    would be reachable again the day that rule stops withholding such a
    parent."""
    by_code = {c.technique_code: c for c in ctx.coverage}
    out: list[SimpleNamespace] = []
    for c in ctx.coverage:
        if ctx.parents_computed and is_computed_parent(c.technique_code):
            tools = [
                t
                for child in PARENT_CHILDREN.get(c.technique_code, ())
                if child in by_code
                and by_code[child].status in _COVERAGE_MAKING
                and child not in ctx.pending_codes
                for t in row_tools(by_code[child])
            ]
        else:
            tools = row_tools(c)
        out.append(
            SimpleNamespace(technique_code=c.technique_code, status=c.status, detection_tools=tools)
        )
    return out


def retirement_sentences(ctx: AttackDeliverableContext) -> list[str]:
    """#686: the count sentences, each only when non-zero; [] with no plan.
    `of_techniques` is this rollup's own covered + partial, and only rows inside
    it (not withheld, #102) can count, so the sentence agrees with the figure.
    Both sides count the same rows: see `_evidence_rows`."""
    return summary_sentences(
        summarize(
            _evidence_rows(ctx),
            ctx.retirement,
            counted_codes=[
                c.technique_code for c in ctx.coverage if c.technique_code not in ctx.pending_codes
            ],
            of_techniques=ctx.rollup.covered + ctx.rollup.partial,
        )
    )


def _row_reason(ctx: AttackDeliverableContext, cov: AttackCoverage | None) -> PartialReason | None:
    """#554 R1: what the client reads for why this row is Partial, or None.

    A computed parent's Partial is its children's only under #620's rules
    (`ctx.parents_computed`); an assessment approved before #620 scored its
    parents directly, so its parent reads like any other row."""
    if cov is None:
        return None
    # #842: the client dashboard's twin (`routes/clients.py`) calls the same
    # entry point, so a stored reason is checked against the computed line in both.
    return partial_reason_for_row(
        cov,
        computed_parent=ctx.parents_computed and is_computed_parent(cov.technique_code),
    )


def partial_reason_counts(ctx: AttackDeliverableContext) -> list[tuple[PartialReason, int]]:
    """#554 R1: the "Partial coverage, by reason" table, in `TABLE_ORDER`,
    zero rows omitted.

    Over the rows the rollup counts as Partial -- in the catalogue and not
    withheld (#102) -- so the counts add up to the Partial figure printed
    beside them, never to a second population. A mismatch RAISES: a table
    that does not add up is a wrong number in a client deliverable."""
    catalogue = {t.id for t in TECHNIQUES}
    counts: dict[PartialReason, int] = {}
    for cov in ctx.coverage:
        if cov.technique_code not in catalogue or cov.technique_code in ctx.pending_codes:
            continue
        reason = _row_reason(ctx, cov)
        if reason is not None:
            counts[reason] = counts.get(reason, 0) + 1
    if sum(counts.values()) != ctx.rollup.partial:
        raise ValueError(
            f"the Partial-by-reason table counts {sum(counts.values())} techniques "
            f"beside a Partial figure of {ctx.rollup.partial}"
        )
    return [(reason, counts[reason]) for reason in TABLE_ORDER if counts.get(reason)]


#: The count table's heading and columns, in the DOCX and the PDF.
PARTIAL_TABLE_HEADING = "Partial coverage, by reason"
PARTIAL_TABLE_COLUMNS = ["Reason", "What it means", "Techniques"]


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
#: COPIED to the admin heatmap card, `apps/web/src/components/admin/attack/AttackHeatmapCard.tsx`
#: (its CardDescription) -- change both.
COVERAGE_PCT_DEFINITION = (
    "Coverage % = (Covered + 0.5 x Partial) / (Covered + Partial + Gap). "
    "N/A, Outside control surface, Not verified, Unscored and Pending review "
    "techniques are outside it; Not verified and Outside control surface are "
    "counted beside it; "
    "'not measured' means no technique there has a Covered, Partial or Gap "
    "status, counting those pending review."
)

#: The definition as delivered BEFORE #621, for an assessment approved before
#: #620 (option (a), 2026-09-26): what was delivered keeps rendering.
COVERAGE_PCT_DEFINITION_RULE_1 = (
    "Coverage % = (Covered + 0.5 x Partial) / (Covered + Partial + Gap). "
    "N/A, Unscored and Pending review techniques are outside it; "
    "'not measured' means no technique there has a Covered, Partial or Gap "
    "status, counting those pending review."
)


def states_outside_counts(ctx: AttackDeliverableContext) -> bool:
    """Whether this deliverable carries #621's two counts outside the assessed
    denominator -- the rows, columns, sentence and definition that name them.

    Option (a), decided 2026-09-26: only where #620's rule set applies, read
    through `ctx.parents_computed`, which `build_context` takes from
    `attack/rules.py` -- the one reader, not a second copy of the rule. An
    assessment approved before #620 renders what was delivered, byte for byte
    (`tests/golden/outside_counts_rule1/`)."""
    return ctx.parents_computed


def _definition(ctx: AttackDeliverableContext) -> str:
    return COVERAGE_PCT_DEFINITION if states_outside_counts(ctx) else COVERAGE_PCT_DEFINITION_RULE_1


def _catalog_phrase(ctx: AttackDeliverableContext) -> str:
    """#419: what "Y" counts. The Risk register prints its own denominator
    ("ATT&CK coverage 12 of 700", the assessment's ROWS), so this one names the
    catalog it divides by rather than leaving the pair unexplained.

    `catalog_version` is NULL only for an assessment whose catalog was never
    recorded, which is never current, and finalize calls
    `require_current_catalog` before it builds this context -- so the
    versionless wording is unreachable through the routes today. It is written
    anyway rather than printing "ATT&CK None"."""
    version = ctx.assessment.catalog_version
    if version is None:
        return "techniques in the catalog this assessment was scored against"
    return f"techniques in the ATT&CK {version} catalog this assessment was scored against"


#: #419: the XLSX row naming the denominator, under #620's rules.
SCORED_OF_CATALOG_LABEL = (
    "Scored, of the techniques in the catalog this assessment was scored against"
)


def _scored_of(ctx: AttackDeliverableContext) -> str:
    """ "X of Y", under #620's rules (#419)."""
    return f"{ctx.rollup.scored_count} of {ctx.rollup.catalogue_count}"


def _scored_total(ctx: AttackDeliverableContext) -> str:
    """ "X/Y" scored, Y from `catalogue_count` under both rule sets and NOT gated:
    it differs from the scored + unscored delivered before #621 only by
    unjudged rows, which a rule-1 assessment cannot hold (nothing may write
    one), so the two agree there -- `tests/golden/outside_counts_rule1/` pins it."""
    return f"{ctx.rollup.scored_count}/{ctx.rollup.catalogue_count}"


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
    return sum(getattr(t, s.value) for s in ASSESSED) + t.pending_review > 0


def coverage_measured(t: CoverageRollup | TacticCoverage) -> bool:
    """`_measured`, for the API (#489): the ONE rule deciding whether a
    percentage is a measurement or "not measured", so the screens say what the
    deliverable says. The heatmap and the client dashboard emit it as
    `coverage_measured`; the web never re-derives it."""
    return _measured(t)


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
    # COPIED to the web as `outsideAssessedText`, `apps/web/src/lib/attack/outsideAssessed.ts`
    # -- change both.
    """The two counts outside the assessed denominator, as every surface states
    them BESIDE the percentage (#554, the owner's decision): "Not verified" is
    never dropped, even at zero, so a reader can tell "none" from "not shown"."""
    return (
        f"Not verified {rollup.unable_to_determine}, "
        f"Outside control surface {rollup.outside_control_surface}"
    )


def _tools(
    value: list | None,
    unconfirmed: frozenset[str],
    retirement: RetirementIndex = NO_PLAN,
    outside: frozenset[str] = frozenset(),
) -> str:
    # #686: the retirement mark stacks AFTER " (unconfirmed)"; #889 (C3): the
    # security tool list mark stacks after both.
    return "; ".join(
        f"{t}{UNCONFIRMED_MARK if t in unconfirmed else ''}{retirement.mark(t)}"
        f"{OUTSIDE_MARK if t in outside else ''}"
        for t in (value or [])
    )


def _safe_text_row(ws, values: list) -> None:
    """Append a row whose strings may be model output or client input: the
    shared guard, `app/xlsx_export.py::safe_text_row` (#972), which this
    function was the pattern for. Kept under this name for its call sites."""
    safe_text_row(ws, values)


_CATALOGUE_CODES = all_codes()


def _link_technique(ws, code: str) -> None:
    """Link the code in column A of the row just appended to MITRE's page (#647).

    Only a catalogue code is linked: a stored code the catalogue does not carry
    is printed unlinked rather than pointed at a URL nobody checked exists.
    The DOCX and PDF gap tables are left unlinked on purpose -- #647 asked for
    the workbook, and those two carry at most fifty codes that the XLSX Gaps
    sheet repeats with links."""
    if code not in _CATALOGUE_CODES:
        return
    cell = ws.cell(row=ws.max_row, column=1)
    cell.hyperlink = technique_url(code)
    cell.style = "Hyperlink"


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
    # #801 (X1): the figure after planned changes, beside today's, only where
    # there is something to recount.
    if ctx.after is not None:
        ws.append([AFTER_LABEL, _pct_value(ctx.after.rollup)])
        for sentence in after_counts(ctx.after):
            ws.append([sentence])
    # #419: the denominator named, under #620's rules only (option (a)); an
    # assessment approved before #620 renders the row it was delivered with.
    if states_outside_counts(ctx):
        ws.append([SCORED_OF_CATALOG_LABEL, _scored_of(ctx)])
    else:
        ws.append(
            [
                "Scored / Total",
                _scored_total(ctx),
            ]
        )
    # #102. Beside the percentage, never instead of it and never omitted: the
    # percentage is a ratio over what can currently be CLAIMED, so a withheld row
    # leaves both sides of it. An assessment whose every positive claim is
    # withheld renders 0.0% here, which without this line is indistinguishable
    # from a client who owns no controls at all.
    ws.append(["Pending review", ctx.rollup.pending_review])
    # #554 R3 (Q4): beside the percentage, only when something awaits review.
    if (awaiting := awaiting_review_text(ctx)) is not None:
        ws.append([awaiting])
    outside = states_outside_counts(ctx)
    if outside:
        # #554: outside the assessed denominator, and beside it, never omitted.
        ws.append(["Not verified", ctx.rollup.unable_to_determine])
        ws.append(["Outside control surface", ctx.rollup.outside_control_surface])
    ws.append(["Coverage % means", _definition(ctx)])
    if ctx.after is not None:
        ws.append(list(AFTER_LEGEND))  # #801 (X2)
    ws.append(
        [
            f"Tools marked{UNCONFIRMED_MARK}",
            "Inferred from a near-match to the client's tool list and not yet "
            "confirmed by a consultant.",
        ]
    )
    # #554 R1: the Coverage sheet's "Why partial" column, explained.
    ws.append(list(WHY_PARTIAL_LEGEND))
    # #554 R3: the Detect / Prevent / Respond columns, explained, and the
    # "cannot be prevented" value only when a row carries it.
    if ctx.statuses_computed:
        ws.append(list(IN_PLACE_LEGEND))
        if any(_computed_leaf(c) and c.capabilities.cannot_be_prevented for c in ctx.coverage):
            ws.append(list(CANNOT_BE_PREVENTED_LEGEND))
    # #686: a legend row only for a mark the Coverage sheet actually carries,
    # so a workbook with none of them renders as it did before.
    delivered_marks = {
        ctx.retirement.mark(t) for row in _delivered_rows(ctx) for t in row_tools(row)
    }
    if PLANNED_MARK in delivered_marks:
        ws.append(
            [
                f"Tools marked{PLANNED_MARK}",
                "Marked Cut, or Cut, covered by another tool, in the Tech Debt "
                "consolidation plan. Still deployed, so still counted toward coverage; "
                "this coverage drops when the tool is retired.",
            ]
        )
    if UNKNOWN_MARK in delivered_marks:
        ws.append(
            [
                f"Tools marked{UNKNOWN_MARK}",
                "Could not be matched to one Tech Debt capability, so whether it is planned "
                "for retirement is not known.",
            ]
        )
    # #889 (C4): a legend row only when the Coverage sheet carries the mark.
    marked = outside_tools(ctx)
    if any(t in marked for row in _delivered_rows(ctx) for t in row_tools(row)):
        ws.append(list(OUTSIDE_LEGEND))
    # #851: the third state, only when nothing could be checked; #889: the
    # count of rows crediting a tool outside the list.
    for sentence in subset_sentences(ctx):
        ws.append([sentence])
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=1):
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
        *(["Outside control surface", "Not verified"] if outside else []),
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
                *([tc.outside_control_surface, tc.unable_to_determine] if outside else []),
                tc.unscored,
                tc.pending_review,
                _pct_value(tc),
            ]
        )
    widths = [10, 28, 12, 14, 10, 10, 8, 8, *([22, 13] if outside else []), 12, 15, 14]
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
        # #554 R1, immediately after "Pending review".
        "Why partial",
        # #554 R3: what is in place, only where statuses are computed. An
        # assessment approved before R3 renders the columns it was delivered with.
        *(["Detect", "Prevent", "Respond"] if ctx.statuses_computed else []),
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
        # #620 round 2 (D-094): a computed parent's evidence is its children's. Its
        # own stored rationale and tools are what the model once wrote, and may
        # contradict the computed status, so the deliverable does not print them.
        # Derived here; the stored row is left alone.
        own = None if ctx.parents_computed and is_computed_parent(tech.id) else cov
        _safe_text_row(
            ws2,
            [
                tech.id,
                tech.name,
                tactic_str,
                "sub" if tech.is_sub_technique else "parent",
                _status_or_unscored(cov.status if cov else None),
                "Yes" if tech.id in ctx.pending_codes else "",
                reason.cell() if (reason := _row_reason(ctx, cov)) is not None else "",
                *(in_place_cells(cov) if ctx.statuses_computed else []),
                (own.rationale if own else None) or "",
                _tools(own.detection_tools if own else None, unconfirmed, ctx.retirement, marked),
                _tools(own.prevention_tools if own else None, unconfirmed, ctx.retirement, marked),
                _tools(own.response_tools if own else None, unconfirmed, ctx.retirement, marked),
                (cov.notes if cov else None) or "",
            ],
        )
        _link_technique(ws2, tech.id)
    widths2 = [
        *[14, 38, 28, 8, 12, 15, 60],
        *([16, 20, 16] if ctx.statuses_computed else []),
        *[60, 30, 30, 30, 40],
    ]
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
        # The Coverage sheet's twin (#620 round 2): no parent's own rationale.
        hide = ctx.parents_computed and is_computed_parent(cov.technique_code)
        rationale = "" if hide else (cov.rationale or "")
        _safe_text_row(ws3, [cov.technique_code, name, tactic_str, rationale, cov.notes or ""])
        _link_technique(ws3, cov.technique_code)
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
        _link_technique(ws4, tech.id)
    if not unscored:
        ws4.append(["—", "No unscored techniques", ""])
        ws4.cell(row=2, column=2).font = italic
    for w, col in zip([14, 38, 28], range(1, 4), strict=True):
        ws4.column_dimensions[get_column_letter(col)].width = w

    out = io.BytesIO()
    add_xlsx_sheet(wb, ctx.ai_mode)  # #646: the LAST sheet
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

    outside = states_outside_counts(ctx)
    doc = new_document(f"{ctx.service_title} — {ctx.client_legal_name}")
    add_title(doc, ctx.service_title, ctx.client_legal_name)
    add_docx_paragraph(doc, ctx.ai_mode)  # #646, under the title

    add_heading(doc, "Coverage summary")
    add_paragraphs(
        doc,
        [
            "Overall coverage: " + coverage_pct_text(ctx.rollup),
            # #801 (P1): only where there is something to recount.
            *(
                [after_document_sentence(_pct_text(ctx.after.rollup)), *after_counts(ctx.after)]
                if ctx.after is not None
                else []
            ),
            _definition(ctx),
            (
                # #419, under #620's rules only (option (a)).
                f"Scored: {_scored_of(ctx)} {_catalog_phrase(ctx)}"
                if outside
                else f"Scored: {_scored_total(ctx)}"
            ),
            f"Covered {ctx.rollup.covered}, Partial {ctx.rollup.partial}, "
            f"Gap {ctx.rollup.gap}, N/A {ctx.rollup.not_applicable}, "
            f"Pending review {ctx.rollup.pending_review}"
            + (", " + outside_assessed_text(ctx.rollup) if outside else ""),
            # #686: only when non-zero, so nothing changes without a plan.
            *retirement_sentences(ctx),
            # #851: the third state, only when nothing could be checked.
            *subset_sentences(ctx),
            # #554 R3 (Q4): only when something awaits review.
            *([awaiting] if (awaiting := awaiting_review_text(ctx)) is not None else []),
        ],
    )

    # #554 R1: why the Partials are partial, counted. Only when there is one.
    reason_counts = partial_reason_counts(ctx)
    if reason_counts:
        add_heading(doc, PARTIAL_TABLE_HEADING)
        add_table(
            doc,
            PARTIAL_TABLE_COLUMNS,
            [[reason.label, reason.sentence, n] for reason, n in reason_counts],
        )

    # #554 R3: the techniques that cannot be prevented, by status. Only when
    # there is one; the PDF carries the same table and they MUST move together.
    unpreventable = cannot_be_prevented_counts(ctx)
    if unpreventable:
        add_heading(doc, CANNOT_BE_PREVENTED_HEADING)
        add_table(doc, CANNOT_BE_PREVENTED_COLUMNS, [[label, n] for label, n in unpreventable])
        add_paragraphs(doc, [CANNOT_BE_PREVENTED_SENTENCE])

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
            *(["Outside", "Not verified"] if outside else []),
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
                *([tc.outside_control_surface, tc.unable_to_determine] if outside else []),
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

    outside = states_outside_counts(ctx)
    story: list = []
    story.append(pdf_text(ctx.service_title, h1))  # #775
    story.append(pdf_text(ctx.client_legal_name, body))  # #775
    story.append(pdf_paragraph(ctx.ai_mode, body))  # #646, under the title
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Coverage summary", h2))
    story.append(
        Paragraph(
            f"Overall coverage: <b>{coverage_pct_text(ctx.rollup)}</b> · "
            + (
                # #419, under #620's rules only (option (a)).
                f"Scored: <b>{ctx.rollup.scored_count}</b> of "
                # Escaped: a Paragraph is markup, and a bare "&" in "ATT&CK"
                # renders as "ATT&CK;". quote=False escapes exactly &, < and >,
                # what reportlab's markup needs; quotes are literal text there.
                f"{ctx.rollup.catalogue_count} " f"{pdf_escape(_catalog_phrase(ctx))} · "
                if outside
                else f"Scored: <b>{_scored_total(ctx)}</b> · "
            )
            + f"Covered <b>{ctx.rollup.covered}</b>, "
            f"Partial <b>{ctx.rollup.partial}</b>, "
            f"Gap <b>{ctx.rollup.gap}</b>, "
            f"N/A <b>{ctx.rollup.not_applicable}</b>, "
            f"Pending review <b>{ctx.rollup.pending_review}</b>"
            # #554: the shared sentence, not a copy of it, so the PDF cannot
            # drift from the DOCX, XLSX and stored summary. It carries no bold.
            + (f", {outside_assessed_text(ctx.rollup)}" if outside else ""),
            body,
        )
    )
    # #801 (P1): the DOCX's sentences, and they MUST move together.
    if ctx.after is not None:
        for sentence in [
            after_document_sentence(_pct_text(ctx.after.rollup)),
            *after_counts(ctx.after),
        ]:
            story.append(pdf_text(sentence, body))
    story.append(Paragraph(_definition(ctx), body))
    # #686: only when non-zero, so nothing changes without a plan.
    for sentence in retirement_sentences(ctx):
        story.append(pdf_text(sentence, body))
    # #851: the third state, only when nothing could be checked.
    for sentence in subset_sentences(ctx):
        story.append(pdf_text(sentence, body))
    # #554 R3 (Q4): only when something awaits review.
    if (awaiting := awaiting_review_text(ctx)) is not None:
        story.append(pdf_text(awaiting, body))

    # #554 R1: the same table as the DOCX, and they MUST move together.
    reason_counts = partial_reason_counts(ctx)
    if reason_counts:
        story.append(Paragraph(PARTIAL_TABLE_HEADING, h2))
        reason_table = Table(
            [
                PARTIAL_TABLE_COLUMNS,
                *[
                    [
                        pdf_text(reason.label, body),
                        pdf_text(reason.sentence, body),
                        str(n),
                    ]
                    for reason, n in reason_counts
                ],
            ],
            colWidths=[1.8 * inch, 4.4 * inch, 0.9 * inch],
            repeatRows=1,
        )
        reason_table.setStyle(_table_style())
        story.append(reason_table)

    # #554 R3: the DOCX's table, and they MUST move together.
    unpreventable = cannot_be_prevented_counts(ctx)
    if unpreventable:
        story.append(Paragraph(CANNOT_BE_PREVENTED_HEADING, h2))
        unpreventable_table = Table(
            [CANNOT_BE_PREVENTED_COLUMNS, *[[label, str(n)] for label, n in unpreventable]],
            colWidths=[2.0 * inch, 1.2 * inch],
            repeatRows=1,
            hAlign="LEFT",
        )
        unpreventable_table.setStyle(_table_style())
        story.append(unpreventable_table)
        story.append(pdf_text(CANNOT_BE_PREVENTED_SENTENCE, body))

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
            *(["Outside", "Not verified"] if outside else []),
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
                *([tc.outside_control_surface, tc.unable_to_determine] if outside else []),
                tc.pending_review,
                _pct_text(tc),
            ]
        )
    # Ten columns since #554 added `Outside` and `Not verified` (eight since #102
    # added `Pending review`). A width list shorter than the header list silently
    # drops the last column's sizing in reportlab, so this has to move with the
    # table above it. The name column gave up the room.
    tactic_col_widths = (
        [
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
        if outside
        # The eight widths delivered before #621 (option (a)).
        else [
            0.8 * inch,
            1.7 * inch,
            0.65 * inch,
            0.65 * inch,
            0.55 * inch,
            0.5 * inch,
            0.95 * inch,
            0.85 * inch,
        ]
    )
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
