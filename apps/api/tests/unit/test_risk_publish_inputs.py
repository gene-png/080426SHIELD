"""#737, Gene's rule: a register is published only when every engaged input is
RELEASED and is still the version it was generated from.

Through the real routes: inputs are released by finalizing and releasing their
deliverables (`tests/_risk_inputs.py`), and the refusal is read from publish.
"""

from __future__ import annotations

import uuid

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


# ---------------------------------------------------------------------------
# #860 review, round 1 (B1-B3)
# ---------------------------------------------------------------------------


def _h(bearer: str, cid: str) -> dict:
    return {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}


def _register_provenance() -> dict:
    from sqlalchemy import select

    from app.models.risk_register import RiskRegister

    with _session() as s:
        reg = s.execute(
            select(RiskRegister).order_by(RiskRegister.version.desc()).limit(1)
        ).scalar_one()
        return dict(reg.provenance)


def _edit_recorded(kind: str, **changes) -> None:
    """Rewrite one recorded input. Used ONLY where no route can produce the
    state, and each test that uses it says so."""
    from sqlalchemy import select

    from app.models.risk_register import RiskRegister

    with _session() as s:
        reg = s.execute(select(RiskRegister)).scalar_one()
        prov = dict(reg.provenance)
        rows = [dict(r) for r in prov["current_inputs"]]
        hits = [r for r in rows if r["kind"] == kind]
        assert len(hits) == 1, rows
        hits[0].update(changes)
        prov["current_inputs"] = rows
        reg.provenance = prov
        s.commit()


def _new_version_released(c, bearer: str, cid: str, prefix: str, service_id: str) -> str:
    """Open the next assessment version of `service_id`, approve it, release it."""
    h = _h(bearer, cid)
    v = c.post(f"/{prefix}/services/{service_id}/assessments", headers=h)
    assert v.status_code in (200, 201), v.text
    assert v.json()["version"] == 2, v.json()
    ap = c.post(f"/{prefix}/assessments/{v.json()['id']}/approve", headers=h)
    assert ap.status_code == 200, ap.text
    release(c, bearer, cid, prefix, service_id)
    return v.json()["id"]


def _new_zt_dod(c, bearer: str, cid: str) -> tuple[str, str]:
    h = _h(bearer, cid)
    svc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_dod", "title": "ZT DoD"})
    assert svc.status_code in (200, 201), svc.text
    a = c.post(f"/zt/services/{svc.json()['id']}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    return svc.json()["id"], a.json()["id"]


def test_an_input_released_during_synthesis_stays_labelled_and_blocks(
    app_client, monkeypatch  # noqa: F811
) -> None:
    """B1. ATT&CK is APPROVED when Generate is clicked and is released while
    the model call runs. The register was drafted from approved work: its
    findings stay labelled and it must not publish. Before the fix the
    provenance was read AFTER the call and recorded "released"."""
    from sqlalchemy import update

    from app.models.attack_assessment import AttackAssessment, AttackAssessmentStatus
    from app.routes import risk as risk_routes

    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    release(c, bearer, cid, "zt", s.zt_service)

    original = risk_routes._run_risk_synthesize_batched
    calls: list[int] = []

    def released_mid_run(db, *args, **kwargs):
        # Another request's release, committed while this one waits on the
        # model: its own session, as the release route would be.
        with _session() as other:
            other.execute(
                update(AttackAssessment)
                .where(AttackAssessment.id == uuid.UUID(s.attack_assessment))
                .values(status=AttackAssessmentStatus.RELEASED)
            )
            other.commit()
        calls.append(1)
        return original(db, *args, **kwargs)

    monkeypatch.setattr(risk_routes, "_run_risk_synthesize_batched", released_mid_run)
    body = _gen(c, provider, bearer, cid)
    assert calls == [1], "the mid-run release never happened"

    prov = _register_provenance()
    recorded = {r["kind"]: r["status"] for r in prov["current_inputs"]}
    assert recorded == {"attack": "approved", "zt": "released"}, prov["current_inputs"]
    assert prov["source_states"] == {s.technique: "approved"}, prov["source_states"]
    assert [e["source_state"] for e in body["entries"]] == [None], body["entries"]
    assert _blockers(_publish(c, bearer, cid)) == [
        {"input": "attack", "reason": "changed", "status": "released"}
    ]


def test_a_finding_with_no_snapshot_status_fails_closed(
    app_client, monkeypatch  # noqa: F811
) -> None:
    """B1, the fallback. A finding whose kind the snapshot has no status for
    must not be recorded as drafted from released work. No path produces one;
    the test injects it, and generate must raise rather than default."""
    from app.routes import risk as risk_routes

    c, provider = app_client
    bearer, cid = _admin(c)
    seed_released(c, bearer, cid)
    original = risk_routes._gather_findings

    def with_a_csf_finding(db, client_id, snapshot=None):
        out = original(db, client_id, snapshot)
        out[0].append(
            {
                "source": "questionnaire_response",
                "source_id": "GV.OC-01",
                "kind": "csf",
                "label": "CSF GV.OC-01: tier 1",
            }
        )
        return out

    monkeypatch.setattr(risk_routes, "_gather_findings", with_a_csf_finding)
    provider.register_static("risk_synthesize", LLMResponse(_entries_payload(_entry("R"))))
    with pytest.raises(RuntimeError, match="no input status in the snapshot"):
        c.post(f"/risk/clients/{cid}/register/generate", headers=_h(bearer, cid))


def test_an_archived_service_is_not_an_input(app_client) -> None:  # noqa: F811
    """B2 (a). The ATT&CK service with v2 RELEASED is archived; a new ATT&CK
    service has v1 DRAFT. The draft is the input -- in the gate, in what
    synthesis reads, and in publish."""
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_released(c, bearer, cid)
    _new_version_released(c, bearer, cid, "attack", s.attack_service)
    h = _h(bearer, cid)
    gone = c.delete(f"/admin/services/{s.attack_service}", headers=h)
    assert gone.status_code == 204, gone.text
    nsvc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A2"})
    assert nsvc.status_code in (200, 201), nsvc.text
    na = c.post(f"/attack/services/{nsvc.json()['id']}/assessments", headers=h)
    assert na.status_code in (200, 201), na.text

    g = c.get(f"/risk/clients/{cid}/gate", headers=h).json()
    assert [r for r in g["inputs"] if r["kind"] == "attack"] == [
        {"kind": "attack", "engaged": True, "status": "draft", "version": 1}
    ]
    _gen(c, provider, bearer, cid)
    prov = _register_provenance()
    assert [i["assessment_id"] for i in prov["inputs"] if i["kind"] == "attack"] == [
        na.json()["id"]
    ], prov["inputs"]
    assert _blockers(_publish(c, bearer, cid)) == [
        {"input": "attack", "reason": "not_released", "status": "draft"}
    ]


def test_every_engaged_zero_trust_service_must_be_released(app_client) -> None:  # noqa: F811
    """B2 (b). CISA has v2 RELEASED; a DoD service has v1 DRAFT. Both are
    engaged, so the DoD draft blocks even though CISA's is the newer version."""
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_released(c, bearer, cid)
    _new_version_released(c, bearer, cid, "zt", s.zt_service)
    _new_zt_dod(c, bearer, cid)
    g = c.get(f"/risk/clients/{cid}/gate", headers=_h(bearer, cid)).json()
    assert [r for r in g["inputs"] if r["kind"] == "zt"] == [
        {"kind": "zt", "engaged": True, "status": "released", "version": 2},
        {"kind": "zt", "engaged": True, "status": "draft", "version": 1},
    ]
    _gen(c, provider, bearer, cid)
    assert _blockers(_publish(c, bearer, cid)) == [
        {"input": "zt", "reason": "not_released", "status": "draft"}
    ]


def test_a_second_tech_debt_service_with_no_list_blocks(app_client) -> None:  # noqa: F811
    """B2 (c). One Tech Debt service has a RELEASED list, another has none.
    The second is engaged and not started.

    The released list is written directly: a Tech Debt release runs the
    extraction pipeline, which this file does not drive. RELEASED is a state
    the product reaches (finalize then release), so the setup builds a
    reachable world rather than an outcome."""
    from app.models.capability import CapabilityList, CapabilityListStatus

    c, provider = app_client
    bearer, cid = _admin(c)
    seed_released(c, bearer, cid)
    h = _h(bearer, cid)
    td1 = c.post("/tech-debt/services", headers=h, json={"kind": "tech_debt", "title": "TD1"})
    td2 = c.post("/tech-debt/services", headers=h, json={"kind": "tech_debt", "title": "TD2"})
    assert td1.status_code in (200, 201) and td2.status_code in (200, 201)
    with _session() as db:
        db.add(
            CapabilityList(
                service_id=uuid.UUID(td1.json()["id"]),
                version=1,
                status=CapabilityListStatus.RELEASED,
            )
        )
        db.commit()
    g = c.get(f"/risk/clients/{cid}/gate", headers=h).json()
    assert [r for r in g["inputs"] if r["kind"] == "tech_debt"] == [
        {"kind": "tech_debt", "engaged": True, "status": "released", "version": 1},
        {"kind": "tech_debt", "engaged": True, "status": None, "version": None},
    ]
    _gen(c, provider, bearer, cid)
    assert _blockers(_publish(c, bearer, cid)) == [
        {"input": "tech_debt", "reason": "not_started", "status": None}
    ]


def test_a_newer_released_version_after_generate_is_changed(app_client) -> None:  # noqa: F811
    """B3. Generated from ATT&CK v1 released; v2 is then opened, approved and
    RELEASED. Every input is released, and the register was not built from
    the current one."""
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    _new_version_released(c, bearer, cid, "attack", s.attack_service)
    assert _blockers(_publish(c, bearer, cid)) == [
        {"input": "attack", "reason": "changed", "status": "released"}
    ]


def test_a_different_record_at_the_same_version_is_changed(app_client) -> None:  # noqa: F811
    """B3, the record half on its own. NOT reachable through a route today: a
    new record is always a new version, so the record id and the version move
    together. Pinned by rewriting the stored record, so the record clause holds
    without leaning on the version clause."""
    c, provider = app_client
    bearer, cid = _admin(c)
    seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    _edit_recorded("attack", record_id=str(uuid.uuid4()))
    assert _blockers(_publish(c, bearer, cid)) == [
        {"input": "attack", "reason": "changed", "status": "released"}
    ]


def test_the_same_record_at_another_version_is_changed(app_client) -> None:  # noqa: F811
    """B3, the version half on its own. Unreachable through a route for the
    same reason as the test above; pinned by rewriting the stored version."""
    c, provider = app_client
    bearer, cid = _admin(c)
    seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    _edit_recorded("zt", version=7)
    assert _blockers(_publish(c, bearer, cid)) == [
        {"input": "zt", "reason": "changed", "status": "released"}
    ]


def test_a_service_engaged_after_generate_is_changed(app_client) -> None:  # noqa: F811
    """B3, the absent record. A Zero Trust DoD service is opened, approved and
    released after the register was generated: it is released, and the
    register never saw it."""
    c, provider = app_client
    bearer, cid = _admin(c)
    seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    svc, a = _new_zt_dod(c, bearer, cid)
    h = _h(bearer, cid)
    assert c.post(f"/zt/assessments/{a}/approve", headers=h).status_code == 200
    release(c, bearer, cid, "zt", svc)
    assert _blockers(_publish(c, bearer, cid)) == [
        {"input": "zt", "reason": "changed", "status": "released"}
    ]


# ---------------------------------------------------------------------------
# #860 review, round 2 (F1, F4)
# ---------------------------------------------------------------------------


def test_a_service_archived_after_generate_blocks(app_client) -> None:  # noqa: F811
    """F1. ZT is APPROVED at generate, so the register carries ZT findings
    labelled "approved". The ZT service is then archived. Its findings are
    still in the register, so publish must refuse -- before the fix the check
    walked only today's services, and the archived input dropped out."""
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    release(c, bearer, cid, "attack", s.attack_service)
    _gen(c, provider, bearer, cid)
    assert _register_provenance()["source_states"] == {s.capability: "approved"}
    gone = c.delete(f"/admin/services/{s.zt_service}", headers=_h(bearer, cid))
    assert gone.status_code == 204, gone.text
    r = _publish(c, bearer, cid)
    assert _blockers(r) == [{"input": "zt", "reason": "changed", "status": None}]
    assert r.json()["error"]["message"] == (
        "An assessment this register draws on has changed since it was generated: "
        "Zero Trust. Generate a new version before publishing."
    )


def test_an_archived_approved_assessment_does_not_count_as_finalized(
    app_client,  # noqa: F811
) -> None:
    """F4. The gate's `not_finalized` report counts the same population as
    unlock and synthesis: an APPROVED assessment on an archived ZT service does
    not make a live ZT draft read as finalized."""
    c, _ = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    h = _h(bearer, cid)
    assert c.delete(f"/admin/services/{s.zt_service}", headers=h).status_code == 204
    _new_zt_dod(c, bearer, cid)
    g = c.get(f"/risk/clients/{cid}/gate", headers=h).json()
    assert "the Zero Trust assessment" in g["not_finalized"], g["not_finalized"]
