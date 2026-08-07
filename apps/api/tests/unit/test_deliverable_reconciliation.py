"""A released deliverable must not present a partial figure as a total (N-010).

2026-08-07: a client uploaded 28 rows worth $3,608,000. Two were excluded. The
released PDF, XLSX and DOCX each said "Total annual cost: $3,368,000" with no
mention of the exclusions — a $240,000 understatement stated as a total, in a
formal client document. The workspace disclosed it; the report never did.

Excluded rows carry only an index and a free-text summary, so an excluded
MONEY total cannot be derived honestly. The report therefore states the row
reconciliation and relabels the figure, rather than inventing a number.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.tech_debt.exporters import DeliverableContext, cost_label, reconciliation_line


@dataclass
class _FakeList:
    source_rows_total: int | None
    excluded_rows: list | None


def _ctx(*, received: int | None, excluded: int, included: int) -> DeliverableContext:
    return DeliverableContext(
        client_legal_name="UX-E2E-Validation",
        service_title="Technical Debt Review",
        cap_list=_FakeList(received, [{"index": i} for i in range(excluded)]),
        items=[object()] * included,
        total_cost=3_368_000.0,
        estimated_savings=0.0,
        savings_cost_known=True,
        source_rows_total=received,
        excluded_count=excluded,
    )


@pytest.mark.unit
def test_reconciliation_is_stated_when_rows_were_excluded() -> None:
    ctx = _ctx(received=28, excluded=2, included=26)
    assert reconciliation_line(ctx) == "28 rows received · 26 included · 2 excluded"
    assert cost_label(ctx) == "Included annual cost", "a partial figure is not a total"


@pytest.mark.unit
def test_nothing_excluded_reads_as_a_plain_total() -> None:
    """No exclusions means the figure IS the whole upload — don't add noise."""
    ctx = _ctx(received=26, excluded=0, included=26)
    assert reconciliation_line(ctx) is None
    assert cost_label(ctx) == "Total annual cost"


@pytest.mark.unit
def test_missing_source_count_does_not_fabricate_a_reconciliation() -> None:
    """Pre-migration lists have no source_rows_total. Say nothing rather than guess."""
    ctx = _ctx(received=None, excluded=2, included=26)
    assert reconciliation_line(ctx) is None
