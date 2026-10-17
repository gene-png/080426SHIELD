"""#1156: the Risk Register with a revision draft open, through `/revisions`.

ATT&CK and Zero Trust are released; then "Start a revision" (#1120) opens ZT
v2 as a DRAFT. Every Risk reader takes the latest record (`latest_record`), so
Generate drafts the ZT findings from v2.

1. The Generate gate's `not_finalized` must name the Zero Trust assessment:
   what Generate reads is a draft. It used to ask for ANY approved-or-released
   assessment, found the released v1 behind the draft, and listed nothing.
2. A register generated from the released v1 must not be refused as if it
   drew on a draft. The register drew on v1, and a newer DRAFT is open, so the
   blocker is `changed` and the sentence is the approved newer-draft one
   (advisor, #736 6225640724 item 5). It names both remedies: discard the
   draft and publish this register, or release the draft and generate again.
   "Generate a new version" alone would name a remedy that cannot publish,
   because that register would draw on the draft.

Every expected value is typed from the scenario, never read from the code.
"""

from __future__ import annotations

import pytest

from tests._risk_inputs import release, seed_attack_and_zt, seed_released
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


def test_a_register_from_released_inputs_names_the_newer_draft(
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
        "This register can't be published while a newer draft is open. Discard that "
        "draft, then publish again. Or release the draft, then generate a new version "
        "before publishing."
    ), message
    assert "(draft" not in message, message


def test_a_register_drawn_from_unreleased_work_is_not_told_to_discard_the_draft(
    app_client,  # noqa: F811
) -> None:
    """Review round 3 F1. ZT was only APPROVED at generate; a revision draft is
    then opened. Discarding that draft cannot make this register publishable
    (it drew on unreleased work, and releasing v1 later still meets `changed`),
    so the discard sentence would name a remedy that fails. The only remedy is
    a new version, which is the generic changed sentence."""
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    release(c, bearer, cid, "attack", s.attack_service)  # ZT stays approved
    _gen(c, provider, bearer, cid)
    _open_zt_revision(c, bearer, cid, s.zt_service, s.zt_assessment)
    r = _publish(c, bearer, cid)
    assert _blockers(r) == [{"input": "zt", "reason": "changed", "status": None}]
    message = r.json()["error"]["message"]
    assert message == (
        "An assessment this register draws on has changed since it was generated: "
        "Zero Trust. Generate a new version before publishing."
    ), message
    assert "Discard" not in message, message
