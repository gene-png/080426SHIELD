"""#474, the minimum: a register says which target its findings were measured
against.

`_gather_findings` returned `target_sources`, and it reached only the audit
row: no schema, no screen, no export. So the baseline a register was computed
against was invisible to the client and to the consultant, and a register
measured against a different target than the released CSF or ZT report had
nothing on it that would let anyone notice.

It is now persisted with the register (provenance `targets`, a generate-time
fact) and reaches the admin response, the client dashboard and the three
exports. Three states: recorded, recorded with the default, and not recorded
(a register generated before this), which the export states rather than
leaving silent.
"""

from __future__ import annotations

import pytest

from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _entries_payload,
    _entry,
    _generate,
    _pdf_text,
    _seed_attack_and_zt,
    _seed_csf_answer_at_tier,
    _session,
    _set_csf_target,
    app_client,
)

pytestmark = pytest.mark.unit


def _latest(c, bearer: str, cid: str) -> dict:
    r = c.get(
        f"/risk/clients/{cid}/register/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _export_pdf_text(c, bearer: str, cid: str) -> str:
    bh = {"Authorization": f"Bearer {bearer}"}
    ex = c.post(f"/risk/clients/{cid}/register/export", headers=bh)
    assert ex.status_code == 200, ex.text
    pdf = c.get(
        f"/artifacts/{ex.json()['pdf_artifact_id']}/download",
        headers={**bh, "X-Client-Id": cid},
    )
    return " ".join(_pdf_text(pdf.content).split())


def _world(app_client, *, csf_target: int | None = None):  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    if csf_target is not None:
        _seed_csf_answer_at_tier(c, bearer, cid, tier=1)
        _set_csf_target(cid, csf_target)
    _generate(c, provider, bearer, cid, _entries_payload(_entry("R")))
    return c, bearer, cid


def test_the_register_records_each_services_target(app_client) -> None:  # noqa: F811
    c, bearer, cid = _world(app_client, csf_target=4)
    body = _latest(c, bearer, cid)
    assert body["targets_recorded"] is True
    by_service = {t["service"]: t for t in body["targets"]}
    assert by_service["csf"] == {
        "service": "csf",
        "target": 4,
        "source": "client",
        "origin": "live_at_generate",
    }
    # No ZT target was set, so ZT used the engine default and says so.
    assert by_service["zt"]["source"] == "default"
    assert by_service["zt"]["origin"] == "live_at_generate"


def test_the_export_states_the_baseline(app_client) -> None:  # noqa: F811
    c, bearer, cid = _world(app_client, csf_target=4)
    zt = {t["service"]: t for t in _latest(c, bearer, cid)["targets"]}["zt"]
    text = _export_pdf_text(c, bearer, cid)
    assert (
        "NIST CSF findings are measured against target tier 4, the engagement "
        "target when this register was generated." in text
    )
    assert (
        f"Zero Trust findings are measured against target stage {zt['target']}, "
        "SHIELD's default: no engagement target was set." in text
    )


def test_a_register_without_the_record_says_so(app_client) -> None:  # noqa: F811
    from sqlalchemy import select

    from app.models.risk_register import RiskRegister

    c, bearer, cid = _world(app_client)
    with _session() as s:
        reg = s.execute(select(RiskRegister)).scalar_one()
        prov = dict(reg.provenance)
        prov.pop("targets")
        reg.provenance = prov
        s.commit()
    body = _latest(c, bearer, cid)
    assert body["targets_recorded"] is False
    assert body["targets"] == []
    text = _export_pdf_text(c, bearer, cid)
    assert (
        "The targets these findings were measured against were not recorded for "
        "this register." in text
    )
    assert "findings are measured against target" not in text


def test_the_client_dashboard_carries_the_baseline(app_client) -> None:  # noqa: F811
    """The client's screen, read as a client user, after publication."""
    c, bearer, cid = _world(app_client, csf_target=4)
    ah = {"Authorization": f"Bearer {bearer}"}
    c.post(f"/admin/clients/{cid}/domains", headers=ah, json={"domain": "acme.example"})
    user = c.post(
        "/auth/register",
        json={
            "email": "user@acme.example",
            "password": "correct horse battery staple!",
            "display_name": "U",
        },
    )
    ch = {"Authorization": f"Bearer {user.json()['tokens']['access_token']}", "X-Client-Id": cid}
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.models.risk_register import RiskRegister

    # Released the way `seed_demo.py` releases one: this PR is stacked under
    # #737's publish route and must not depend on it.
    with _session() as s:
        reg = s.execute(select(RiskRegister)).scalar_one()
        reg.finalized_at = datetime.now(UTC)
        s.commit()
    r = c.get(f"/clients/{cid}/risk/dashboard", headers=ch)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["targets_recorded"] is True
    assert {t["service"]: t["target"] for t in body["targets"]}["csf"] == 4
