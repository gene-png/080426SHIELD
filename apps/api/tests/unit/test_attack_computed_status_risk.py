"""#554 R3: risk synthesis refuses an ATT&CK assessment whose computed statuses
nobody has reviewed (the advisor's ruling, 2026-10-03 00:35Z: fail-closed).

An APPROVED assessment with an unreviewed queue cannot be released, and the
same statuses must not reach a register the client can export either. Through
the generate endpoint; the refusal's words are the build's copy, written out.
"""

from __future__ import annotations

import pytest

from app.ai.llm import LLMResponse
from tests._attack_rows import standalone_rows
from tests.unit.test_risk_register import _admin, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

ALL_THREE = {
    "detection_tools": ["Tool D"],
    "prevention_tools": ["Tool P"],
    "response_tools": ["Tool R"],
}


def _approved_attack_and_zt(c, bearer: str, cid: str, n: int = 1) -> tuple[dict, str]:
    """An approved R3 ATT&CK assessment whose one scored row the AI called Gap
    with all three in place (computed: Covered, so it awaits review), and an
    approved ZT assessment so the register is unlocked."""
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    a = c.post(f"/attack/services/{svc.json()['id']}/assessments", headers=h).json()
    rows = standalone_rows(a["coverage"], n)
    for cov in rows:
        r = c.patch(f"/attack/coverage/{cov['id']}", headers=h, json={"status": "gap", **ALL_THREE})
        assert r.status_code == 200, r.text
        assert r.json()["in_review_queue"] is True
    cov = rows[0]
    zsvc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "ZT"})
    za = c.post(f"/zt/services/{zsvc.json()['id']}/assessments", headers=h).json()
    zans = za["answers"][0]
    c.patch(f"/zt/answers/{zans['id']}", headers=h, json={"maturity_stage": 1})
    assert c.post(f"/attack/assessments/{a['id']}/approve", headers=h).status_code == 200
    assert c.post(f"/zt/assessments/{za['id']}/approve", headers=h).status_code == 200
    return {"assessment": a, "code": cov["technique_code"]}, zans["capability_code"]


def test_generate_refuses_an_unreviewed_computed_assessment(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    world, capability = _approved_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}

    refused = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert refused.status_code == 409, refused.text
    body = refused.json()
    detail = body.get("error", body.get("detail", body))
    assert detail["reason"] == "attack_computed_status_unreviewed", detail
    assert detail["message"] == (
        "The Risk Register cannot be generated yet: 1 ATT&CK technique has a computed "
        "status that differs from the AI's suggestion and has not been reviewed. Review "
        "it in the ATT&CK Computed status review panel, then generate again."
    )
    assert detail["unreviewed"] == [world["code"]]

    # Reviewed: the same request goes through.
    h = {**bh, "X-Client-Id": cid}
    r = c.post(
        f"/attack/assessments/{world['assessment']['id']}/computed-status-review",
        headers=h,
        json={"reviews": [{"code": world["code"], "computed_status": "covered"}]},
    )
    assert r.status_code == 200, r.text
    provider.register_static(
        "risk_synthesize",
        LLMResponse(
            '{"entries": [{"title": "Exposure", "description": "d", "axis": "detection",'
            ' "source": "control_gap", "source_id": "' + capability + '",'
            ' "linked_techniques": [], "linked_controls": ["' + capability + '"],'
            ' "likelihood": "high", "impact": "major",'
            ' "recommended_action": "remediate", "rationale": "r"}]}'
        ),
    )
    ok = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert ok.status_code == 201, ok.text


def test_the_refusal_counts_in_the_plural(app_client) -> None:  # noqa: F811
    c, _provider = app_client
    bearer, cid = _admin(c)
    _approved_attack_and_zt(c, bearer, cid, n=2)
    refused = c.post(
        f"/risk/clients/{cid}/register/generate", headers={"Authorization": f"Bearer {bearer}"}
    )
    assert refused.status_code == 409, refused.text
    body = refused.json()
    detail = body.get("error", body.get("detail", body))
    assert detail["message"] == (
        "The Risk Register cannot be generated yet: 2 ATT&CK techniques have a computed "
        "status that differs from the AI's suggestion and has not been reviewed. Review "
        "them in the ATT&CK Computed status review panel, then generate again."
    )


def test_the_gate_carries_the_same_sentence(app_client) -> None:  # noqa: F811
    """The review's F3, the #556 precedent: the gate asks the SAME predicate as
    generate and carries the SAME sentence, or it offers a Generate whose only
    outcome is the 409."""
    c, _provider = app_client
    bearer, cid = _admin(c)
    world, _capability = _approved_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}

    gate = c.get(f"/risk/clients/{cid}/gate", headers=bh).json()
    refused = c.post(f"/risk/clients/{cid}/register/generate", headers=bh).json()
    refusal = refused.get("error", refused.get("detail", refused))
    assert gate["attack_computed_status_unreviewed"] == refusal["message"]
    assert gate["attack_computed_status_unreviewed"].startswith(
        "The Risk Register cannot be generated yet: 1 ATT&CK technique has"
    )

    r = c.post(
        f"/attack/assessments/{world['assessment']['id']}/computed-status-review",
        headers={**bh, "X-Client-Id": cid},
        json={"reviews": [{"code": world["code"], "computed_status": "covered"}]},
    )
    assert r.status_code == 200, r.text
    gate = c.get(f"/risk/clients/{cid}/gate", headers=bh).json()
    assert gate["attack_computed_status_unreviewed"] is None
