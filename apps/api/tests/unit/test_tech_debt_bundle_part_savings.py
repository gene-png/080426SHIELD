"""A bundle part's stored cost is not a saving (for #929, advisor ruling on #736).

A split bundle's part (`parent_item_id` set) carries no cost of its own: the
bundle row holds the licence value. Since #927 a cost can no longer be PATCHed
onto a part, but one stored before that refusal is still in the row. #1044
stopped every screen showing it ("Included in {bundle}"), and the advisor ruled
(#736 6115773247) that it stops counting toward savings too, so the savings
figures stop contradicting that cell.

The rule, which keeps the earlier ruling that a Cut part with no cost is an
UNKNOWN saving: a part's stored cost is read as no cost. So a Cut part still
makes savings a floor ("≥ $…"), and its legacy figure never adds to it.

The plan: CrowdStrike Falcon (120,000) Cut, and Microsoft Defender for Endpoint,
a part of Microsoft 365 E5 holding a legacy 20,000, Cut; everything else Keep.
Before: $140,000, known. After: at least $120,000.

One test per surface, each through that surface's own endpoint or file, as
`test_tech_debt_savings_surfaces.py` pins the six for #804.
"""

from __future__ import annotations

import pytest

from tests.unit.test_tech_debt_bundle_components import (
    SPLIT_BESIDE_TOOLS,
    _docx_text,
    _extract_and_split,
    _pdf_text,
    _store_legacy_part_cost,
)
from tests.unit.test_tech_debt_dashboard import (  # noqa: F401  (fixture)
    _register,
    app_client,
)

pytestmark = pytest.mark.unit

LEGACY = 20000
PLAN = {"CrowdStrike Falcon": "cut", "Microsoft Defender for Endpoint": "cut"}
#: CrowdStrike alone: the part's legacy 20,000 is not a saving.
SAVINGS = 120_000.0


@pytest.fixture()
def released(app_client):  # noqa: F811
    c, provider = app_client
    h, svc, lst, items, bundle_id = _extract_and_split(c, provider, SPLIT_BESIDE_TOOLS)
    client = _register(c, "client@example.com")
    _store_legacy_part_cost(bundle_id, LEGACY, expected=len(SPLIT_BESIDE_TOOLS))
    for it in items:
        r = c.patch(
            f"/tech-debt/capability-items/{it['id']}",
            headers=h,
            json={"disposition": PLAN.get(it["name"], "keep")},
        )
        assert r.status_code == 200, r.text
    plan_card = c.get(f"/tech-debt/services/{svc}/consolidation-plan", headers=h)
    assert plan_card.status_code == 200, plan_card.text
    preview = c.post(
        f"/tech-debt/capability-lists/{lst['id']}/savings-preview",
        headers=h,
        json={"dispositions": {}},
    )
    assert preview.status_code == 200, preview.text
    assert c.post(f"/tech-debt/capability-lists/{lst['id']}/approve", headers=h).status_code == 200
    fin = c.post(f"/tech-debt/services/{svc}/deliverables/finalize", headers=h)
    assert fin.status_code == 201, fin.text
    deliv = fin.json()
    rel = c.post(f"/tech-debt/deliverables/{deliv['id']}/release", headers=h)
    assert rel.status_code == 200, rel.text
    files = {}
    for kind in ("pdf", "docx"):
        got = c.get(f"/artifacts/{deliv[f'{kind}_artifact_id']}/download", headers=h)
        assert got.status_code == 200, got.text
        files[kind] = got.content
    cid = client["user"]["client_id"]
    ch = {"Authorization": f"Bearer {client['tokens']['access_token']}", "X-Client-Id": cid}
    dash = c.get(f"/clients/{cid}/tech-debt/{svc}/dashboard", headers=ch)
    assert dash.status_code == 200, dash.text
    home = c.get(f"/clients/{cid}/value-summary", headers=ch)
    assert home.status_code == 200, home.text
    return {
        "summary": deliv["summary"],
        "plan": plan_card.json(),
        "preview": preview.json(),
        "dash": dash.json(),
        "home": home.json(),
        "files": files,
    }


def test_the_deliverable_summary_leaves_out_a_parts_legacy_cost(released) -> None:
    assert "≥ $120,000 estimated annual savings" in released["summary"], released["summary"]


def test_the_pdf_and_docx_leave_out_a_parts_legacy_cost(released) -> None:
    for text in (_pdf_text(released["files"]["pdf"]), _docx_text(released["files"]["docx"])):
        assert "Estimated annual savings: ≥ $120,000" in text, text
        assert "$140,000" not in text


def test_the_plan_card_leaves_out_a_parts_legacy_cost(released) -> None:
    assert released["plan"]["estimated_annual_savings"] == SAVINGS
    assert released["plan"]["savings_cost_known"] is False


def test_the_what_if_leaves_out_a_parts_legacy_cost(released) -> None:
    assert released["preview"]["estimated_annual_savings"] == SAVINGS
    assert released["preview"]["savings_cost_known"] is False


def test_the_client_dashboard_headline_leaves_out_a_parts_legacy_cost(released) -> None:
    assert released["dash"]["identified_savings_usd"] == SAVINGS
    assert released["dash"]["savings_cost_known"] is False


def test_the_client_dashboard_redundancy_leaves_out_a_parts_legacy_cost(released) -> None:
    by_cat = {r["category"]: r["savings_usd"] for r in released["dash"]["redundancies"]}
    assert by_cat["EDR"] == SAVINGS, by_cat


def test_the_home_value_card_leaves_out_a_parts_legacy_cost(released) -> None:
    assert released["home"]["tech_debt_savings_usd"] == SAVINGS
    assert released["home"]["tech_debt_savings_cost_known"] is False
