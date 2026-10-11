"""A kept ID.AM-09 answer feeds no Risk finding and is not citable (#852).

The twin of `test_risk_zt_retired_rows.py`. The CSF catalog no longer has
`ID.AM-09` (NIST CSF 2.0 has no such subcategory), the migration KEEPS the
answers stored under it, and the CSF workspace and deliverable say they are not
scored. Risk synthesis read every stored CSF row, so a kept row below target
still became a client-facing finding and stayed in the allow-list the model
cites from.

The world: `_seed_attack_and_zt` plus an approved CSF assessment with one
catalog Playbook row below its target, and a Playbook row on `ID.AM-09` below
its target, as an assessment provisioned before #852 holds it (#474 D': Risk
reads the Playbook). Driven through generate, read at
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
    """#474 D': Risk reads the Playbook, so the kept row is a Working Profile
    row on `ID.AM-09`, written as a consultant would have before #852."""
    from app.models.csf_assessment import CsfAssessment
    from app.models.csf_profile import CsfDimensionScore
    from tests._csf_playbook_rows import score_csf_playbook

    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    a = c.post(f"/csf/services/{svc.json()['id']}/assessments", headers=h).json()
    scored = a["answers"][0]
    score_csf_playbook(c, h, svc.json()["id"], {scored["subcategory_code"]: (1, 5)})
    db = _session()
    row = db.get(CsfAssessment, uuid.UUID(a["id"]))
    db.add(
        CsfDimensionScore(
            assessment_id=row.id,
            client_id=row.client_id,
            tier="high",
            subcategory_code=RETIRED,
            in_scope=True,
            has_evidence=True,
            target_level=5,
            answer_source="consultant",
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
    finding_ids = set(seen[0]["findings"])
    # The scored catalog row still flows: what must appear, first.
    assert subcategory in controls
    assert subcategory in finding_ids
    # The kept row does not.
    assert RETIRED not in controls
    assert RETIRED not in finding_ids
