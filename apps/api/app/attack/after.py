"""ATT&CK coverage AFTER planned changes (#801): one figure, one set of words.

Gene's decision on #801 (with #736): a tool marked for retirement in the
client's latest approved or released Tech Debt list -- Cut, or "Cut, covered by
another tool", `models/capability.py::RETIRING_DISPOSITIONS` -- does not count
in a SECOND coverage figure, "after planned changes": R3's own computation
(`computed.effective_coverage(..., retirement=index)`) recounted, labelled "if
these tools are cut and nothing else changes". Today's figure is unchanged.

The figure exists only where there is something to recount:
  * an assessment whose statuses are COMPUTED (R3). One approved before R3
    renders its stored statuses, so there is nothing to recount;
  * a client WITH a consolidation plan. Without one there are no planned
    changes, so no second figure is shown rather than one equal to today.

Every surface takes the figure and its sentences from here (approved by the
advisor 05:05Z on #801), so the dashboard, the admin card, the three documents
and the finalize summary cannot disagree.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.attack.analytics import CoverageRollup
from app.attack.analytics import compute as compute_rollup
from app.attack.catalog import all_codes
from app.attack.computed import EffectiveRow, InPlace, effective_coverage
from app.attack.pending import pending_codes
from app.attack.retirement import Retirement, RetirementIndex
from app.attack.rules import parents_computed, statuses_computed

#: Higher is better; a drop in rank is "would score lower".
_RANK = {"covered": 2, "partial": 1, "gap": 0}

#: X1 and X2: the XLSX row label, and its legend row.
AFTER_LABEL = "Coverage % after planned changes"
AFTER_LEGEND = (
    "Coverage % after planned changes means",
    "The same calculation with the tools marked for planned retirement removed: if "
    "these tools are cut and nothing else changes.",
)
#: D2: the dashboard reads the plan live.
CURRENT_PLAN_SENTENCE = "This uses the current consolidation plan."


@dataclass(frozen=True)
class AfterPlannedChanges:
    rollup: CoverageRollup
    #: Techniques whose status after planned changes is below today's (A1).
    lower: int
    #: Computed techniques where a tool whose retirement status is unknown is
    #: what leaves a capability awaiting review after planned changes (A3).
    unknown: int


class _UnknownStays(RetirementIndex):
    """`retirement` with every UNKNOWN verdict read as not retiring: the
    counterfactual A3 is measured against, never a figure any surface shows."""

    def __init__(self, retirement: RetirementIndex) -> None:
        super().__init__(has_plan=retirement.has_plan, by_key=retirement.by_key)

    def state(self, tool: str) -> Retirement | None:
        s = super().state(tool)
        return Retirement.NOT_RETIRING if s is Retirement.UNKNOWN else s


def _stored(rows: Iterable[Any]) -> list[Any]:
    """The stored rows under any `EffectiveRow` the caller already built."""
    return [r._row if isinstance(r, EffectiveRow) else r for r in rows]


def after_planned_changes(
    assessment: Any, rows: Iterable[Any], retirement: RetirementIndex
) -> AfterPlannedChanges | None:
    """The figure, or None where there is nothing to recount (see the module)."""
    if not statuses_computed(assessment) or not retirement.has_plan:
        return None
    stored = _stored(rows)
    today = effective_coverage(assessment, stored)
    after = effective_coverage(assessment, stored, retirement=retirement)
    valid = all_codes()
    rollup = compute_rollup(
        {r.technique_code: r.status for r in after if r.technique_code in valid},
        pending_codes(after, parents_computed=parents_computed(assessment)),
    )
    by_code = {r.technique_code: r for r in today}
    lower = sum(
        1
        for r in after
        if r.technique_code in valid
        and r.status in _RANK
        and by_code[r.technique_code].status in _RANK
        and _RANK[r.status] < _RANK[by_code[r.technique_code].status]
    )
    # A3 counts a technique only where the UNKNOWN retirement is what made the
    # difference: with those tools treated as staying, a capability awaiting
    # review would be in place. A pending citation also leaves a capability
    # awaiting review, and that is not an unknown retirement (#813 review).
    staying = {
        r.technique_code: r
        for r in effective_coverage(assessment, stored, retirement=_UnknownStays(retirement))
    }
    unknown = 0
    for r in after:
        if r.technique_code not in valid or not r.is_computed:
            continue
        if_staying = staying[r.technique_code].capabilities
        pairs = zip(if_staying.judged(), r.capabilities.judged(), strict=True)
        if any(s is InPlace.IN_PLACE and a is InPlace.AWAITING_REVIEW for s, a in pairs):
            unknown += 1
    return AfterPlannedChanges(rollup=rollup, lower=lower, unknown=unknown)


def figure_sentence(pct_text: str) -> str:
    """D1 (the client dashboard) and H1 (the admin heatmap card)."""
    return (
        f"After planned changes: {pct_text}, if the tools marked for planned retirement "
        "are cut and nothing else changes."
    )


def document_sentence(pct_text: str) -> str:
    """P1: the PDF's and DOCX's coverage summary."""
    return (
        f"Coverage after planned changes: {pct_text}, if the tools marked for planned "
        "retirement are cut and nothing else changes."
    )


def summary_sentence(pct_text: str) -> str:
    """F1: appended to the finalize results-list line."""
    return f"After planned changes: {pct_text}."


def lower_sentence(n: int) -> str | None:
    """A1, or None at zero."""
    if n == 0:
        return None
    if n == 1:
        return "1 technique would score lower."
    return f"{n} techniques would score lower."


def unknown_sentence(n: int) -> str | None:
    """A3, or None at zero."""
    if n == 0:
        return None
    if n == 1:
        return (
            "1 technique cites tools whose retirement status is unknown; it is scored "
            "after planned changes as if those tools were not in place."
        )
    return (
        f"{n} techniques cite tools whose retirement status is unknown; they are scored "
        "after planned changes as if those tools were not in place."
    )


def counts(figure: AfterPlannedChanges) -> list[str]:
    """A1 and A3, each only when non-zero."""
    return [s for s in (lower_sentence(figure.lower), unknown_sentence(figure.unknown)) if s]


def sentences(
    figure: AfterPlannedChanges, pct_text: str, *, current_plan: bool = False
) -> list[str]:
    """D1 (or H1), then D2 (`current_plan`, the dashboard only), then A1 and A3."""
    out = [figure_sentence(pct_text)]
    if current_plan:
        out.append(CURRENT_PLAN_SENTENCE)
    return out + counts(figure)


__all__ = [
    "AFTER_LABEL",
    "AFTER_LEGEND",
    "CURRENT_PLAN_SENTENCE",
    "AfterPlannedChanges",
    "after_planned_changes",
    "counts",
    "document_sentence",
    "figure_sentence",
    "lower_sentence",
    "sentences",
    "summary_sentence",
    "unknown_sentence",
]
