"""Extraction reconciliation (UX finding 4 / E2E F-5).

A 21-row inventory totalling $1,634,236 produced 12 capabilities totalling
$891,796 in the 2026-08-04 review. Nine non-security rows were dropped — correct
per the prompt, which asks only for security capabilities — but the workspace
reported "CAPABILITIES 12 · ANNUAL COST $891,796" with no hint that 45% of the
uploaded spend had been excluded. A consultant reading that has no way to know
the inventory is partial.

The extractor already returns `source_row_index` per item, so the input rows can
be reconciled against the output exactly.
"""

from __future__ import annotations

import pytest

from app.tech_debt.reconcile import reconcile_rows


def _row(name: str) -> dict:
    return {"Tool Name": name, "Annual Cost USD": "100"}


@pytest.mark.unit
def test_reports_every_row_that_did_not_become_a_capability() -> None:
    rows = [_row("CrowdStrike"), _row("SAP S4HANA"), _row("Splunk"), _row("Workday")]
    result = reconcile_rows(rows, [0, 2])

    assert result.received == 4
    assert result.included == 2
    assert result.excluded == 2
    assert [e.index for e in result.excluded_rows] == [1, 3]
    # The row is echoed back so the UI can show WHAT was dropped, not just how many.
    assert "SAP S4HANA" in result.excluded_rows[0].summary
    assert "Workday" in result.excluded_rows[1].summary
    assert result.attribution_complete is True


@pytest.mark.unit
def test_nothing_excluded_when_every_row_maps() -> None:
    rows = [_row("CrowdStrike"), _row("Splunk")]
    result = reconcile_rows(rows, [0, 1])

    assert (result.received, result.included, result.excluded) == (2, 2, 0)
    assert result.excluded_rows == []


@pytest.mark.unit
def test_counts_still_reconcile_when_the_model_omits_row_indexes() -> None:
    """Older prompts / sloppy providers may not return source_row_index. The
    COUNT must still be honest even when the specific rows can't be attributed —
    silence is the failure mode being fixed."""
    rows = [_row("A"), _row("B"), _row("C")]
    result = reconcile_rows(rows, [None, None])

    assert result.received == 3
    assert result.included == 2
    assert result.excluded == 1
    assert result.excluded_rows == []
    assert result.attribution_complete is False


@pytest.mark.unit
def test_out_of_range_index_degrades_to_counts_without_naming_rows() -> None:
    """An unusable index must not crash, and must not be turned into a guess.

    NOTE: this expectation was corrected during implementation. It first
    asserted that row 1 be listed as excluded — but with items claiming rows
    [0, 99] against a 2-row upload, the bogus index may well BE row 1. Naming it
    would present a guess as fact, which is the same class of error as the
    silent drop this feature exists to fix. Counts stay honest; rows are named
    only when every item is attributable.
    """
    rows = [_row("A"), _row("B")]
    result = reconcile_rows(rows, [0, 99])

    assert result.received == 2
    assert result.included == 2
    assert result.excluded == 0
    assert result.excluded_rows == []
    assert result.attribution_complete is False


@pytest.mark.unit
def test_summary_is_truncated_and_never_empty() -> None:
    rows = [{"Tool Name": "X" * 500, "Vendor": "Y" * 500}]
    result = reconcile_rows(rows, [])
    summary = result.excluded_rows[0].summary
    assert 0 < len(summary) <= 200

    blank = reconcile_rows([{}], [])
    assert blank.excluded_rows[0].summary
