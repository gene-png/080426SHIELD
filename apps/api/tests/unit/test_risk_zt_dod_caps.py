"""Risk synthesis applies the DoD target cap (#839), through the shared resolver.

A DoD capability with no Advanced activity can never score 3, so under the cap
its target is 2 and a stage-2 answer is at target: the ZT deliverable lists no
gap for it, and Risk must not raise a finding for it either. Risk applied a
per-capability target raw and the engagement target unchecked, so it would
have kept a finding the deliverable says does not exist.

The world: an ATT&CK gap (the register's gate) and an approved DoD assessment
whose client chose stage 3 at intake, with 1.1 User Inventory (no Advanced
activity) and 1.2 Conditional User Access (has Advanced activities) both at
stage 2. Driven through the generate endpoint and read at the egress payload.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.ai.llm import LLMResponse
from tests._attack_rows import first_standalone

from .test_risk_register import (
    _admin,
    app_client,  # noqa: F401  -- the fixture, used by name below.
)
from .test_zt_dashboard import _attach_intake_target

pytestmark = pytest.mark.unit

NO_ADVANCED = "DOD.USR.01"  # 1.1 User Inventory
HAS_ADVANCED = "DOD.USR.02"  # 1.2 Conditional User Access


def _seed(c, bearer: str, cid: str) -> None:
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    asvc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    a = c.post(f"/attack/services/{asvc.json()['id']}/assessments", headers=h)
    cov = first_standalone(a.json()["coverage"])
    r = c.patch(f"/attack/coverage/{cov['id']}", headers=h, json={"status": "gap"})
    assert r.status_code == 200, r.text
    r = c.post(f"/attack/assessments/{a.json()['id']}/approve", headers=h)
    assert r.status_code == 200, r.text

    zsvc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_dod", "title": "ZT"})
    _attach_intake_target(zsvc.json()["id"], zt_stage=3)
    za = c.post(f"/zt/services/{zsvc.json()['id']}/assessments", headers=h).json()
    for ans in za["answers"]:
        if ans["capability_code"] in (NO_ADVANCED, HAS_ADVANCED):
            r = c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"maturity_stage": 2})
            assert r.status_code == 200, r.text
    zr = c.post(f"/zt/assessments/{za['id']}/approve", headers=h)
    assert zr.status_code == 200, zr.text


def test_a_capped_capability_at_target_is_no_risk_finding(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed(c, bearer, cid)

    seen: list[dict[str, Any]] = []

    def capture(payload: dict[str, Any]) -> LLMResponse:
        seen.append(payload)
        return LLMResponse(json.dumps({"entries": []}))

    provider.register("risk_synthesize", capture)
    r = c.post(
        f"/risk/clients/{cid}/register/generate",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 201, r.text
    assert seen, "no risk_synthesize payload was captured"
    finding_ids = {f["source_id"] for f in seen[0]["findings"]}
    assert HAS_ADVANCED in finding_ids  # below its target of 3: what must appear, first
    assert NO_ADVANCED not in finding_ids  # at its capped target of 2
