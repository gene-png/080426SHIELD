"""No write path stores a DoD stage above the capability's own maximum (#839, F1).

The advisor's ruling (#736 comment 6048561596, option (a)): the cap at the
highest level a capability defines means the store must not hold a stage the
capability cannot reach. A DoD capability with no Advanced activity tops out at
Target (2), so a maturity stage of 3 is refused:

* the consultant's PATCH and the client's self-assessment PATCH answer a typed
  422 in the approved words, and store nothing;
* a Run-AI suggestion of it is dropped as refused, its reason recorded.

The expected sentence is copied from that comment, filled in for 1.1, and the
capabilities are chosen from the extraction's levels (1.1 has no Advanced
activity, 1.2 has one: `test_zt_dod_target_caps.py` pins both groups), never
from the code under test.
"""

from __future__ import annotations

import pytest

from app.ai.llm import LLMResponse
from tests._ai_runs import zt_run_ai
from tests.unit.test_zt_run_ai import _admin_service, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

NO_ADVANCED = "DOD.USR.01"  # 1.1 User Inventory: Target activities only
HAS_ADVANCED = "DOD.USR.02"  # 1.2 Conditional User Access
REFUSED = {
    "reason": "stage_above_capability_max",
    "message": "1.1 User Inventory has no DoD Advanced activities, so it cannot be scored 3.",
}


def _assert_refused(body: dict) -> None:
    err = body["error"]  # the D-016 envelope
    assert {k: err[k] for k in REFUSED} == REFUSED, body


def _draft(c, kind: str = "zero_trust_dod") -> tuple[dict, str, dict[str, dict]]:
    h, svc_id, _ = _admin_service(c, kind)
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    return h, svc_id, {r["capability_code"]: r for r in a.json()["answers"]}


def _stored(c, h, svc_id: str, code: str) -> dict:
    latest = c.get(f"/zt/services/{svc_id}/assessments/latest", headers=h)
    assert latest.status_code == 200, latest.text
    return next(r for r in latest.json()["answers"] if r["capability_code"] == code)


def test_the_consultant_patch_refuses_a_stage_above_the_capability_max(
    app_client,  # noqa: F811
) -> None:
    c, _ = app_client
    h, svc_id, rows = _draft(c)
    r = c.patch(f"/zt/answers/{rows[NO_ADVANCED]['id']}", headers=h, json={"maturity_stage": 3})
    assert r.status_code == 422, r.text
    _assert_refused(r.json())
    assert _stored(c, h, svc_id, NO_ADVANCED)["maturity_stage"] is None


def test_the_client_self_assessment_patch_refuses_it_too(app_client) -> None:  # noqa: F811
    c, _ = app_client
    h, svc_id, rows = _draft(c)
    r = c.patch(
        f"/zt/self-assessment/answers/{rows[NO_ADVANCED]['id']}",
        headers=h,
        json={"maturity_stage": 3},
    )
    assert r.status_code == 422, r.text
    _assert_refused(r.json())
    assert _stored(c, h, svc_id, NO_ADVANCED)["maturity_stage"] is None


def test_the_capabilitys_own_maximum_and_other_capabilities_are_accepted(
    app_client,  # noqa: F811
) -> None:
    c, _ = app_client
    h, svc_id, rows = _draft(c)
    # The positive states first: the guard must not refuse what is reachable.
    ok = c.patch(f"/zt/answers/{rows[NO_ADVANCED]['id']}", headers=h, json={"maturity_stage": 2})
    assert ok.status_code == 200, ok.text
    three = c.patch(
        f"/zt/answers/{rows[HAS_ADVANCED]['id']}", headers=h, json={"maturity_stage": 3}
    )
    assert three.status_code == 200, three.text
    assert _stored(c, h, svc_id, NO_ADVANCED)["maturity_stage"] == 2
    assert _stored(c, h, svc_id, HAS_ADVANCED)["maturity_stage"] == 3


def test_cisa_is_untouched(app_client) -> None:  # noqa: F811
    c, _ = app_client
    h, svc_id, rows = _draft(c, "zero_trust_cisa")
    code = next(iter(rows))
    r = c.patch(f"/zt/answers/{rows[code]['id']}", headers=h, json={"maturity_stage": 4})
    assert r.status_code == 200, r.text


def test_run_ai_drops_the_suggestion_as_refused_and_applies_its_siblings(
    app_client,  # noqa: F811
) -> None:
    c, provider = app_client
    h, svc_id, _ = _draft(c)
    provider.register_static(
        "zt_score",
        LLMResponse(
            '{"capabilities": ['
            '{"code": "' + NO_ADVANCED + '", "current": 3, "target": 2},'
            '{"code": "' + HAS_ADVANCED + '", "current": 3}'
            "]}"
        ),
    )
    body = zt_run_ai(c, svc_id, h)
    by_code = {r["capability_code"]: r for r in body["answers"]}
    # The positive state first: the reachable values landed.
    assert by_code[HAS_ADVANCED]["maturity_stage"] == 3
    assert by_code[NO_ADVANCED]["target_stage"] == 2
    assert by_code[NO_ADVANCED]["maturity_stage"] is None
    drops = [d for d in body["dropped"] if d["key"] == NO_ADVANCED]
    assert drops == [
        {
            "reason": "stage_above_capability_max",
            "key": NO_ADVANCED,
            "field": "current",
            "value": "3",
            "values": 1,
        }
    ], body["dropped"]
    assert body["suggestions_applied"] == 2, body
