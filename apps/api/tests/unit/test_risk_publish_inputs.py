"""#737, Gene's rule: a register is published only when every engaged input is
RELEASED and is still the version it was generated from.

Through the real routes: inputs are released by finalizing and releasing their
deliverables (`tests/_risk_inputs.py`), and the refusal is read from publish.
"""

from __future__ import annotations

import pytest

from app.ai.llm import LLMResponse
from tests._risk_inputs import release, seed_attack_and_zt, seed_released
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _entries_payload,
    _entry,
    _session,
    app_client,
)

pytestmark = pytest.mark.unit


def _gen(c, provider, bearer: str, cid: str) -> dict:
    # One rated entry, so the unrated-entry refusal (D1) never masks the
    # input refusal under test.
    provider.register_static("risk_synthesize", LLMResponse(_entries_payload(_entry("R"))))
    r = c.post(
        f"/risk/clients/{cid}/register/generate", headers={"Authorization": f"Bearer {bearer}"}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _publish(c, bearer: str, cid: str):
    return c.post(
        f"/risk/clients/{cid}/register/publish", headers={"Authorization": f"Bearer {bearer}"}
    )


def _blockers(r) -> list[dict]:
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["reason"] == "risk_register_inputs_not_final", err
    return err["blockers"]


def test_every_engaged_input_released_publishes(app_client) -> None:  # noqa: F811
    """ATT&CK and ZT released; the client has no CSF or Tech Debt service, so
    neither is engaged and neither holds publication up."""
    c, provider = app_client
    bearer, cid = _admin(c)
    seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    r = _publish(c, bearer, cid)
    assert r.status_code == 200, r.text


def test_an_approved_but_unreleased_input_blocks_and_is_named(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    release(c, bearer, cid, "zt", s.zt_service)
    _gen(c, provider, bearer, cid)
    r = _publish(c, bearer, cid)
    assert _blockers(r) == [{"input": "attack", "reason": "not_released", "status": "approved"}]
    assert r.json()["error"]["message"] == (
        "This register cannot be published until every assessment it draws on is "
        "released: ATT&CK coverage (approved, not yet released)."
    )


def test_an_engaged_service_with_no_assessment_blocks(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    seed_released(c, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    r = c.post("/tech-debt/services", headers=h, json={"kind": "tech_debt", "title": "TD"})
    assert r.status_code in (200, 201), r.text
    _gen(c, provider, bearer, cid)
    assert _blockers(_publish(c, bearer, cid)) == [
        {"input": "tech_debt", "reason": "not_started", "status": None}
    ]


def test_a_newer_version_after_generate_blocks(app_client) -> None:  # noqa: F811
    """Released at generate, then a new ATT&CK version is opened: the register
    was built from the old one and must be regenerated."""
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    v2 = c.post(f"/attack/services/{s.attack_service}/assessments", headers=h)
    assert v2.status_code in (200, 201), v2.text
    assert _blockers(_publish(c, bearer, cid)) == [
        {"input": "attack", "reason": "not_released", "status": "draft"}
    ]


def test_a_register_generated_before_its_inputs_were_released_blocks(
    app_client,  # noqa: F811
) -> None:
    """Generated while ATT&CK was only approved; ATT&CK is released afterwards.
    The inputs are final NOW, but the register was not built from final work."""
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    release(c, bearer, cid, "zt", s.zt_service)
    _gen(c, provider, bearer, cid)
    release(c, bearer, cid, "attack", s.attack_service)
    r = _publish(c, bearer, cid)
    assert _blockers(r) == [{"input": "attack", "reason": "changed", "status": "released"}]
    assert r.json()["error"]["message"] == (
        "An assessment this register draws on has changed since it was generated: "
        "ATT&CK coverage. Generate a new version before publishing."
    )


def test_a_register_with_no_input_record_blocks(app_client) -> None:  # noqa: F811
    from sqlalchemy import select

    from app.models.risk_register import RiskRegister

    c, provider = app_client
    bearer, cid = _admin(c)
    seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    with _session() as s:
        reg = s.execute(select(RiskRegister)).scalar_one()
        prov = dict(reg.provenance)
        prov.pop("current_inputs")
        reg.provenance = prov
        s.commit()
    assert _blockers(_publish(c, bearer, cid)) == [
        {"input": "register", "reason": "not_recorded", "status": None}
    ]


def test_the_gate_lists_every_input_and_its_state(app_client) -> None:  # noqa: F811
    """The Inputs panel's data, from the same reader publish uses."""
    c, _ = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    release(c, bearer, cid, "zt", s.zt_service)
    g = c.get(f"/risk/clients/{cid}/gate", headers={"Authorization": f"Bearer {bearer}"})
    assert g.status_code == 200, g.text
    assert g.json()["inputs"] == [
        {"kind": "attack", "engaged": True, "status": "approved", "version": 1},
        {"kind": "csf", "engaged": False, "status": None, "version": None},
        {"kind": "zt", "engaged": True, "status": "released", "version": 1},
        {"kind": "tech_debt", "engaged": False, "status": None, "version": None},
    ]
