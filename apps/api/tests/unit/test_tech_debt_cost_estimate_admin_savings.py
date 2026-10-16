"""TD-5 (for #1060), #1299 folded in, no admin exemption (#736
issuecomment-6225076633): the consultant's two savings figures count the
AI-estimated costs they include, by the same rule as every client and
deliverable savings figure, so each can say so (copy E6).

- The consolidation-plan card counts over the STORED dispositions.
- The savings what-if counts over the PROPOSED dispositions: an estimated row
  the what-if cuts is counted, one it keeps is not.

The seed (`test_tech_debt_dashboard`): BeyondTrust (PAM) is cut, Splunk ES
(SIEM) is kept; both have a cost.
"""

from __future__ import annotations

import pytest

from tests.unit.test_tech_debt_cost_estimate_surfaces import _mark_estimated
from tests.unit.test_tech_debt_dashboard import (  # noqa: F401  (fixture)
    _register,
    _seed_release,
    app_client,
)

pytestmark = pytest.mark.unit


def _admin(app_client):  # noqa: F811
    c, provider = app_client
    admin = _register(c, "admin@example.com")
    h = {"Authorization": f"Bearer {admin['tokens']['access_token']}"}
    svc_id = _seed_release(c, provider, admin["tokens"]["access_token"], release=False)
    lst = c.get(f"/tech-debt/services/{svc_id}/capability-lists/latest", headers=h)
    assert lst.status_code == 200, lst.text
    ids = {it["name"]: it["id"] for it in lst.json()["items"]}
    return c, h, svc_id, lst.json()["id"], ids


def _plan_count(c, h, svc_id) -> int:
    r = c.get(f"/tech-debt/services/{svc_id}/consolidation-plan", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["savings_ai_estimate_count"]


def _preview_count(c, h, list_id, dispositions: dict) -> int:
    r = c.post(
        f"/tech-debt/capability-lists/{list_id}/savings-preview",
        headers=h,
        json={"dispositions": dispositions},
    )
    assert r.status_code == 200, r.text
    return r.json()["savings_ai_estimate_count"]


def test_the_plan_card_counts_the_estimated_cut_rows(app_client) -> None:  # noqa: F811
    c, h, svc_id, _list_id, _ids = _admin(app_client)
    # POSITIVE CONTROL: nothing estimated, nothing counted.
    assert _plan_count(c, h, svc_id) == 0
    _mark_estimated("Splunk ES")  # kept: in no savings figure
    assert _plan_count(c, h, svc_id) == 0
    _mark_estimated("BeyondTrust")  # cut
    assert _plan_count(c, h, svc_id) == 1


def test_the_what_if_counts_under_the_proposed_dispositions(app_client) -> None:  # noqa: F811
    c, h, _svc_id, list_id, ids = _admin(app_client)
    _mark_estimated("Splunk ES", "BeyondTrust")
    # As stored: BeyondTrust (cut) is counted, Splunk ES (kept) is not.
    assert _preview_count(c, h, list_id, {}) == 1
    # Proposing to cut Splunk ES adds it; proposing to keep BeyondTrust drops it.
    assert _preview_count(c, h, list_id, {ids["Splunk ES"]: "cut"}) == 2
    assert _preview_count(c, h, list_id, {ids["BeyondTrust"]: "keep"}) == 0
    # Unticking (None) is a choice too: an undecided row is in no savings.
    assert _preview_count(c, h, list_id, {ids["BeyondTrust"]: None}) == 0
