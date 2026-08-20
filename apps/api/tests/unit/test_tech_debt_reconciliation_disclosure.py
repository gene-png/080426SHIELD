"""Item 3, Tech Debt: the reconciliation disappears exactly when it cannot name rows.

`reconcile_rows` deliberately produces two different things:

- `excluded` — a COUNT, `received - included`, trustworthy in every case;
- `excluded_rows` — the NAMED rows, populated **only** when every extracted item
  attributed itself to a valid source row. Its own comment says the naming is
  "withheld rather than guessed" and that "the count stays honest".

The count did not stay honest, because nothing persisted it. The route stores
`source_rows_total` and the named list; `Reconciliation.excluded` and
`attribution_complete` are dropped on the floor. Both surfaces then measure the
NAMED LIST:

    exporters.py   excluded_count = len(cap_list.excluded_rows or [])
    TechDebtWorkspace.tsx   (list.excluded_rows?.length ?? 0) > 0

So when a provider omits `source_row_index` on even one item, attribution is
incomplete, the named list is empty, and both surfaces conclude nothing was
excluded — while `cost_label` prints the unqualified **"Total annual cost"** over
a partial figure. That is the 2026-08-04 incident (21 rows / $1,634,236 became
12 / $891,796 presented as the portfolio) reachable through the very mechanism
added to prevent it.

It is the shape `CLAUDE.md` records twice already: a conditional whose false
branch drops the record instead of emitting it under a different reason.

**The fix derives the count rather than storing a second copy of it.**
`source_rows_total - (items that came from a source row)` equals
`len(excluded_rows)` whenever attribution is complete, and recovers the true
count when it is not. Storing a counter would need decrementing on the
include-an-excluded-row path and would be a second source of truth to drift.
Child items from a decomposed bundle carry `parent_item_id`, so they are not
counted — the same correction the workspace already made after `28 > 32` silently
unmounted the whole disclosure.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from app.tech_debt.exporters import build_context, cost_label, reconciliation_line


@dataclass
class _Item:
    name: str
    annual_cost_usd: float | None = 100.0
    parent_item_id: uuid.UUID | None = None
    disposition: object | None = None
    vendor: str | None = None
    category: str | None = None
    function: str | None = None
    license_count: int | None = None
    notes: str | None = None
    confidence_pct: int | None = None
    disposition_rationale: str | None = None


@dataclass
class _List:
    source_rows_total: int | None
    excluded_rows: list | None


def _ctx(*, received: int | None, named: list | None, items: list[_Item]):
    return build_context(
        client_legal_name="Atlas",
        service_title="Tech Debt",
        cap_list=_List(source_rows_total=received, excluded_rows=named),
        items=items,
    )


# --- the defect -------------------------------------------------------------


@pytest.mark.unit
def test_the_count_survives_when_the_rows_cannot_be_named() -> None:
    """21 rows in, 12 capabilities out, provider attributed none of them."""
    ctx = _ctx(received=21, named=[], items=[_Item(f"cap{i}") for i in range(12)])
    assert ctx.excluded_count == 9
    line = reconciliation_line(ctx)
    assert line is not None, "the disclosure vanished exactly when it was needed"
    assert "21 rows received" in line
    assert "9 excluded" in line


@pytest.mark.unit
def test_a_partial_figure_is_never_called_a_total_when_rows_are_unnamed() -> None:
    """`cost_label` keyed on the named list, so it printed 'Total annual cost'."""
    ctx = _ctx(received=21, named=[], items=[_Item(f"cap{i}") for i in range(12)])
    assert cost_label(ctx) == "Included annual cost"


@pytest.mark.unit
def test_the_line_says_the_rows_could_not_be_named() -> None:
    """A count with no list must explain itself, or it reads as a rendering bug."""
    ctx = _ctx(received=21, named=[], items=[_Item(f"cap{i}") for i in range(12)])
    line = reconciliation_line(ctx)
    assert "not attributed" in line or "could not be" in line, line


# --- what must not change ---------------------------------------------------


@pytest.mark.unit
def test_named_rows_still_drive_the_count_when_attribution_is_complete() -> None:
    named = [{"index": 5, "summary": "row 6"}, {"index": 7, "summary": "row 8"}]
    ctx = _ctx(received=14, named=named, items=[_Item(f"cap{i}") for i in range(12)])
    assert ctx.excluded_count == 2
    line = reconciliation_line(ctx)
    assert "14 rows received · 12 included · 2 excluded" in line
    # The complete case must NOT carry the caveat — that would be noise on the
    # common path, which is how a real warning gets tuned out (#31).
    assert "not attributed" not in line


@pytest.mark.unit
def test_nothing_excluded_still_reports_nothing() -> None:
    ctx = _ctx(received=12, named=[], items=[_Item(f"cap{i}") for i in range(12)])
    assert ctx.excluded_count == 0
    assert reconciliation_line(ctx) is None
    assert cost_label(ctx) == "Total annual cost"


@pytest.mark.unit
def test_a_list_predating_the_reconciliation_columns_claims_nothing() -> None:
    """Pre-0036 rows have `source_rows_total = None` — unknown, not zero.

    Nothing can be derived, so nothing is asserted. The C0 pattern requires the
    older row to parse unchanged; it does not license inventing a disclosure.
    """
    ctx = _ctx(received=None, named=None, items=[_Item("cap")])
    assert ctx.excluded_count == 0
    assert reconciliation_line(ctx) is None


@pytest.mark.unit
def test_decomposed_children_do_not_move_the_arithmetic() -> None:
    """Splitting a bundle ADDS items with a parent; source coverage is unchanged.

    The workspace already fixed this after `28 > 32` went false and unmounted
    the disclosure permanently. The exporter must not reintroduce it: counting
    all items here would make 12 included become 15 and hide 3 excluded rows.
    """
    parent = uuid.uuid4()
    items = [_Item(f"cap{i}") for i in range(12)] + [
        _Item(f"child{i}", parent_item_id=parent) for i in range(3)
    ]
    ctx = _ctx(received=21, named=[], items=items)
    assert ctx.excluded_count == 9


@pytest.mark.unit
def test_more_items_than_source_rows_never_reports_a_negative_exclusion() -> None:
    ctx = _ctx(received=5, named=[], items=[_Item(f"cap{i}") for i in range(9)])
    assert ctx.excluded_count == 0
    assert reconciliation_line(ctx) is None
