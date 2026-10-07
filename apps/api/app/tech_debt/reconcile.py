"""Reconcile an uploaded inventory against the capabilities extracted from it.

The extraction prompt keeps only rows that represent a SECURITY capability and
skips the rest — by design. What was missing is the disclosure: in the
2026-08-04 review a 21-row, $1,634,236 inventory became 12 capabilities worth
$891,796, and the workspace presented that as the portfolio with no indication
that nine rows and 45% of the spend had been left out.

"AI suggests, code computes" applies here too: the model is not asked how many
rows it dropped. Code counts them, from the ``source_row_index`` each item
already carries.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

_SUMMARY_MAX = 200


@dataclass(frozen=True)
class ExcludedRow:
    """One uploaded row that produced no capability."""

    index: int
    summary: str


@dataclass(frozen=True)
class Reconciliation:
    """How the uploaded rows map onto the extracted capabilities."""

    received: int
    included: int
    excluded: int
    excluded_rows: list[ExcludedRow] = field(default_factory=list)
    # False when the model did not attribute every item to a source row, so the
    # specific rows cannot all be named.
    #
    # The count is trustworthy whenever fewer items came back than rows went in,
    # which is the normal case. It is NOT when items outnumber source rows: two
    # items sharing one `source_row_index` make `max(received - included, 0)`
    # report zero, and the arithmetic then cannot distinguish "nothing was
    # excluded" from "a row was excluded and another row produced two items".
    # Persisting THIS flag is what would let a renderer say "the reconciliation
    # does not balance" instead. An earlier comment here said the count was
    # trustworthy full stop; it is not.
    attribution_complete: bool = True


def _summarise(row: Mapping[str, object], index: int) -> str:
    """A short, human-readable echo of the row so the UI can show what was cut."""
    parts = [
        f"{key}: {value}"
        for key, value in row.items()
        if key and value not in (None, "") and str(value).strip()
    ]
    text = " · ".join(parts).strip()
    if not text:
        # Never render an empty chip — say which row it was.
        return f"(row {index + 1}: no readable values)"
    return text[:_SUMMARY_MAX]


def reconcile_rows(
    rows: Sequence[Mapping[str, object]],
    source_row_indexes: Iterable[int | None],
) -> Reconciliation:
    """Compare parsed input rows against the extracted items' source indexes.

    ``source_row_indexes`` is one entry per extracted capability — the value of
    its ``source_row_index``, which may be None when the provider omitted it.
    """
    indexes = list(source_row_indexes)
    included = len(indexes)
    received = len(rows)

    claimed = {i for i in indexes if isinstance(i, int) and 0 <= i < received}
    # Every item must name a valid row for the per-row list to be complete.
    attribution_complete = len(claimed) == included

    excluded_rows: list[ExcludedRow] = []
    if attribution_complete:
        excluded_rows = [
            ExcludedRow(index=i, summary=_summarise(rows[i], i))
            for i in range(received)
            if i not in claimed
        ]

    return Reconciliation(
        received=received,
        included=included,
        excluded=max(received - included, 0),
        excluded_rows=excluded_rows,
        attribution_complete=attribution_complete,
    )


ExclusionCountState = Literal["not_recorded", "exact", "unknown"]


def exclusion_count_state(cap_list: Any) -> ExclusionCountState:
    """How much a stored list may honestly say about rows its extraction excluded.

    THE ONE READER (#177): the exporter, the client dashboard, the admin list
    and ATT&CK's AI-inputs view all call it, so no surface can call a count
    exact that another calls unknown.

    * ``not_recorded`` -- ``source_rows_total`` is NULL: no reconciliation was
      stored (a pre-0036 list, or one no extraction wrote). No claim either way.
    * ``exact`` -- the extraction attributed every item to one uploaded row
      (``attribution_complete`` True, migration 0058), so
      ``received - included`` is the exclusion count and ``excluded_rows``
      names every one of them. Zero is a true zero.
    * ``unknown`` -- attribution failed: two items claimed one row, or an item
      named none. ``received - included`` is then only a FLOOR (the rows the
      items actually claimed are fewer than the items), and floors to zero when
      items outnumber rows, which is #193.

    NULL ``attribution_complete`` -- a list written before 0058 -- is NEVER read
    as complete by default. One inference is sound, and WHY is the writer:
    ``reconcile_rows`` above builds ``excluded_rows`` only inside
    ``if attribution_complete:`` (otherwise it stays ``[]``), and the
    extraction job (``routes/tech_debt.py``, the ``CapabilityList(`` insert)
    stores exactly that list, unchanged since migration 0036. So a NON-EMPTY
    stored list could only have been written with attribution complete. An
    empty one is what BOTH a clean run that excluded nothing and a failed
    attribution wrote, so it proves nothing, and reads ``unknown``.
    ``test_tech_debt_exclusion_count.py`` builds each pre-0058 state through
    that writer and nulls the flag, rather than hand-building a combination
    the writer could not produce.
    """
    if getattr(cap_list, "source_rows_total", None) is None:
        return "not_recorded"
    flag = getattr(cap_list, "attribution_complete", None)
    if flag is True:
        return "exact"
    if flag is None and getattr(cap_list, "excluded_rows", None):
        return "exact"
    return "unknown"


def unconfirmed_exclusions(cap_list) -> list[int]:
    """#850: the indexes of excluded rows nobody has confirmed, in list order.

    An entry is confirmed only when its `confirmed` is exactly True. A missing
    key is UNCONFIRMED: extraction writes entries without it, and a list from
    before the confirm action has none, and missing data never defaults to
    confirmed. A list whose extraction could not attribute its items stores no
    entries, so it has nothing to confirm and is not gated (it stays disclosed
    as an unknown exclusion count).
    """
    return [
        int(e.get("index", -1))
        for e in (getattr(cap_list, "excluded_rows", None) or [])
        if e.get("confirmed") is not True
    ]
