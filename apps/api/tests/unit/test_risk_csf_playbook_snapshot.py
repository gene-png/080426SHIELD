"""#474 D': a Playbook edited after generate stops publish (snapshot, not lock).

Risk's CSF findings come from the Playbook, and Playbook rows stay editable
after the CSF assessment is approved and released (#37 is Gene's open
decision; nothing here freezes them). `publish_blockers` compared only an
input's record id, version and status, so a score or target changed after
generate published a register whose CSF findings no longer matched the
Playbook. The advisor's ruling (#736 6087786886, item 3, option (a)):
generate records a content fingerprint of the in-scope Playbook rows, and
publish reports CSF `changed` when it differs.

A register generated before the fingerprint was recorded carries no
fingerprint for its CSF input. It is reported `changed` too, so it is
regenerated before it can publish: missing data is unconfirmed, never a
match.

Driven through the generate, Playbook PATCH and publish routes.
"""

from __future__ import annotations

import pytest

from tests._csf_playbook_rows import score_csf_playbook
from tests._risk_inputs import release, seed_released
from tests.unit.test_risk_publish_inputs import _blockers, _gen, _publish
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _session,
    app_client,
)

pytestmark = pytest.mark.unit

CHANGED = [{"input": "csf", "reason": "changed", "status": "released"}]


def _released_world(c, provider, bearer: str, cid: str) -> tuple[dict, str]:
    """ATT&CK, ZT and CSF all released, the CSF Playbook scored on one row;
    a register generated from them. Returns the CSF headers and that row's id."""
    seed_released(c, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    assert svc.status_code in (200, 201), svc.text
    sid = svc.json()["id"]
    a = c.post(f"/csf/services/{sid}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    code = a.json()["answers"][0]["subcategory_code"]
    score_csf_playbook(c, h, sid, {code: (1, 5)})
    ap = c.post(f"/csf/assessments/{a.json()['id']}/approve", headers=h)
    assert ap.status_code == 200, ap.text
    release(c, bearer, cid, "csf", sid)
    _gen(c, provider, bearer, cid)
    row = next(
        r
        for r in c.get(f"/csf/services/{sid}/profile/high", headers=h).json()["rows"]
        if r["subcategory_code"] == code
    )
    return h, row["id"]


def test_an_untouched_register_still_publishes(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    _released_world(c, provider, bearer, cid)
    r = _publish(c, bearer, cid)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize(
    "edit",
    [{"governance": 2}, {"target_level": 4}],
    ids=["score", "target"],
)
def test_a_playbook_edit_after_generate_blocks_publish(app_client, edit: dict) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    h, row_id = _released_world(c, provider, bearer, cid)
    r = c.patch(f"/csf/dimension-scores/{row_id}", headers=h, json=edit)
    assert r.status_code == 200, r.text
    assert _blockers(_publish(c, bearer, cid)) == CHANGED


def test_a_register_without_a_recorded_fingerprint_is_changed(app_client) -> None:  # noqa: F811
    """A register generated before this change: its CSF input carries no
    fingerprint. Reported `changed`, so it is regenerated, never published
    as if it matched."""
    from sqlalchemy import select

    from app.models.risk_register import RiskRegister

    c, provider = app_client
    bearer, cid = _admin(c)
    _released_world(c, provider, bearer, cid)
    with _session() as s:
        reg = s.execute(select(RiskRegister)).scalar_one()
        prov = dict(reg.provenance)
        rows = [dict(r) for r in prov["current_inputs"]]
        csf = [r for r in rows if r["kind"] == "csf"]
        assert len(csf) == 1, rows
        assert csf[0].pop("playbook_fingerprint", None) is not None, csf  # it was recorded
        prov["current_inputs"] = rows
        reg.provenance = prov
        s.commit()
    assert _blockers(_publish(c, bearer, cid)) == CHANGED
