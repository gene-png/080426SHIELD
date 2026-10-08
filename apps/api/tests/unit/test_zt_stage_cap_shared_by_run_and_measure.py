"""A run and the consistency measure refuse the same DoD maturity stages (#839
F1, the #867 hand-off).

#867 made `routes/zt.py::_validated_stage` the one statement of what a
zt_score stage must be to be applied, called by `_zt_run_work` and by
`scripts/measure_ai_consistency.py`. #839 added a second rule on the apply
path: a maturity stage above the capability's own maximum is refused as
`stage_above_capability_max`. Merging second, #839 owed passing that maximum
into the shared validator so the measure counts as refused exactly what a run
refuses. These tests drive both SURFACES, the Run-AI route and `measure_zt`,
with the same response.

The capabilities are the ones `test_zt_dod_stage_cap_guard.py` uses, chosen
from the PDF's levels (1.1 has no Advanced activity, 1.2 has one), never from
the code under test. The reason string is the one the PATCH routes give,
written out, not imported.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from scripts.measure_ai_consistency import ZtScope, compare_pair, measure_zt

from app.ai.llm import LLMClient, LLMResponse
from app.routes.zt import _validated_stage
from tests._ai_runs import zt_run_ai
from tests.unit.test_measure_ai_consistency import world  # noqa: F401  (fixture)
from tests.unit.test_zt_run_ai import _admin_service, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

NO_ADVANCED = "DOD.USR.01"  # 1.1 User Inventory: Target activities only
HAS_ADVANCED = "DOD.USR.02"  # 1.2 Conditional User Access
DOD_LADDER = 3  # Basic, Target, Advanced
REASON = "stage_above_capability_max"

# Current 3 on both: refused on 1.1, applied on 1.2. Target 2 on 1.1 is within
# its maximum and lands, so the row is not refused as a whole.
RESPONSE = (
    '{"capabilities": ['
    '{"code": "' + NO_ADVANCED + '", "current": 3, "target": 2},'
    '{"code": "' + HAS_ADVANCED + '", "current": 3}'
    "]}"
)


@pytest.mark.parametrize(
    ("raw", "capability_max", "expected"),
    [
        (3, 2, (None, REASON)),
        (2, 2, (2, None)),
        ("2", 2, (2, None)),
        (3, 3, (3, None)),
        (3, None, (3, None)),
        # The ladder and wholeness are judged first: their reasons win.
        (4, 2, (None, "out_of_range")),
        (2.5, 2, (None, "unparseable")),
        ("x", 2, (None, "unparseable")),
    ],
)
def test_the_validator_checks_the_capability_maximum_last(raw, capability_max, expected) -> None:
    assert _validated_stage(raw, DOD_LADDER, capability_max) == expected


def _dod_assessment(c: TestClient) -> None:
    admin = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    bearer = admin.json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Acme"},
    ).json()["id"]
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_dod", "title": "T"})
    assert svc.status_code in (200, 201), svc.text
    svc_id = svc.json()["id"]
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    codes = {r["capability_code"] for r in a.json()["answers"]}
    assert {NO_ADVANCED, HAS_ADVANCED} <= codes


def test_measure_zt_refuses_what_the_run_refuses(world) -> None:  # noqa: F811
    c, TestSession, provider = world
    _dod_assessment(c)
    provider.register_static("zt_score", LLMResponse(RESPONSE))

    with TestSession() as db:
        report = measure_zt(db, LLMClient(provider), framework="dod", runs=2)
        db.commit()
    current = report["pairs"][0]["fields"]["current"]
    # The positive state first: 1.2's 3 is an answer, and both runs agree on it.
    assert (current["compared"], current["equal"]) == (2, 1), current
    # 1.1's 3 is refused in both runs: compared, no agreement, both absent.
    assert current["both_absent"] == 1, current
    target = report["pairs"][0]["fields"]["target"]
    assert (target["compared"], target["equal"]) == (2, 1), target


def test_the_run_refuses_what_the_measure_refuses(app_client) -> None:  # noqa: F811
    """The same RESPONSE through the Run-AI route: 1.1's current is dropped
    for the same reason, 1.2's current and 1.1's target land."""
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_dod")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    provider.register_static("zt_score", LLMResponse(RESPONSE))
    body = zt_run_ai(c, svc_id, h)
    by_code = {r["capability_code"]: r for r in body["answers"]}
    assert by_code[HAS_ADVANCED]["maturity_stage"] == 3
    assert by_code[NO_ADVANCED]["target_stage"] == 2
    assert by_code[NO_ADVANCED]["maturity_stage"] is None
    assert [(d["key"], d["field"], d["reason"]) for d in body["dropped"]] == [
        (NO_ADVANCED, "current", REASON)
    ], body["dropped"]


def test_a_target_above_the_capability_maximum_is_not_refused_by_the_measure() -> None:
    """Scope 1 (6049667540): a target above the maximum is stored and
    disclosed (C1), never refused, so the measure compares it as an answer."""
    from app.zt.maturity import ZtFrameworkCode

    scope = ZtScope(
        max_stage=DOD_LADDER,
        codes=frozenset({NO_ADVANCED}),
        framework=ZtFrameworkCode.DOD_ZTRA,
    )
    a = {"capabilities": [{"code": NO_ADVANCED, "current": 2, "target": 3}]}
    r = compare_pair("zt_score", a, a, context=scope)
    assert (r["fields"]["target"]["compared"], r["fields"]["target"]["equal"]) == (1, 1)
    assert r["fields"]["target"]["both_absent"] == 0
    assert (r["fields"]["current"]["compared"], r["fields"]["current"]["equal"]) == (1, 1)
