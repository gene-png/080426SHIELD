"""#1123 item 2, Tech Debt (ruled at #736 6216024281). Tech Debt passes a
`ParentGuard`, but before #1123 its refusal fired only while the list was
still APPROVED, and a status change before the flip committed the release.
Same hook and the same approved refusal as `test_release_status_change_race.py`.
"""

from __future__ import annotations

import uuid

import pytest

from tests.unit.test_capability_list_revision import app_client  # noqa: F401  (fixture)
from tests.unit.test_release_status_change_race import (
    _released,
    _status_moves_before_the_flip,
    assert_refused,
)

pytestmark = pytest.mark.unit


def test_tech_debt_release_is_refused_when_the_list_moved_before_the_flip(
    app_client,  # noqa: F811
) -> None:
    from app.models.capability import CapabilityList, CapabilityListStatus
    from tests.unit.test_capability_list_revision import _approve, _decide_all, _finalize
    from tests.unit.test_capability_list_revision import _world as _td_world

    w = _td_world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    fin = _finalize(w)
    assert fin.status_code in (200, 201), fin.text
    deliv_id = fin.json()["id"]

    with _status_moves_before_the_flip(
        CapabilityList, uuid.UUID(w.list_id), CapabilityListStatus.DRAFT
    ) as fired:
        r = w.c.post(f"/tech-debt/deliverables/{deliv_id}/release", headers=w.h)

    assert fired, "the hook never ran -- the race was not driven"
    assert_refused(r)
    assert not _released(deliv_id), "a release committed over a list that moved"
