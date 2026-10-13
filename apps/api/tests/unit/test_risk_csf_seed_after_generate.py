"""#1120 (review of #1151, round 2): the CSF Playbook fingerprint's `changed`
path, reached through the one writer A2 leaves on an approved record.

Under ruling A2 an APPROVED or RELEASED CSF assessment's Playbook rows are not
edited in place, but seeding still creates the rows of one that has none. A
register generated before that seed recorded the empty Playbook's fingerprint,
so publish must report CSF `changed` rather than publish findings that no
longer match the Playbook. Driven through the generate, seed and publish
routes.
"""

from __future__ import annotations

import pytest

from tests._risk_inputs import release, seed_released
from tests.unit.test_risk_publish_inputs import _blockers, _gen, _publish
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _session,
    app_client,
)

pytestmark = pytest.mark.unit

CHANGED = [{"input": "csf", "reason": "changed", "status": "released"}]


def test_seeding_a_released_playbook_after_generate_is_changed(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    seed_released(c, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    sid = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()["id"]
    a = c.post(f"/csf/services/{sid}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    assert c.post(f"/csf/assessments/{a.json()['id']}/approve", headers=h).status_code == 200
    release(c, bearer, cid, "csf", sid)
    _gen(c, provider, bearer, cid)
    recorded = _recorded_fingerprint()
    # The mismatch path, not the NULL one: generate recorded a fingerprint.
    assert recorded is not None

    seeded = c.post(f"/csf/services/{sid}/profiles/seed", headers=h, json={"tiers": ["low"]})
    assert seeded.status_code == 200, seeded.text  # A2's one exception: no rows yet
    assert _current_fingerprint(a.json()["id"]) != recorded

    assert _blockers(_publish(c, bearer, cid)) == CHANGED
    assert _recorded_fingerprint() == recorded  # publish refused; nothing rewrote it


def _recorded_fingerprint() -> str | None:
    from sqlalchemy import select

    from app.models.risk_register import RiskRegister

    with _session() as s:
        reg = s.execute(select(RiskRegister)).scalar_one()
        (csf,) = [r for r in reg.provenance["current_inputs"] if r["kind"] == "csf"]
        return csf.get("playbook_fingerprint")


def _current_fingerprint(assessment_id: str) -> str:
    from app.risk.inputs import csf_playbook_fingerprint

    with _session() as s:
        return csf_playbook_fingerprint(s, assessment_id)
