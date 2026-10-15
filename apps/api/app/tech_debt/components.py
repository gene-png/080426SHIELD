"""Bundle components: the ONE statement of which rows count as what (for #835).

`add_capability_components` (routes/tech_debt.py) splits a bundled license,
such as Microsoft 365 E5, into the capabilities a consultant names inside it.
Each part is written with `parent_item_id` set and NO cost, because the parent
row keeps the whole license value. So a part is:

  - not a source row: it never counts as an application, a "capability
    reviewed", or an included upload row;
  - not a cost: it never adds to spend, and its missing cost never makes spend
    a floor (the parent's cost covers it);
  - a capability in its OWN category, which is why splitting exists (UX
    finding 5): Defender for Endpoint beside a separately licensed CrowdStrike
    is a real redundancy. But the parts of one bundle, and the bundle itself,
    are ONE license, so they count once in any category or vendor bucket.

Savings still SEE a part (advisor ruling on #736): a part marked Cut is an
unknown saving, so `savings.estimated_savings` makes the figure a floor for it.
But a part's STORED cost is never a saving (advisor ruling on #736, 6115773247,
for #929): one written before #927 refused it is read as no cost, through
`savings_cost`, which every savings caller uses.

Every reader calls these rather than re-testing `parent_item_id`: the defect
this module ends was a third reader that missed the rule two others had.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def is_component(item: Any) -> bool:
    """True for a named part of a split bundle. `getattr` because the exporter
    is also called with plain objects that carry the same fields."""
    return getattr(item, "parent_item_id", None) is not None


def source_items[T](items: Iterable[T]) -> list[T]:
    """The rows that came from the upload (or were added as tools of their own)."""
    return [it for it in items if not is_component(it)]


def license_key(item: Any) -> str:
    """The license a row is paid under: a part's bundle, or the row itself.

    Buckets count DISTINCT license keys, so a bundle and its parts in one
    category (or under one vendor) count once."""
    parent = getattr(item, "parent_item_id", None)
    return str(parent if parent is not None else item.id)


def license_count(items: Iterable[Any]) -> int:
    """How many distinct licenses `items` are paid under."""
    return len({license_key(it) for it in items})


def savings_cost(item: Any) -> Any:
    """The cost a savings figure may count for `item`: its own cost, or None
    for a part. A part's cost is held by its bundle, so a figure stored on a
    part (only possible before #927) is not a saving; None keeps a Cut part an
    UNKNOWN saving, which makes the figure a floor, as it always has."""
    return None if is_component(item) else item.annual_cost_usd


def bundle_name(item: Any, names: dict[Any, str]) -> str | None:
    """for #929: the name of the bundle carrying a part's cost, stripped; ""
    when that name is blank; None for a row that is not a part. `names` maps
    each row's id to its name over the same list. A part's bundle is always in
    that list (the split route writes both, and the foreign key cascades), so a
    missing parent is a broken list: the lookup raises KeyError rather than
    inventing a name."""
    if not is_component(item):
        return None
    return names[item.parent_item_id].strip()


def included_in(bundle: str) -> str:
    """A part's cost cell: where its cost is (copy approved on #736,
    6114570797). The SAME words the client dashboard renders
    (`apps/web/src/lib/dashboards/techDebt.ts`, `itemCost`); "" is a bundle
    with a blank name."""
    return "Included in its bundle" if bundle == "" else f"Included in {bundle}"
