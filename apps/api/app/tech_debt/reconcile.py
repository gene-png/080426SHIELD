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
    # COUNT is trustworthy but the specific rows cannot all be named.
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
