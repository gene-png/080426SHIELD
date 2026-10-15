"""TD-2 F2 (for #1058): each v3.3 flag finding names WHICH item it is about.

The consultant panel counts items missing a usable flag answer, an item missing
both flags counting once (#736 6170931492). A finding's `source_row_index` and
`item_name` do not identify an item: the parser keeps both items that name one
source row (v3.2 section 4, "duplicated"), and two items with no row can share a
name. So each flag finding carries `item_index`, the item's position in the
model's `items` list, and the panel keys on it.

Every case goes through the extraction route, as `test_tech_debt_suite_flags`
does, and reads the findings back from the API.
"""

from __future__ import annotations

import pytest

from tests.unit.test_tech_debt_routes import app_client  # noqa: F401  (fixture)
from tests.unit.test_tech_debt_suite_flags import _extract, _flag_findings, _item

pytestmark = pytest.mark.unit


def test_two_items_naming_one_row_are_two_items(app_client) -> None:  # noqa: F811
    """The model returns "Okta" twice for row 0 (breaking v3.2 section 4), with
    no `is_suite` on either. Both items are kept, so both are counted."""
    items = [
        _item(0, name="Okta", is_suite=...),
        _item(0, name="Okta", is_suite=...),
    ]
    _, body = _extract(app_client, items, rows=1)
    found = _flag_findings(body)
    # The positive state first: one finding per item, same row, same name.
    assert [(f["source_row_index"], f["item_name"]) for f in found] == [(0, "Okta"), (0, "Okta")]
    assert [f["item_index"] for f in found] == [0, 1]


def test_two_unrowed_items_sharing_a_name_are_two_items(app_client) -> None:  # noqa: F811
    items = [
        _item(0, name="Adobe Acrobat", source_row_index=..., recognized=...),
        _item(1, name="Adobe Acrobat", source_row_index=..., recognized="true"),
    ]
    _, body = _extract(app_client, items, rows=2)
    found = _flag_findings(body)
    assert [(f["source_row_index"], f["item_name"]) for f in found] == [
        (None, "Adobe Acrobat"),
        (None, "Adobe Acrobat"),
    ]
    assert [f["item_index"] for f in found] == [0, 1]


def test_one_item_missing_both_flags_carries_one_index(app_client) -> None:  # noqa: F811
    items = [
        _item(0, name="Okta"),  # compliant: records nothing, but holds index 0
        _item(1, name="Adobe Creative Cloud All Apps", is_suite=..., recognized=...),
    ]
    _, body = _extract(app_client, items, rows=2)
    found = _flag_findings(body)
    assert [(f["field"], f["item_index"]) for f in found] == [
        ("is_suite", 1),
        ("recognized", 1),
    ]
