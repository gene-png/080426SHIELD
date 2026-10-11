"""#804: every surface that shows Tech Debt savings shows the SAME number.

Five copies of the savings loop became one function
(`tech_debt/savings.py::estimated_savings`). This pins, per surface and
through that surface's own endpoint or exporter, the figure one fixed plan
produces, as a LITERAL: the deliverable's stored summary, the admin plan card,
the client dashboard's headline, its per-category redundancy savings, the home
value card and the what-if. Each surface is a separate test, so reverting any
one surface to a different derivation turns that surface's test red.

The plan, on the seed's three tools (Wiz 350,000 and Lacework 120,000 in
CNAPP; Splunk 480,000 in SIEM): Wiz KEEP, Lacework "Cut, covered by another
tool" (stored `consolidate`), Splunk CUT. Since the advisor's ruling on #736
both cuts count their full annual cost, and Keep counts nothing: before it,
the same plan made 480,000 and a CNAPP figure of 0.
"""

from __future__ import annotations

import io
import json

import pytest

from app.ai.llm import LLMResponse
from tests._ai_runs import tech_debt_extract
from tests.unit.test_tech_debt_dashboard import (  # noqa: F401  (fixture)
    _register,
    app_client,
)

pytestmark = pytest.mark.unit

ITEMS = [
    {"name": "Wiz", "category": "CNAPP", "annual_cost_usd": 350000, "source_row_index": 0},
    {"name": "Lacework", "category": "CNAPP", "annual_cost_usd": 120000, "source_row_index": 1},
    {"name": "Splunk", "category": "SIEM", "annual_cost_usd": 480000, "source_row_index": 2},
]
PLAN = {"Wiz": "keep", "Lacework": "consolidate", "Splunk": "cut"}
#: Lacework 120,000 + Splunk 480,000.
SAVINGS = 600_000.0
#: CNAPP holds Wiz (kept) and Lacework (cut, covered): the category's savings.
CNAPP_SAVINGS = 120_000.0


@pytest.fixture()
def released(app_client):  # noqa: F811
    c, provider = app_client
    provider.register(
        "extract.capabilities", lambda _p: LLMResponse(content=json.dumps({"items": ITEMS}))
    )
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    h = {"Authorization": f"Bearer {admin['tokens']['access_token']}"}
    svc = c.post("/tech-debt/services", headers=h, json={"title": "TD"}).json()["id"]
    csv = b"Tool,Cost\nWiz,1\nLacework,1\nSplunk,1\n"
    art = c.post(
        "/artifacts", headers=h, files={"file": ("inv.csv", io.BytesIO(csv), "text/csv")}
    ).json()["id"]
    lst = tech_debt_extract(c, svc, h, art)
    for it in lst["items"]:
        r = c.patch(
            f"/tech-debt/capability-items/{it['id']}",
            headers=h,
            json={"disposition": PLAN[it["name"]]},
        )
        assert r.status_code == 200, r.text
    plan_card = c.get(f"/tech-debt/services/{svc}/consolidation-plan", headers=h).json()
    preview = c.post(
        f"/tech-debt/capability-lists/{lst['id']}/savings-preview",
        headers=h,
        json={"dispositions": {}},
    ).json()
    assert c.post(f"/tech-debt/capability-lists/{lst['id']}/approve", headers=h).status_code == 200
    fin = c.post(f"/tech-debt/services/{svc}/deliverables/finalize", headers=h)
    assert fin.status_code == 201, fin.text
    rel = c.post(f"/tech-debt/deliverables/{fin.json()['id']}/release", headers=h)
    assert rel.status_code == 200, rel.text
    cid = client["user"]["client_id"]
    ch = {"Authorization": f"Bearer {client['tokens']['access_token']}", "X-Client-Id": cid}
    dash = c.get(f"/clients/{cid}/tech-debt/{svc}/dashboard", headers=ch).json()
    home = c.get(f"/clients/{cid}/value-summary", headers=ch).json()
    return {
        "summary": fin.json()["summary"],
        "plan": plan_card,
        "preview": preview,
        "dash": dash,
        "home": home,
    }


def test_the_deliverable_states_the_savings(released) -> None:
    assert "$600,000 estimated annual savings" in released["summary"], released["summary"]


def test_the_plan_card_states_the_savings(released) -> None:
    assert released["plan"]["estimated_annual_savings"] == SAVINGS
    assert released["plan"]["savings_cost_known"] is True


def test_the_what_if_states_the_savings_for_the_plan_as_it_stands(released) -> None:
    assert released["preview"]["estimated_annual_savings"] == SAVINGS
    assert released["preview"]["savings_cost_known"] is True


def test_the_client_dashboard_headline_states_the_savings(released) -> None:
    assert released["dash"]["identified_savings_usd"] == SAVINGS
    assert released["dash"]["savings_cost_known"] is True


def test_the_client_dashboard_states_each_categorys_savings(released) -> None:
    by_cat = {r["category"]: r["savings_usd"] for r in released["dash"]["redundancies"]}
    assert by_cat == {"CNAPP": CNAPP_SAVINGS}, by_cat


def test_the_home_value_card_states_the_savings(released) -> None:
    assert released["home"]["tech_debt_savings_usd"] == SAVINGS
    assert released["home"]["tech_debt_savings_cost_known"] is True
