"""#804: the Tech Debt savings what-if.

An admin ticks tools and sees the estimated annual savings recalculate. The
figure comes from the SERVER, through the one savings function every other
Tech Debt surface calls (`tech_debt/savings.py`), so the what-if cannot
disagree with the deliverable the same ticks would produce. It is a what-if:
the preview writes nothing, and no AI is called.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.llm_call import LLMCall
from tests.unit.test_tech_debt_routes import (  # noqa: F401  (fixture)
    _latest_list,
    _register,
    _seed_three_item_list,
    app_client,
)

pytestmark = pytest.mark.unit

# The seed's costs: Wiz 350,000, Lacework 120,000, Splunk 480,000.
WIZ, LACEWORK, SPLUNK = 350_000.0, 120_000.0, 480_000.0


def _world(app_client):  # noqa: F811
    c, sessions, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    lst = _latest_list(c, bearer, svc_id)
    by_name = {i["name"]: i["id"] for i in lst["items"]}
    return c, sessions, h, bearer, svc_id, lst["id"], by_name


def _preview(c, h, list_id, dispositions):
    return c.post(
        f"/tech-debt/capability-lists/{list_id}/savings-preview",
        headers=h,
        json={"dispositions": dispositions},
    )


def test_ticking_a_tool_cut_adds_its_cost_and_writes_nothing(app_client) -> None:  # noqa: F811
    c, sessions, h, bearer, svc_id, list_id, ids = _world(app_client)

    r = _preview(c, h, list_id, {ids["Splunk"]: "cut"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estimated_annual_savings"] == SPLUNK
    assert body["savings_cost_known"] is True
    assert body["cut_count"] == 1

    r = _preview(c, h, list_id, {ids["Splunk"]: "cut", ids["Wiz"]: "cut"})
    assert r.json()["estimated_annual_savings"] == SPLUNK + WIZ

    # A what-if: the real plan is untouched.
    assert all(i["disposition"] is None for i in _latest_list(c, bearer, svc_id)["items"])
    # And nothing was sent to an AI.
    with sessions() as s:
        assert s.execute(select(func.count()).select_from(LLMCall)).scalar_one() == 1  # the extract


def test_cut_covered_by_another_tool_counts_its_full_cost_and_keep_counts_nothing(
    app_client,  # noqa: F811
) -> None:
    """The advisor's ruling on #736 (2026-10-02): "Cut, covered by another
    tool" (stored `consolidate`) counts the tool's FULL annual cost, as Cut
    does. Keep counts nothing."""
    c, _s, h, _b, _svc, list_id, ids = _world(app_client)
    body = _preview(
        c, h, list_id, {ids["Wiz"]: "consolidate", ids["Splunk"]: "cut", ids["Lacework"]: "keep"}
    ).json()
    assert body["estimated_annual_savings"] == WIZ + SPLUNK
    assert (body["consolidate_count"], body["cut_count"], body["keep_count"]) == (1, 1, 1)


def test_an_untouched_row_keeps_its_stored_disposition(app_client) -> None:  # noqa: F811
    c, _s, h, _b, _svc, list_id, ids = _world(app_client)
    r = c.patch(f"/tech-debt/capability-items/{ids['Wiz']}", headers=h, json={"disposition": "cut"})
    assert r.status_code == 200, r.text

    # Only Splunk is ticked; Wiz is already cut on the real plan.
    assert _preview(c, h, list_id, {ids["Splunk"]: "cut"}).json()["estimated_annual_savings"] == (
        SPLUNK + WIZ
    )
    # And unticking Wiz in the what-if takes it out.
    assert _preview(c, h, list_id, {ids["Wiz"]: None}).json()["estimated_annual_savings"] == 0.0


def test_the_what_if_agrees_with_the_plan_and_the_deliverable(app_client) -> None:  # noqa: F811
    """The same ticks, three surfaces, one number."""
    c, _s, h, _b, svc_id, list_id, ids = _world(app_client)
    choice = {ids["Wiz"]: "keep", ids["Lacework"]: "consolidate", ids["Splunk"]: "cut"}
    preview = _preview(c, h, list_id, choice).json()
    for item_id, disp in choice.items():
        r = c.patch(f"/tech-debt/capability-items/{item_id}", headers=h, json={"disposition": disp})
        assert r.status_code == 200, r.text
    plan = c.get(f"/tech-debt/services/{svc_id}/consolidation-plan", headers=h).json()
    assert c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=h).status_code == 200
    fin = c.post(f"/tech-debt/services/{svc_id}/deliverables/finalize", headers=h)
    assert fin.status_code == 201, fin.text

    assert preview["estimated_annual_savings"] == plan["estimated_annual_savings"]
    assert preview["savings_cost_known"] == plan["savings_cost_known"]
    assert f"${preview['estimated_annual_savings']:,.0f}" in fin.json()["summary"]


def test_an_uncosted_cut_tool_makes_the_figure_a_lower_bound(app_client) -> None:  # noqa: F811
    c, _s, h, _b, _svc, list_id, ids = _world(app_client)
    r = c.patch(
        f"/tech-debt/capability-items/{ids['Lacework']}", headers=h, json={"annual_cost_usd": None}
    )
    assert r.status_code == 200, r.text

    body = _preview(c, h, list_id, {ids["Lacework"]: "cut", ids["Splunk"]: "cut"}).json()
    assert body["estimated_annual_savings"] == SPLUNK
    assert body["savings_cost_known"] is False


@pytest.mark.parametrize(
    ("dispositions", "reason"),
    [
        ({"00000000-0000-0000-0000-000000000000": "cut"}, "savings_preview_unknown_item"),
        ("not-a-map", "savings_preview_bad_request"),
        (None, "savings_preview_bad_request"),
    ],
)
def test_a_bad_request_is_a_typed_422(app_client, dispositions, reason) -> None:  # noqa: F811
    c, _s, h, _b, _svc, list_id, _ids = _world(app_client)
    r = _preview(c, h, list_id, dispositions)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["reason"] == reason


def test_an_unknown_disposition_is_a_typed_422(app_client) -> None:  # noqa: F811
    c, _s, h, _b, _svc, list_id, ids = _world(app_client)
    r = _preview(c, h, list_id, {ids["Wiz"]: "retire"})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["reason"] == "savings_preview_unknown_disposition"


def test_another_tenants_list_is_not_found(app_client) -> None:  # noqa: F811
    c, _s, h, bearer, _svc, list_id, _ids = _world(app_client)
    made = c.post("/admin/clients", headers=h, json={"legal_name": "B"})
    assert made.status_code in (200, 201), made.text
    r = _preview(c, {**h, "X-Client-Id": made.json()["id"]}, list_id, {})
    assert r.status_code == 404, r.text


def test_a_client_role_is_refused_as_on_the_disposition_routes(app_client) -> None:  # noqa: F811
    """The same admin-only guard the disposition PATCH and bulk routes carry."""
    c, _s, h, _b, _svc, list_id, ids = _world(app_client)
    client = _register(c, "client@example.com")
    r = _preview(
        c,
        {"Authorization": f"Bearer {client['tokens']['access_token']}"},
        list_id,
        {ids["Splunk"]: "cut"},
    )
    assert r.status_code == 403, r.text


def test_the_undecided_refusal_names_the_dispositions_by_their_labels(
    app_client,  # noqa: F811
) -> None:
    """#810 review: the approve refusal still said "keep, consolidate or cut"
    after the rename."""
    c, _s, h, _b, _svc, list_id, _ids = _world(app_client)
    r = c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=h)
    assert r.status_code == 409, r.text
    message = r.json()["error"]["message"]
    assert "Give every row a decision (Keep, Cut, or Cut, covered by another tool)" in message
    assert "consolidate" not in message.lower()
