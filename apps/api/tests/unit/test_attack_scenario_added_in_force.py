"""For #1012: the what-if's "tools added since the base" check reads only the
Tech Debt list version that was IN FORCE when the base was approved
(`attack/added_since_base.py`, the advisor's option A).

A list approved before migration 0043 has no recorded membership, so the
check cannot be made when that list was the version in force at the base:
null, never 0. A pre-0043 v1 that an approved v2 with a recorded snapshot had
already superseded by then does not decide anything, so it must not make the
whole what-if unknowable.

Driven through the routes (`POST /attack/scenarios/{id}/run`), on the world
`test_attack_scenario_routes` builds: v1 APPROVED with no recorded
membership, the base approved, finalized and released.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus
from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)
from tests.unit.test_attack_scenario_added_basis import _approve_before_the_base
from tests.unit.test_attack_scenario_routes import (
    EDR,
    SIEM,
    SOAR,
    World,
    _flags,
    _run_to_completion,
    _world,
)

pytestmark = pytest.mark.unit


def _approved_v2_uploaded_before_the_base(w: World) -> None:
    """v2 of the same Tech Debt service, holding the same tools, approved
    through the approve route (membership recorded, post-0043) and placed
    before the base: the version in force at the base. The same tools are
    offered now, so none was added."""
    with w.sessions() as db:
        v1 = db.execute(select(CapabilityList)).scalars().one()
        v2 = CapabilityList(service_id=v1.service_id, version=2, status=CapabilityListStatus.DRAFT)
        db.add(v2)
        db.flush()
        for name in (EDR, SIEM, SOAR):
            db.add(CapabilityItem(capability_list_id=v2.id, name=name))
        db.commit()
        v2_id = v2.id
    _approve_before_the_base(w, v2_id)
    with w.sessions() as db:
        snapshot = db.get(CapabilityList, v2_id).approved_membership
    assert sorted(e["name"] for e in snapshot) == sorted([EDR, SIEM, SOAR])


def test_a_superseded_pre_0043_version_does_not_make_the_check_unknowable(
    app_parts,  # noqa: F811
) -> None:
    w = _world(app_parts)  # v1 APPROVED, no approved_membership (pre-0043)
    _approved_v2_uploaded_before_the_base(w)
    w.answer({w.cc: [_flags(w.cc, SIEM, d=True)]})
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["tools_added_since_base"] == 0, body["tools_added_since_base"]
    assert all(d["credited_added_tool"] is False for d in body["differences"])


def test_the_pre_0043_version_in_force_still_reads_null(app_parts) -> None:  # noqa: F811
    """The other half: when the pre-0043 list IS the version in force, the
    check still cannot be made, and says null, never 0."""
    w = _world(app_parts)
    w.answer({w.cc: [_flags(w.cc, SIEM, d=True)]})
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["after"] is not None
    assert body["tools_added_since_base"] is None
