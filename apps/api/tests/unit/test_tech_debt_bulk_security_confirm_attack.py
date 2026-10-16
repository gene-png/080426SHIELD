"""#1174: a row signed off by the BULK confirm reads, in ATT&CK's what-if,
exactly as a row signed off by the single confirm.

This pins the reason the bulk route writes one audit row per item rather
than one for the list: the what-if dates each row's exit from scope by its
first per-item confirmation (`_list_history` in `routes/attack_scenarios.py`,
`first_confirmed_at`). A confirmed row with no such row on record cannot be
placed in time, and the what-if reads "cannot be checked" (null) for it.

Driven through the routes, on `test_attack_scenario_added_basis`'s world and
its case "a row in scope at the base and confirmed out since is not added",
once per confirm route.
"""

from __future__ import annotations

import pytest

from app.models.capability import CapabilityListStatus
from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)
from tests.unit.test_attack_scenario_added_basis import (
    MAIL,
    _approve,
    _confirm,
    _mail_on_v1_before_the_base,
    _re_extracted_v2,
    _v1_id,
    _what_if,
)
from tests.unit.test_attack_scenario_routes import EDR, SIEM, SOAR, _flags, _world

pytestmark = pytest.mark.unit


def _bulk_confirm(w, list_id, item_id) -> None:
    """The bulk route, with one row ticked."""
    r = w.c.post(
        f"/tech-debt/capability-lists/{list_id}/items/security-classification/confirm",
        headers=w.h,
        json={"item_ids": [str(item_id)]},
    )
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("route", ["single", "bulk"])
def test_a_row_confirmed_out_since_the_base_reads_the_same_by_either_route(
    app_parts, route: str  # noqa: F811
) -> None:
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    item_id = _mail_on_v1_before_the_base(w)
    if route == "single":
        _confirm(w, item_id)  # after the base
    else:
        _bulk_confirm(w, _v1_id(w), item_id)  # after the base
    _approve(w, _v1_id(w))  # v1 moves on (after the base) before v2 is cut
    _re_extracted_v2(w, [EDR, SIEM, SOAR, MAIL])
    body = _what_if(w, {w.cc: [_flags(w.cc, MAIL, d=True)]})
    # 0, not null: the confirmation is on record per row, so MAIL is placed
    # in scope at the base and is not "added since" it.
    assert body["tools_added_since_base"] == 0, body["tools_added_since_base"]
