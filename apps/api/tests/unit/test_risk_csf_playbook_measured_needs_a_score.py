"""#474 D': `measured` requires a recorded value other than a target.

The advisor's ruling (#736 6090360421): a Playbook whose only recorded values
are target levels -- targets set, nothing scored -- has measured nothing, so
it must not read `measured`. Since R10 (#736 6102665946), `measured` needs one
tier row that is both scored and targeted, so a score and a target on two
different rows read `playbook_no_scores`; which rows raise findings is
pinned in `test_risk_csf_scored_and_targeted_row.py`.

Every row is written the way the product writes it: scores through the real
CSF Run-AI (a registered provider response), targets through the
consultant's target-only PATCH. The expected state is written from each
scenario and read back through `/register/latest`.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.csf.catalog import SUBCATEGORIES
from tests._ai_runs import csf_run_ai, csf_scores_by_batch
from tests.unit.test_risk_csf_playbook_citable import _generate
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _seed_attack_and_zt,
    app_client,
)

pytestmark = pytest.mark.unit

_GV = [s.code for s in SUBCATEGORIES if s.code.startswith("GV.")]
SCORED, TARGETED = _GV[0], _GV[1]


def _playbook(
    c, provider, bearer: str, cid: str, *, score: bool, target: str | None
) -> dict[str, Any]:
    """A CSF Playbook (`high` tier). `score`: the Run-AI scores SCORED at
    governance 2, policy 1. `target`: the code given target level 4 by a
    target-only PATCH, or None. Approved, then the register is generated."""
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    assert svc.status_code in (200, 201), svc.text
    sid = svc.json()["id"]
    a = c.post(f"/csf/services/{sid}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    seeded = c.post(f"/csf/services/{sid}/profiles/seed", headers=h, json={"tiers": ["high"]})
    assert seeded.status_code in (200, 201), seeded.text

    if score:
        from app.ai.llm import LLMClient
        from app.routes.csf import _llm_dep as csf_llm_dep

        c.app.dependency_overrides[csf_llm_dep] = lambda: LLMClient(provider)
        provider.register(
            "csf_score",
            csf_scores_by_batch(
                [{"tier": "high", "subcategory_code": SCORED, "governance": 2, "policy": 1}],
                tiers=["high"],
                codes=[s.code for s in SUBCATEGORIES],
            ),
        )
        run = csf_run_ai(c, sid, h, serves="offline")
        assert run["suggestions_received"] == 2 and run["suggestions_applied"] == 2, run

    rows = {
        r["subcategory_code"]: r
        for r in c.get(f"/csf/services/{sid}/profile/high", headers=h).json()["rows"]
    }
    if target is not None:
        r = c.patch(
            f"/csf/dimension-scores/{rows[target]['id']}", headers=h, json={"target_level": 4}
        )
        assert r.status_code == 200, r.text
    ap = c.post(f"/csf/assessments/{a.json()['id']}/approve", headers=h)
    assert ap.status_code == 200, ap.text
    return _generate(c, provider, bearer, cid)


def _csf_source(c, bearer: str, cid: str) -> str:
    latest = c.get(
        f"/risk/clients/{cid}/register/latest", headers={"Authorization": f"Bearer {bearer}"}
    )
    assert latest.status_code == 200, latest.text
    (csf,) = [t for t in latest.json()["targets"] if t["kind"] == "csf"]
    assert csf["target"] is None, csf
    return csf["source"]


@pytest.mark.parametrize(
    ("score", "target", "expected"),
    [
        # Targets set, nothing scored: only target levels are recorded.
        (False, TARGETED, "playbook_no_scores"),
        # Scored, no target anywhere.
        (True, None, "playbook_no_targets"),
        # Scored, and that row has a target.
        (True, SCORED, "playbook"),
        # One row scored, a DIFFERENT row given a target: no row is both
        # scored and targeted, so nothing was measured against a target (R10).
        (True, TARGETED, "playbook_no_scores"),
    ],
    ids=["targets_only", "scores_no_targets", "scores_and_target", "score_and_target_on_two_rows"],
)
def test_the_recorded_csf_state(
    app_client, score: bool, target: str | None, expected: str  # noqa: F811
) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    _playbook(c, provider, bearer, cid, score=score, target=target)
    assert _csf_source(c, bearer, cid) == expected
