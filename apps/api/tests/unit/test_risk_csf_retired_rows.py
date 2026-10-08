"""A kept ID.AM-09 answer feeds no Risk finding and is not citable (#852).

The twin of `test_risk_zt_retired_rows.py`. The CSF catalog no longer has
`ID.AM-09` (NIST CSF 2.0 has no such subcategory), the migration KEEPS the
answers stored under it, and the CSF workspace and deliverable say they are not
scored. Risk synthesis read every stored CSF row, so a kept row below target
still became a client-facing finding and stayed in the allow-list the model
cites from.

The world: `_seed_attack_and_zt` plus an approved CSF assessment with one
catalog row scored below target, and a row on `ID.AM-09` at tier 1, as an
assessment provisioned before #852 holds it. Driven through generate, read at
the egress payload.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from app.ai.llm import LLMResponse

from .test_risk_register import (
    _admin,
    _seed_attack_and_zt,
    _session,
    app_client,  # noqa: F401  -- the fixture, used by name below.
)

pytestmark = pytest.mark.unit

RETIRED = "ID.AM-09"


def _approved_csf_with_kept_row(c, bearer: str, cid: str) -> str:
    from app.models.csf_assessment import CsfAnswer, CsfAssessment

    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    a = c.post(f"/csf/services/{svc.json()['id']}/assessments", headers=h).json()
    scored = a["answers"][0]
    r = c.patch(f"/csf/answers/{scored['id']}", headers=h, json={"maturity_tier": 1})
    assert r.status_code == 200, r.text
    db = _session()
    row = db.get(CsfAssessment, uuid.UUID(a["id"]))
    db.add(
        CsfAnswer(
            assessment_id=row.id,
            client_id=row.client_id,
            subcategory_code=RETIRED,
            maturity_tier=1,
        )
    )
    db.commit()
    db.close()
    ar = c.post(f"/csf/assessments/{a['id']}/approve", headers=h)
    assert ar.status_code == 200, ar.text
    return scored["subcategory_code"]


def test_a_kept_csf_row_below_target_is_no_finding_and_not_citable(
    app_client,  # noqa: F811
) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    subcategory = _approved_csf_with_kept_row(c, bearer, cid)

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

    controls = set(seen[0]["valid_controls"])
    finding_ids = {f["source_id"] for f in seen[0]["findings"]}
    # The scored catalog row still flows: what must appear, first.
    assert subcategory in controls
    assert subcategory in finding_ids
    # The kept row does not.
    assert RETIRED not in controls
    assert RETIRED not in finding_ids
