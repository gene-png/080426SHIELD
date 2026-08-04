"""Overlap analysis for a capability list.

Pure function over a list of CapabilityItem rows. No DB, no I/O. Computes:
  - by_category: buckets where > 1 item shares a category (consolidation
                 candidates).
  - by_vendor:   buckets where > 1 item shares a vendor (license-volume
                 negotiation candidates).
  - top_cost_items: the 5 priciest items, descending.
  - aggregates:  total cost, total item count, count of items missing
                 category / vendor / cost (so the admin sees which fields
                 need editing before the consolidation plan ships).

Cost handling: an item with `annual_cost_usd = None` is excluded from the
sum but still counted in `item_count`. Buckets with at least one None
cost flag `cost_known = False` so the renderer can show "≥ $X" rather
than a misleading exact total.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from app.models.capability import CapabilityItem


@dataclass(frozen=True)
class OverlapBucket:
    key: str
    item_count: int
    total_cost: float
    cost_known: bool
    item_ids: tuple[str, ...]
    item_names: tuple[str, ...]


@dataclass(frozen=True)
class TopCostItem:
    id: str
    name: str
    vendor: str | None
    category: str | None
    annual_cost_usd: float


@dataclass(frozen=True)
class OverlapAnalysis:
    by_category: list[OverlapBucket]
    by_vendor: list[OverlapBucket]
    top_cost_items: list[TopCostItem]
    total_cost: float
    total_items: int
    uncategorized_count: int
    no_vendor_count: int
    no_cost_count: int


def _bucketize(
    items: Iterable[CapabilityItem],
    key_fn,
) -> list[OverlapBucket]:
    """Group items by `key_fn(item)`, return only buckets with > 1 item."""
    grouped: dict[str, list[CapabilityItem]] = defaultdict(list)
    for item in items:
        key = key_fn(item)
        if not key:
            continue
        grouped[key].append(item)

    out: list[OverlapBucket] = []
    for key, group in grouped.items():
        if len(group) <= 1:
            continue
        total = 0.0
        all_known = True
        for it in group:
            if it.annual_cost_usd is None:
                all_known = False
                continue
            total += float(it.annual_cost_usd)
        out.append(
            OverlapBucket(
                key=key,
                item_count=len(group),
                total_cost=total,
                cost_known=all_known,
                item_ids=tuple(str(i.id) for i in group),
                item_names=tuple(i.name for i in group),
            )
        )
    # Largest bucket first; tie-break alphabetically so the output is
    # deterministic for unit tests.
    out.sort(key=lambda b: (-b.item_count, b.key.lower()))
    return out


def analyze_overlap(items: list[CapabilityItem]) -> OverlapAnalysis:
    by_category = _bucketize(items, lambda i: (i.category or "").strip())
    by_vendor = _bucketize(items, lambda i: (i.vendor or "").strip())

    costed = [it for it in items if it.annual_cost_usd is not None]
    costed.sort(key=lambda i: float(i.annual_cost_usd or 0), reverse=True)
    top_cost = [
        TopCostItem(
            id=str(i.id),
            name=i.name,
            vendor=i.vendor,
            category=i.category,
            annual_cost_usd=float(i.annual_cost_usd or 0),
        )
        for i in costed[:5]
    ]

    total_cost = sum(float(i.annual_cost_usd or 0) for i in costed)
    uncategorized = sum(1 for i in items if not (i.category or "").strip())
    no_vendor = sum(1 for i in items if not (i.vendor or "").strip())
    no_cost = sum(1 for i in items if i.annual_cost_usd is None)

    return OverlapAnalysis(
        by_category=by_category,
        by_vendor=by_vendor,
        top_cost_items=top_cost,
        total_cost=total_cost,
        total_items=len(items),
        uncategorized_count=uncategorized,
        no_vendor_count=no_vendor,
        no_cost_count=no_cost,
    )
