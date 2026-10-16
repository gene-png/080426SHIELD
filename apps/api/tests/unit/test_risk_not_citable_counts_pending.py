"""#1264 item 1: the Risk Register's "Scored coverage" sheet prints, per
assessment, "Rows scored", "Rows total" and "Not citable" (`total - scored`).

For ATT&CK the citable set is the scored codes LESS those pending review
(`link_scope.LinkScope.citable`), and the register's allow-list reads exactly
that. A pending technique is scored, so it is not in "Not citable", yet it can
never be linked: the column states fewer uncitable rows than there are.

Reachable only on registers built from ATT&CK assessments approved before R3
(`status_rules` 1, migration 0059's backfill), where `pending_codes` is not
empty. The world is #415's (`test_risk_pending_links._World`), which builds that
shape.

The expected "Not citable" is derived from the ATT&CK API's own per-row
`pending_review` flag and the sheet's own "Rows total" and "Rows scored" cells,
never from the module that writes the cell.
"""

from __future__ import annotations

import pytest

from tests.unit.test_risk_pending_links import _World
from tests.unit.test_risk_register import app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def test_not_citable_counts_the_pending_rows_that_cannot_be_linked(
    app_client,  # noqa: F811
) -> None:
    w = _World(app_client, pending_leaf=True, pending_parent=False)
    assert w.pending == {w.leaf}, "setup: one scored technique is pending review"
    w.generate(w.confirmed)
    header, *rows = w.exports()["xlsx_scope"]
    assert header == ("Assessment", "Rows scored", "Rows total", "Not citable", "Pending review")
    (attack,) = [r for r in rows if r and r[0] == "ATT&CK coverage"]
    _label, scored, total, not_citable, pending = attack
    assert pending == len(w.pending) == 1, attack  # positive first: the count is there
    # The rows that cannot be linked: the unscored ones, and the scored ones
    # pending review.
    assert not_citable == (total - scored) + pending, attack
