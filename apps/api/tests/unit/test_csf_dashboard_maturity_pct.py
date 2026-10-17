"""#1183, the CSF half (tier-1; Gene's decision, #736 6204217058, narrowed by
the advisor in 6225264951): the client dashboard's maturity percentage is
(avg - 1) / (top - 1), one decimal, rounded DOWN. CSF tiers run 1..4.

Before, it was avg / 4: a client at tier 1 everywhere read 25%, and the
default target tier 3 read 75%.

Through the client dashboard route. Every expected value is worked out here
from the tiers typed into the world, never computed by the module under test:
- tier 1 everywhere: (1 - 1) / 3 = 0.0%;
- target tier 3: (3 - 1) / 3 = 66.66..., shown 66.6 (rounding to nearest
  would give 66.7);
- 71 subcategories at tier 3 and 35 at tier 2: the average is 283/106,
  2.6698..., shown by the API as 2.67; (2.67 - 1) / 3 = 55.66..., shown 55.6.
"""

from __future__ import annotations

import pytest

from tests.unit.test_csf_dashboard import _register, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def _world(c, tiers_by_index, tier_by_code=None) -> tuple[str, dict]:
    """A released CSF assessment whose i-th subcategory is scored
    `tiers_by_index(i)` (or `tier_by_code(subcategory_code)` when given), read through
    the client dashboard."""
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    client_id = client["user"]["client_id"]
    h = {"Authorization": f"Bearer {admin['tokens']['access_token']}"}
    svc_id = c.post(
        "/csf/services", headers=h, json={"kind": "nist_csf", "title": "Atlas - CSF"}
    ).json()["id"]
    assessment = c.post(f"/csf/services/{svc_id}/assessments", headers=h).json()
    for i, ans in enumerate(assessment["answers"]):
        r = c.patch(
            f"/csf/answers/{ans['id']}",
            headers=h,
            json={
                "maturity_tier": (
                    tier_by_code(ans["subcategory_code"]) if tier_by_code else tiers_by_index(i)
                )
            },
        )
        assert r.status_code == 200, r.text
    assert c.post(f"/csf/assessments/{assessment['id']}/approve", headers=h).status_code == 200
    fin = c.post(f"/csf/services/{svc_id}/deliverables/finalize", headers=h)
    assert fin.status_code == 201, fin.text
    rel = c.post(f"/csf/deliverables/{fin.json()['id']}/release", headers=h)
    assert rel.status_code == 200, rel.text
    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/csf/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    )
    assert r.status_code == 200, r.text
    return client_id, r.json()


def test_the_lowest_tier_everywhere_is_zero_percent(app_client) -> None:  # noqa: F811
    _cid, body = _world(app_client, lambda _i: 1)
    assert body["current_tier"] == 1.0, body["current_tier"]  # positive first
    assert body["current_pct"] == 0.0, body["current_pct"]
    assert body["target_tier"] == 3
    assert body["target_pct"] == 66.6, body["target_pct"]
    for fn in body["functions"]:
        assert (fn["current_pct"], fn["target_pct"], fn["gap_pct"]) == (0.0, 66.6, 66.6), fn
    assert body["largest_gap_pct"] == 66.6, body["largest_gap_pct"]


def test_a_fractional_average_is_floored_to_one_decimal(app_client) -> None:  # noqa: F811
    _cid, body = _world(app_client, lambda i: 3 if i < 71 else 2)
    assert body["current_tier"] == 2.67, body["current_tier"]
    assert body["current_pct"] == 55.6, body["current_pct"]


def test_the_percentage_is_taken_from_the_exact_average_not_the_displayed_one(
    app_client,  # noqa: F811
) -> None:
    # 3 subcategories at tier 3, the other 103 at tier 2: the average is
    # 215/106 = 2.0283..., shown as 2.03. Exactly, (109/106) / 3 = 34.27...%,
    # floored 34.2. Flooring the shown 2.03 would give 34.3, a figure higher
    # than the truth (advisor, #736 6228351462 item 5).
    _cid, body = _world(app_client, lambda i: 3 if i < 3 else 2)
    assert body["current_tier"] == 2.03, body["current_tier"]  # positive first
    assert body["current_pct"] == 34.2, body["current_pct"]


def test_a_function_percentage_is_taken_from_its_exact_average(app_client) -> None:  # noqa: F811
    # Three Govern subcategories are scored 3; the rest are 2. Govern has
    # 31 subcategories, so its average is 65/31 = 2.0967..., shown 2.10.
    # Exactly, (34/31) / 3 = 36.55...%, floored 36.5; flooring the shown 2.10
    # would give 36.6. Gap to the target 66.6: 30.1.
    three = {"GV.OC-01", "GV.OC-02", "GV.OC-03"}
    _cid, body = _world(app_client, None, lambda code: 3 if code in three else 2)
    govern = body["functions"][0]
    assert (govern["code"], govern["subcategory_count"]) == ("GV", 31), govern  # positive first
    assert govern["current_tier"] == 2.1, govern
    assert govern["current_pct"] == 36.5, govern["current_pct"]
    assert govern["gap_pct"] == 30.1, govern["gap_pct"]
