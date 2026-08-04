"""Unit tests for analyze_overlap. Pure function; no DB."""

from __future__ import annotations

import uuid

import pytest

from app.models.capability import CapabilityItem
from app.tech_debt.overlap import analyze_overlap


def _item(
    name: str,
    *,
    category: str | None = None,
    vendor: str | None = None,
    cost: float | None = None,
) -> CapabilityItem:
    return CapabilityItem(
        id=uuid.uuid4(),
        capability_list_id=uuid.uuid4(),
        name=name,
        vendor=vendor,
        category=category,
        function=None,
        annual_cost_usd=cost,
        license_count=None,
        notes=None,
        confidence_pct=None,
        source_artifact_id=None,
    )


@pytest.mark.unit
def test_analyze_overlap_groups_categories_with_more_than_one_item() -> None:
    items = [
        _item("Wiz", category="CNAPP", cost=350_000),
        _item("Lacework", category="CNAPP", cost=120_000),
        _item("Splunk", category="SIEM", cost=480_000),
        _item("Bare row", category=None),  # uncategorized
    ]
    result = analyze_overlap(items)
    assert len(result.by_category) == 1
    cnapp = result.by_category[0]
    assert cnapp.key == "CNAPP"
    assert cnapp.item_count == 2
    assert cnapp.total_cost == 470_000
    assert cnapp.cost_known is True
    assert set(cnapp.item_names) == {"Wiz", "Lacework"}
    assert result.uncategorized_count == 1


@pytest.mark.unit
def test_analyze_overlap_buckets_sorted_largest_first() -> None:
    items = [
        _item("A", category="X"),
        _item("B", category="X"),
        _item("C", category="X"),
        _item("D", category="Y"),
        _item("E", category="Y"),
    ]
    result = analyze_overlap(items)
    assert [b.key for b in result.by_category] == ["X", "Y"]
    assert [b.item_count for b in result.by_category] == [3, 2]


@pytest.mark.unit
def test_analyze_overlap_marks_partial_cost_buckets() -> None:
    items = [
        _item("A", category="X", cost=100),
        _item("B", category="X"),  # no cost
    ]
    result = analyze_overlap(items)
    assert len(result.by_category) == 1
    assert result.by_category[0].cost_known is False
    assert result.by_category[0].total_cost == 100  # sum of known costs


@pytest.mark.unit
def test_analyze_overlap_top_cost_items_descending_max_five() -> None:
    items = [_item(f"Tool {i}", cost=float(i * 100_000)) for i in range(1, 10)]
    result = analyze_overlap(items)
    costs = [i.annual_cost_usd for i in result.top_cost_items]
    assert len(result.top_cost_items) == 5
    assert costs == sorted(costs, reverse=True)
    assert result.top_cost_items[0].annual_cost_usd == 900_000


@pytest.mark.unit
def test_analyze_overlap_counts_aggregates() -> None:
    items = [
        _item("A", category="X", vendor="V1", cost=100),
        _item("B", category=None, vendor="V1", cost=None),
        _item("C", category="X", vendor=None, cost=50),
    ]
    result = analyze_overlap(items)
    assert result.total_items == 3
    assert result.total_cost == 150
    assert result.uncategorized_count == 1
    assert result.no_vendor_count == 1
    assert result.no_cost_count == 1


@pytest.mark.unit
def test_analyze_overlap_skips_blank_keys() -> None:
    items = [
        _item("A", category="   "),  # whitespace-only
        _item("B", category="   "),
    ]
    result = analyze_overlap(items)
    # Whitespace-only keys don't form a bucket.
    assert result.by_category == []
    assert result.uncategorized_count == 2


@pytest.mark.unit
def test_analyze_overlap_empty_input() -> None:
    result = analyze_overlap([])
    assert result.total_items == 0
    assert result.total_cost == 0
    assert result.by_category == []
    assert result.by_vendor == []
    assert result.top_cost_items == []
