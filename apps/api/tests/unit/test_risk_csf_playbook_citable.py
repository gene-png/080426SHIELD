"""#474 D': which CSF codes the Risk Register may cite, by how a row was written.

The advisor's ruling (#736 6087786886, items 1 and 2): a CSF code is citable
when an in-scope Playbook row has a recorded score (`csf/retired.py`
`has_recorded_score`). The CSF Run-AI deliberately writes no `answer_source`,
and a target-only PATCH writes none either, so a rule keyed on `answer_source`
left every AI-scored and target-only row uncitable.

Every row here is written the way the product writes it -- through the real
CSF Run-AI (fixture mode, a registered provider response) or through the
consultant's PATCH -- and every expected set is written from the scenario,
never from the predicate.

The world: `_seed_attack_and_zt` (the gate) plus one CSF assessment whose
`high` Playbook has
- AI_SCORED: scored by the Run-AI, then given a target by a target-only PATCH;
- AI_ZEROS: "scored" by the Run-AI at 0 on every dimension, with no notes,
  evidence or target, so it is indistinguishable from the seeded row;
- TARGET_ONLY: never scored, given a target by a target-only PATCH.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.ai.llm import LLMResponse
from app.csf.catalog import SUBCATEGORIES
from tests._ai_runs import csf_run_ai, csf_scores_by_batch
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _seed_attack_and_zt,
    app_client,
)

pytestmark = pytest.mark.unit

_GV = [s.code for s in SUBCATEGORIES if s.code.startswith("GV.")]
AI_SCORED, AI_ZEROS, TARGET_ONLY = _GV[0], _GV[1], _GV[2]


def _world(c, provider, bearer: str, cid: str) -> None:
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    assert svc.status_code in (200, 201), svc.text
    sid = svc.json()["id"]
    a = c.post(f"/csf/services/{sid}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    seeded = c.post(f"/csf/services/{sid}/profiles/seed", headers=h, json={"tiers": ["high"]})
    assert seeded.status_code in (200, 201), seeded.text

    zeros = dict.fromkeys(
        ("governance", "policy", "implementation", "monitoring", "improvement"), 0
    )
    scores = [
        {"tier": "high", "subcategory_code": AI_SCORED, "governance": 2, "policy": 1},
        {"tier": "high", "subcategory_code": AI_ZEROS, **zeros},
    ]
    # The Risk fixture overrides only Risk's LLM dependency; the CSF run gets
    # the same provider, so the registered response is what it reads.
    from app.ai.llm import LLMClient
    from app.routes.csf import _llm_dep as csf_llm_dep

    c.app.dependency_overrides[csf_llm_dep] = lambda: LLMClient(provider)
    provider.register(
        "csf_score",
        csf_scores_by_batch(scores, tiers=["high"], codes=[s.code for s in SUBCATEGORIES]),
    )
    run = csf_run_ai(c, sid, h, serves="offline")
    # Exactly the two entries landed: the registered response, not a canned one.
    assert run["suggestions_received"] == 7 and run["suggestions_applied"] == 7, run

    rows = {
        r["subcategory_code"]: r
        for r in c.get(f"/csf/services/{sid}/profile/high", headers=h).json()["rows"]
    }
    assert rows[AI_SCORED]["governance"] == 2, rows[AI_SCORED]
    for code in (AI_SCORED, TARGET_ONLY):
        r = c.patch(
            f"/csf/dimension-scores/{rows[code]['id']}", headers=h, json={"target_level": 4}
        )
        assert r.status_code == 200, r.text
    ap = c.post(f"/csf/assessments/{a.json()['id']}/approve", headers=h)
    assert ap.status_code == 200, ap.text


def _generate(c, provider, bearer: str, cid: str) -> dict[str, Any]:
    seen: list[dict[str, Any]] = []

    def capture(payload: dict[str, Any]) -> LLMResponse:
        seen.append(payload)
        return LLMResponse('{"entries": []}')

    provider.register("risk_synthesize", capture)
    r = c.post(
        f"/risk/clients/{cid}/register/generate",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 201, r.text
    assert seen, "no risk_synthesize payload was captured"
    return seen[0]


def _csf_ids(codes) -> set[str]:
    gv = set(_GV)
    return {c for c in codes if c in gv}


def test_ai_scored_and_target_only_rows_are_findings_and_citable(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    _world(c, provider, bearer, cid)
    payload = _generate(c, provider, bearer, cid)

    findings = _csf_ids(f["source_id"] for f in payload["findings"])
    citable = _csf_ids(payload["valid_controls"])
    # Both rows carry a target above their level, so both are findings...
    assert findings == {AI_SCORED, TARGET_ONLY}, findings
    # ...and each finding's own code is citable.
    assert citable == {AI_SCORED, TARGET_ONLY}, citable


def test_an_ai_row_of_zeros_with_nothing_else_is_neither_a_finding_nor_citable(
    app_client,  # noqa: F811
) -> None:
    """The edge the ruling asks to pin: an AI run that scores a row 0 on every
    dimension, with no notes, evidence or target, leaves it exactly as seeded.
    It carries no target, so it is no finding, and it is not citable."""
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    _world(c, provider, bearer, cid)
    payload = _generate(c, provider, bearer, cid)

    findings = _csf_ids(f["source_id"] for f in payload["findings"])
    citable = _csf_ids(payload["valid_controls"])
    assert AI_SCORED in citable and AI_SCORED in findings  # positive first
    assert AI_ZEROS not in findings, findings
    assert AI_ZEROS not in citable, citable


def test_a_playbook_scored_only_by_the_run_ai_counts_through_its_dimensions(
    app_client,  # noqa: F811
) -> None:
    """The Run-AI writes no `answer_source`, and here NO row has a target, so
    the only thing recorded on the row is the two dimension scores the model
    sent. `has_recorded_score` must count it through those: the code is
    citable, and the Playbook is `no_targets` (scores, no targets), not
    `no_scores`."""
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    assert svc.status_code in (200, 201), svc.text
    sid = svc.json()["id"]
    a = c.post(f"/csf/services/{sid}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    seeded = c.post(f"/csf/services/{sid}/profiles/seed", headers=h, json={"tiers": ["high"]})
    assert seeded.status_code in (200, 201), seeded.text

    from app.ai.llm import LLMClient
    from app.routes.csf import _llm_dep as csf_llm_dep

    c.app.dependency_overrides[csf_llm_dep] = lambda: LLMClient(provider)
    provider.register(
        "csf_score",
        csf_scores_by_batch(
            [{"tier": "high", "subcategory_code": AI_SCORED, "governance": 2, "policy": 1}],
            tiers=["high"],
            codes=[s.code for s in SUBCATEGORIES],
        ),
    )
    run = csf_run_ai(c, sid, h, serves="offline")
    # One entry, two values: both applied.
    assert run["suggestions_received"] == 2 and run["suggestions_applied"] == 2, run
    rows = {
        r["subcategory_code"]: r
        for r in c.get(f"/csf/services/{sid}/profile/high", headers=h).json()["rows"]
    }
    assert (rows[AI_SCORED]["governance"], rows[AI_SCORED]["policy"]) == (2, 1)
    assert all(r["target_level"] is None for r in rows.values()), "no row has a target"
    ap = c.post(f"/csf/assessments/{a.json()['id']}/approve", headers=h)
    assert ap.status_code == 200, ap.text

    payload = _generate(c, provider, bearer, cid)
    assert _csf_ids(payload["valid_controls"]) == {AI_SCORED}
    # No target anywhere, so nothing is below one: no CSF finding.
    assert _csf_ids(f["source_id"] for f in payload["findings"]) == set()

    latest = c.get(
        f"/risk/clients/{cid}/register/latest", headers={"Authorization": f"Bearer {bearer}"}
    )
    assert latest.status_code == 200, latest.text
    (csf,) = [t for t in latest.json()["targets"] if t["kind"] == "csf"]
    assert csf["source"] == "playbook_no_targets", csf
