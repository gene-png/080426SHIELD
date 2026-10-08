"""A retired ZT row feeds no Risk finding and is not citable (#838 PR 2).

Migration 0063 KEEPS the answers on the rows CISA ZTMM 2.0 does not have, and
the ZT workspace and deliverables say those answers are not scored. Risk
synthesis read every stored row, so a retired row below target still became a
client-facing Risk finding and stayed in the allow-list the model cites from:
the deliverable said "not scored" while the register scored it.

The world: `_seed_attack_and_zt` (one approved CISA assessment, one scored row)
plus a row on a retired code at stage 1, exactly as migration 0063 leaves an
old answer. Driven through the generate endpoint, read at the egress payload.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import select

from app.ai.llm import LLMResponse

from .test_risk_register import (
    _admin,
    _seed_attack_and_zt,
    _session,
    app_client,  # noqa: F401  -- the fixture, used by name below.
)

pytestmark = pytest.mark.unit

RETIRED = "CISA.GV.01"  # a pre-#838 Governance-pillar row; not in CISA ZTMM 2.0


def _keep_retired_row(cid: str) -> None:
    from app.models.zt_assessment import ZtAnswer

    db = _session()
    scored = db.execute(
        select(ZtAnswer).where(
            ZtAnswer.client_id == uuid.UUID(cid), ZtAnswer.maturity_stage.is_not(None)
        )
    ).scalar_one()
    db.add(
        ZtAnswer(
            assessment_id=scored.assessment_id,
            client_id=scored.client_id,
            capability_code=RETIRED,
            maturity_stage=1,
        )
    )
    db.commit()
    db.close()


def test_a_retired_row_below_target_is_no_finding_and_not_citable(
    app_client,  # noqa: F811
) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    _technique, capability = _seed_attack_and_zt(c, bearer, cid)
    _keep_retired_row(cid)

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
    # The scored, catalog row still flows: what must appear, first.
    assert capability in controls
    assert capability in finding_ids
    # The retired row does not.
    assert RETIRED not in controls
    assert RETIRED not in finding_ids
