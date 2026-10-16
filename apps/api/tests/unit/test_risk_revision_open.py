"""#1156: the Risk Register with a revision draft open, through `/revisions`.

ATT&CK and Zero Trust are released; then "Start a revision" (#1120) opens ZT
v2 as a DRAFT. Every Risk reader takes the latest record (`latest_record`), so
Generate drafts the ZT findings from v2.

1. The Generate gate's `not_finalized` must name the Zero Trust assessment:
   what Generate reads is a draft. It used to ask for ANY approved-or-released
   assessment, found the released v1 behind the draft, and listed nothing.
2. A register generated from the released v1 must not be refused as if it
   drew on a draft. The register drew on v1; a newer version exists, so the
   refusal is the one for a changed input, which names the remedy that works
   (generate a new version), not "(draft)".

Every expected value is typed from the scenario, never read from the code.
"""

from __future__ import annotations

import pytest

from tests._risk_inputs import seed_released
from tests.unit.test_risk_publish_inputs import _blockers, _gen, _publish
from tests.unit.test_risk_register import _admin, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def _open_zt_revision(c, bearer: str, cid: str, zt_service: str, zt_assessment: str) -> None:
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    r = c.post(
        f"/zt/services/{zt_service}/assessments/{zt_assessment}/revisions",
        headers=h,
        json={"reason": "Client asked for a correction."},
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "draft", r.json()["status"]


def _gate(c, bearer: str, cid: str) -> dict:
    r = c.get(f"/risk/clients/{cid}/gate", headers={"Authorization": f"Bearer {bearer}"})
    assert r.status_code == 200, r.text
    return r.json()


def test_the_gate_names_an_input_whose_current_record_is_a_revision_draft(
    app_client,  # noqa: F811
) -> None:
    c, _provider = app_client
    bearer, cid = _admin(c)
    s = seed_released(c, bearer, cid)
    assert _gate(c, bearer, cid)["not_finalized"] == []  # positive control: all released
    _open_zt_revision(c, bearer, cid, s.zt_service, s.zt_assessment)
    gate = _gate(c, bearer, cid)
    assert gate["not_finalized"] == ["the Zero Trust assessment"], gate
    # Generate is not refused for it (#737): the unlock rule is unchanged.
    assert gate["unlocked"] is True, gate
    assert gate["synthesizable_missing"] == [], gate


def test_a_register_from_released_inputs_is_refused_as_changed_not_as_a_draft(
    app_client,  # noqa: F811
) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    _open_zt_revision(c, bearer, cid, s.zt_service, s.zt_assessment)
    r = _publish(c, bearer, cid)
    assert _blockers(r) == [{"input": "zt", "reason": "changed", "status": "draft"}]
    message = r.json()["error"]["message"]
    assert message == (
        "An assessment this register draws on has changed since it was generated: "
        "Zero Trust. Generate a new version before publishing."
    ), message
    assert "(draft" not in message, message
