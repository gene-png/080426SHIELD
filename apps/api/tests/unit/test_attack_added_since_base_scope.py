"""For #1012: was a capability row in ATT&CK security scope AT THE BASE?

The what-if's drafts-branch basis (`attack/added_since_base.py`) reads a draft
row as of the base's approval, not as it is now. The writers decide the truth
table, so it is written from them, never from the function under test:

* every row starts IN scope: extraction writes `security_related` True, None
  or False with `security_class_confirmed` False, and an unconfirmed negative
  is provisional, so in scope (`tech_debt/security_scope.in_security_scope`);
* the confirm route takes a row OUT of scope, and accepts only a negative
  (`security_related` False); it writes a confirm audit row;
* the override route puts a row back IN scope for good: it sets
  `security_related` True and clears the confirmation, and the confirm
  route then refuses the row. So nothing follows an override, and the
  FIRST override is the one that matters.

So: in scope at the base iff the first override was at or before it, or no
confirmation was at or before it. Each row below names its history (the
classification the extraction wrote, then when it was confirmed and when it
was first overridden, relative to the base) and builds the row's CURRENT
fields from that history as the writers would. Histories the writers cannot
produce are marked and still pinned, so the rule stays total.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.attack.added_since_base import (
    DraftRow,
    ListVersion,
    basis_at,
)
from app.models.capability import CapabilityListStatus

pytestmark = pytest.mark.unit

BASE = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
BEFORE = BASE - timedelta(hours=1)
AFTER = BASE + timedelta(hours=1)
CREATED = BASE - timedelta(days=1)
TIMES = {"before": BEFORE, "after": AFTER, "never": None}

# (extraction's security_related, confirmed, first overridden, in scope at the
# base, reachable). Expected values are the rule above, worked by hand.
TRUTH_TABLE = [
    # security_related True: the confirm route refuses a positive.
    (True, "never", "never", True, True),
    (True, "never", "before", True, True),
    (True, "never", "after", True, True),
    (True, "before", "never", False, False),
    (True, "before", "before", True, False),
    (True, "before", "after", False, False),
    (True, "after", "never", True, False),
    (True, "after", "before", True, False),
    (True, "after", "after", True, False),
    # security_related None: the confirm route refuses it too.
    (None, "never", "never", True, True),
    (None, "never", "before", True, True),
    (None, "never", "after", True, True),
    (None, "before", "never", False, False),
    (None, "before", "before", True, False),
    (None, "before", "after", False, False),
    (None, "after", "never", True, False),
    (None, "after", "before", True, False),
    (None, "after", "after", True, False),
    # security_related False: provisional (in scope) until confirmed.
    (False, "never", "never", True, True),
    (False, "never", "before", True, True),
    (False, "never", "after", True, True),  # re-overriding an in-scope row
    (False, "before", "never", False, True),
    (False, "before", "before", True, True),  # confirmed, then overridden, both before
    (False, "before", "after", False, True),  # out at the base, back in since
    (False, "after", "never", True, True),  # in at the base, confirmed out since
    (False, "after", "before", True, False),  # a confirm after an override is refused
    (False, "after", "after", True, True),  # confirm then override, both after
]


def _row(related: bool | None, confirmed: str, overridden: str) -> DraftRow:
    """The row's current fields, as the writers leave them after its history."""
    confirm_at, override_at = TIMES[confirmed], TIMES[overridden]
    ever_overridden = override_at is not None
    return DraftRow(
        name="Mail Gateway",
        created_at=CREATED,
        security_related=True if ever_overridden else related,
        # The override clears the confirmation; the confirm sets it.
        confirmed=confirm_at is not None and not ever_overridden,
        first_confirmed_at=confirm_at,
        first_overridden_at=override_at,
    )


def _draft(row: DraftRow) -> ListVersion:
    return ListVersion(
        service_id="td",
        version=1,
        status=CapabilityListStatus.DRAFT,
        created_at=CREATED,
        approved_at=None,
        approvals=(),
        discarded_at=None,
        approved_membership=None,
        rows=(row,),
    )


@pytest.mark.parametrize(
    ("related", "confirmed", "overridden", "in_scope", "reachable"),
    TRUTH_TABLE,
    ids=[f"{r}-confirmed_{c}-overridden_{o}" for r, c, o, _, _ in TRUTH_TABLE],
)
def test_a_drafts_basis_row_is_judged_by_its_scope_at_the_base(
    related, confirmed, overridden, in_scope, reachable
) -> None:
    basis = basis_at(BASE, [_draft(_row(related, confirmed, overridden))])
    expected = {"mail gateway"} if in_scope else set()
    assert basis == expected, (related, confirmed, overridden, reachable)


def test_the_table_is_the_whole_state_space() -> None:
    """3 classifications x 3 confirm times x 3 override times."""
    keys = {(r, c, o) for r, c, o, _, _ in TRUTH_TABLE}
    assert len(keys) == len(TRUTH_TABLE) == 3 * 3 * 3


def test_a_confirmed_row_with_no_confirm_on_record_cannot_be_placed() -> None:
    """Confirmed out of scope now, with no record of WHEN: whether it was in
    scope at the base is not on record. Null for the whole basis, never a
    guess in either direction."""
    row = DraftRow(
        name="Mail Gateway",
        created_at=CREATED,
        security_related=False,
        confirmed=True,
        first_confirmed_at=None,
        first_overridden_at=None,
    )
    assert basis_at(BASE, [_draft(row)]) is None
