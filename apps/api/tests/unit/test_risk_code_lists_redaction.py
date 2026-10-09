"""#997 (the code lists): a Risk synthesis run sends the real catalog codes in
`valid_controls` and `valid_techniques`, even for a client named "GV" or "DoD".

Before this, strict redaction rewrote every string in the payload, so for a
client named "GV" each CSF code in `valid_controls` went out as
"[CLIENT].OC-01", and for one named "DoD" each DoD capability code as
"[CLIENT].USR.01" (measured on main aa099ac0). The model was handed an
allow-list of codes that do not exist. The two lists are now registered with
#985's catalog guard, as #986 registered the other services' code lists: sent
verbatim, each entry rebuilt from the catalog, and refused before egress when
an entry is not a catalog code.

`findings` is NOT exempt and stays redacted as before: it is nested, and its
design waits on the Risk E ruling (#997, the other half). The last assertion
of the collision test pins that this change leaves it alone.

Driven through the generate endpoint and read at the provider. Expected codes
come from the catalogs' own tables, never from the route that builds the lists.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ai.llm import LLMResponse
from app.ai.redact import redact_payload
from app.csf.catalog import SUBCATEGORIES
from app.models.llm_call import LLMCall
from app.zt.catalog import DOD_CAPABILITIES
from tests._attack_rows import standalone_rows

from .test_risk_register import app_client  # noqa: F401  -- the fixture, used by name below.

pytestmark = pytest.mark.unit

#: Two CSF codes that begin "GV.", in the catalog's own order.
CSF_CODES = [s.code for s in SUBCATEGORIES if s.code.startswith("GV.")][:2]
#: Two DoD capability codes, in the catalog's own order.
DOD_CODES = [c.code for c in DOD_CAPABILITIES][:2]


def _client_named(c, org: str) -> tuple[str, str]:
    bearer = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    ).json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients", headers={"Authorization": f"Bearer {bearer}"}, json={"legal_name": org}
    ).json()["id"]
    return bearer, cid


def _seed(c, bearer: str, cid: str) -> list[str]:
    """ATT&CK (two standalone gaps), CSF (two GV codes scored) and DoD ZT (two
    capabilities scored), each approved. Returns the scored technique codes."""
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}

    asvc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    a = c.post(f"/attack/services/{asvc.json()['id']}/assessments", headers=h).json()
    techniques = []
    for cov in standalone_rows(a["coverage"], 2):
        r = c.patch(f"/attack/coverage/{cov['id']}", headers=h, json={"status": "gap"})
        assert r.status_code == 200, r.text
        techniques.append(cov["technique_code"])
    r = c.post(f"/attack/assessments/{a['id']}/approve", headers=h)
    assert r.status_code == 200, r.text

    csvc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    ca = c.post(f"/csf/services/{csvc.json()['id']}/assessments", headers=h).json()
    for ans in ca["answers"]:
        if ans["subcategory_code"] in CSF_CODES:
            r = c.patch(f"/csf/answers/{ans['id']}", headers=h, json={"maturity_tier": 1})
            assert r.status_code == 200, r.text
    r = c.post(f"/csf/assessments/{ca['id']}/approve", headers=h)
    assert r.status_code == 200, r.text

    zsvc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_dod", "title": "ZT"})
    za = c.post(f"/zt/services/{zsvc.json()['id']}/assessments", headers=h).json()
    for ans in za["answers"]:
        if ans["capability_code"] in DOD_CODES:
            r = c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"maturity_stage": 1})
            assert r.status_code == 200, r.text
    r = c.post(f"/zt/assessments/{za['id']}/approve", headers=h)
    assert r.status_code == 200, r.text
    return techniques


def _redacted(value: Any, org: str) -> Any:
    out, _ = redact_payload({"v": value}, mode="strict", client_org_name=org)
    return out["v"]


def _risk_calls() -> list[LLMCall]:
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    try:
        with Session(engine) as db:
            return list(
                db.execute(select(LLMCall).where(LLMCall.purpose == "risk_synthesize")).scalars()
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize("org", ["GV", "DoD"])
def test_the_run_sends_the_real_codes_and_still_redacts_the_findings(
    app_client, org: str  # noqa: F811
) -> None:
    c, provider = app_client
    bearer, cid = _client_named(c, org)
    techniques = _seed(c, bearer, cid)
    controls = sorted(CSF_CODES + DOD_CODES)
    assert _redacted(controls, org) != controls, "the client name must collide to test anything"

    sent: list[dict[str, Any]] = []

    def _spy(payload: dict[str, Any]) -> LLMResponse:
        sent.append(payload)
        return LLMResponse(json.dumps({"entries": []}))

    provider.register("risk_synthesize", _spy)
    r = c.post(
        f"/risk/clients/{cid}/register/generate",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 201, r.text
    assert sent, "no risk_synthesize payload reached the provider"

    assert sent[0]["valid_controls"] == controls
    assert sent[0]["valid_techniques"] == sorted(techniques)
    # `findings` is not registered: a finding on a colliding code still goes
    # out redacted, exactly as before this change (the Risk E half of #997).
    colliding = [code for code in controls if _redacted(code, org) != code]
    assert colliding, "at least one scored code collides with the client name"
    finding_ids = {f["source_id"] for f in sent[0]["findings"]}
    for code in colliding:
        assert _redacted(code, org) in finding_ids
        assert code not in finding_ids


@pytest.mark.parametrize("field", ["valid_controls", "valid_techniques"])
def test_a_code_list_entry_the_catalog_does_not_have_is_refused_before_egress(
    app_client, monkeypatch, capsys, field: str  # noqa: F811
) -> None:
    """A value under either key that is not a catalog code would egress
    unredacted, so it is refused: no provider call, no `llm_calls` row, and a
    message that names the field and never the value."""
    from app.routes import risk as risk_routes

    c, provider = app_client
    bearer, cid = _client_named(c, "Acme")
    _seed(c, bearer, cid)
    token = "ZEBRA-PRIVATE-NOTE-7731"
    original = risk_routes._gather_findings

    def tampered(db, client_id, snapshot=None):
        findings, techniques, controls, targets, scopes = original(db, client_id, snapshot)
        if field == "valid_controls":
            controls = {*controls, token}
        else:
            techniques = {*techniques, token}
        return findings, techniques, controls, targets, scopes

    monkeypatch.setattr(risk_routes, "_gather_findings", tampered)
    calls: list[dict[str, Any]] = []

    def _spy(payload: dict[str, Any]) -> LLMResponse:
        calls.append(payload)
        return LLMResponse(json.dumps({"entries": []}))

    provider.register("risk_synthesize", _spy)
    r = c.post(
        f"/risk/clients/{cid}/register/generate",
        headers={"Authorization": f"Bearer {bearer}"},
    )

    assert r.status_code == 502, r.text
    detail = r.json()["error"]
    assert detail["reason"] == "ai_call_failed"
    assert f"payload field '{field}' could not be rebuilt from the catalog" in detail["message"]
    assert token not in r.text
    assert calls == [], "nothing may reach the provider"
    assert _risk_calls() == [], "no llm_calls row is written for a refused payload"
    captured = capsys.readouterr()
    assert token not in captured.out + captured.err
