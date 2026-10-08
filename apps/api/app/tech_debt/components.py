"""Bundle components: the ONE statement of which rows count as what (for #835).

`add_capability_components` (routes/tech_debt.py) splits a bundled licence,
such as Microsoft 365 E5, into the capabilities a consultant names inside it.
Each part is written with `parent_item_id` set and NO cost, because the parent
row keeps the whole licence value. So a part is:

  - not a source row: it never counts as an application, a "capability
    reviewed", or an included upload row;
  - not a cost: it never adds to spend, and its missing cost never makes spend
    a floor (the parent's cost covers it);
  - a capability in its OWN category, which is why splitting exists (UX
    finding 5): Defender for Endpoint beside a separately licensed CrowdStrike
    is a real redundancy. But the parts of one bundle, and the bundle itself,
    are ONE licence, so they count once in any category or vendor bucket.

Savings are deliberately NOT routed through here (advisor ruling on #736): a
part marked Cut with no cost really is an unknown saving, so
`savings.estimated_savings` still sees it.

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


def licence_key(item: Any) -> str:
    """The licence a row is paid under: a part's bundle, or the row itself.

    Buckets count DISTINCT licence keys, so a bundle and its parts in one
    category (or under one vendor) count once."""
    parent = getattr(item, "parent_item_id", None)
    return str(parent if parent is not None else item.id)


def licence_count(items: Iterable[Any]) -> int:
    """How many distinct licences `items` are paid under."""
    return len({licence_key(it) for it in items})
