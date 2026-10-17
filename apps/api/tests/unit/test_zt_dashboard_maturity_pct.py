"""#1183, the Zero Trust half (tier-1; Gene's decision, #736 6204217058,
narrowed by the advisor in 6225266160): the client dashboard's maturity
percentage is (avg - 1) / (top - 1), one decimal, rounded DOWN. CISA stages run
1..4, DoD stages 1..3. The CSF half is #1382, on the same shared helper.

Before, it was avg / top: a client at stage 1 everywhere read 25% (CISA).

Through the client dashboard route. Every expected value is worked out here
from the stages typed into the world, never computed by the module under test.
The first rows below are whole stages, so the exact and the two-decimal
displayed average are the same number; the last two tests are not (advisor,
#736 6228351462 item 5: floor the EXACT average):
- CISA, stage 1 everywhere: (1 - 1) / 3 = 0.0%;
- CISA, stage 3 everywhere: (3 - 1) / 3 = 66.66..., shown 66.6 (rounding to
  nearest would give 66.7);
- CISA, target stage 4: (4 - 1) / 3 = 100.0%;
- DoD, stage 1 everywhere: (1 - 1) / 2 = 0.0% (it was 33.3);
- DoD, target stage 2: (2 - 1) / 2 = 50.0% (it was 66.7). Stage 3 is not used:
  it is refused on the capabilities with no Advanced level (#839).
"""

from __future__ import annotations

import pytest

from tests.unit.test_zt_dashboard import _register, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def _world(c, *, kind: str, stage: int, target_stage: int, stage_by_code=None) -> dict:
    """A released ZT assessment with every capability at `stage` (or at
    `stage_by_code(capability_code)` when given) and every per-capability
    target at `target_stage`, read through the client dashboard."""
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    client_id = client["user"]["client_id"]
    h = {"Authorization": f"Bearer {admin['tokens']['access_token']}"}
    svc_id = c.post(
        "/zt/services", headers=h, json={"kind": kind, "title": "Atlas - Zero Trust"}
    ).json()["id"]
    assessment = c.post(f"/zt/services/{svc_id}/assessments", headers=h).json()
    for ans in assessment["answers"]:
        r = c.patch(
            f"/zt/answers/{ans['id']}",
            headers=h,
            json={
                "maturity_stage": stage_by_code(ans["capability_code"]) if stage_by_code else stage,
                "target_stage": target_stage,
            },
        )
        assert r.status_code == 200, r.text
    assert c.post(f"/zt/assessments/{assessment['id']}/approve", headers=h).status_code == 200
    fin = c.post(f"/zt/services/{svc_id}/deliverables/finalize", headers=h)
    assert fin.status_code == 201, fin.text
    rel = c.post(f"/zt/deliverables/{fin.json()['id']}/release", headers=h)
    assert rel.status_code == 200, rel.text
    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_cisa_the_lowest_stage_everywhere_is_zero_percent(app_client) -> None:  # noqa: F811
    body = _world(app_client, kind="zero_trust_cisa", stage=1, target_stage=4)
    assert body["framework"] == "cisa_ztmm_2_0"  # positive first
    assert body["current_pct"] == 0.0, body["current_pct"]
    assert body["target_pct"] == 100.0, body["target_pct"]
    assert body["pillars"], "no pillars to check"
    for p in body["pillars"]:
        assert (p["current_pct"], p["target_pct"], p["gap_pct"]) == (0.0, 100.0, 100.0), p
    assert body["largest_gap_pct"] == 100.0, body["largest_gap_pct"]


def test_cisa_a_percentage_is_floored_not_rounded(app_client) -> None:  # noqa: F811
    body = _world(app_client, kind="zero_trust_cisa", stage=3, target_stage=4)
    assert body["current_label"] == "Advanced", body["current_label"]  # positive first
    assert body["current_pct"] == 66.6, body["current_pct"]
    assert body["pillars"], "no pillars to check"
    for p in body["pillars"]:
        assert (p["current_pct"], p["gap_pct"]) == (66.6, 33.4), p
    assert body["largest_gap_pct"] == 33.4, body["largest_gap_pct"]


def test_dod_the_middle_stage_is_half_way(app_client) -> None:  # noqa: F811
    body = _world(app_client, kind="zero_trust_dod", stage=1, target_stage=2)
    assert body["framework"] == "dod_ztra", body["framework"]  # positive first
    assert body["current_pct"] == 0.0, body["current_pct"]
    assert body["target_pct"] == 50.0, body["target_pct"]
    assert body["pillars"], "no pillars to check"
    for p in body["pillars"]:
        assert (p["current_pct"], p["target_pct"], p["gap_pct"]) == (0.0, 50.0, 50.0), p


def test_a_pillar_percentage_is_taken_from_its_exact_average(app_client) -> None:  # noqa: F811
    # Two of the Identity pillar's seven capabilities are at stage 3, the other
    # five at 2: its average is 16/7 = 2.2857..., shown as 2.29. Exactly,
    # (9/7) / 3 = 42.857...%, floored 42.8; flooring the shown 2.29 would give
    # 43.0, a figure higher than the truth. Target stage 4 everywhere is 100%,
    # so the pillar's gap is 57.2.
    three = {"CISA.ID.01", "CISA.ID.02"}
    body = _world(
        app_client,
        kind="zero_trust_cisa",
        stage=0,
        target_stage=4,
        stage_by_code=lambda code: 3 if code in three else 2,
    )
    identity = body["pillars"][0]
    assert (identity["code"], identity["capability_count"]) == ("ID", 7), identity  # positive first
    assert identity["current_pct"] == 42.8, identity["current_pct"]
    assert identity["gap_pct"] == 57.2, identity["gap_pct"]


def test_the_overall_percentage_is_taken_from_the_exact_average(app_client) -> None:  # noqa: F811
    # The same two capabilities at 3 and the other 35 at 2: the average is
    # 76/37 = 2.0540..., shown 2.05. Exactly, (39/37) / 3 = 35.13...%, floored
    # 35.1; the shown 2.05 would give 35.0.
    three = {"CISA.ID.01", "CISA.ID.02"}
    body = _world(
        app_client,
        kind="zero_trust_cisa",
        stage=0,
        target_stage=4,
        stage_by_code=lambda code: 3 if code in three else 2,
    )
    # The 76/37 above depends on CISA having 37 capabilities.
    assert sum(p["capability_count"] for p in body["pillars"]) == 37, body["pillars"]
    assert body["current_pct"] == 35.1, body["current_pct"]
