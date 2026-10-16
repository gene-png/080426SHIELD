"""#1214: the client's "Annual spend by category" counts an uncosted tool as
$0, so each category now says how many of its tools have no cost.

Ruled on #736 (6216024281, T3): option (a). The API gives every category a
`no_cost_count` by TD-10's one rule (`overlap.no_cost_items`), and the chart's
tooltip reads "≥ $X" with TD-10 copy 1 beneath it when the count is above 0.
Driven through the dashboard endpoint, on `test_tech_debt_no_cost_count.py`'s
released world (EDR: CrowdStrike, Defender at a RECORDED $0; PAM: CyberArk,
BeyondTrust; SIEM: Splunk ES alone).
"""

from __future__ import annotations

import pytest

from tests.unit.test_tech_debt_dashboard import app_client  # noqa: F401  (fixture)
from tests.unit.test_tech_debt_no_cost_count import _dashboard, _null_costs, _released

pytestmark = pytest.mark.unit


def _by_category(rows: list[dict]) -> dict[str, dict]:
    return {r["category"]: r for r in rows}


def test_each_category_counts_its_own_uncosted_tools(app_client) -> None:  # noqa: F811
    c, client, svc_id = _released(app_client)
    _null_costs("Splunk ES", "CyberArk")
    spend = _by_category(_dashboard(c, client, svc_id)["spend_by_category"])
    # SIEM is made only of an uncosted tool: its $0 is a floor, and says so.
    assert (spend["SIEM"]["total_usd"], spend["SIEM"]["no_cost_count"]) == (0.0, 1)
    # PAM is mixed: BeyondTrust's cost, and CyberArk's missing one.
    assert (spend["PAM"]["total_usd"], spend["PAM"]["no_cost_count"]) == (38000.0, 1)
    # A recorded $0 (Defender) is a cost, not a missing one.
    assert spend["EDR"]["no_cost_count"] == 0


def test_the_categories_add_up_to_the_headline_count(app_client) -> None:  # noqa: F811
    """One rule: the per-category counts and the headline's cannot disagree."""
    c, client, svc_id = _released(app_client)
    _null_costs("Splunk ES", "CyberArk")
    body = _dashboard(c, client, svc_id)
    assert body["no_cost_count"] == 2  # POSITIVE CONTROL: the world has two
    assert sum(r["no_cost_count"] for r in body["spend_by_category"]) == 2


def test_every_category_is_zero_when_every_cost_is_recorded(app_client) -> None:  # noqa: F811
    c, client, svc_id = _released(app_client)
    body = _dashboard(c, client, svc_id)
    assert {r["category"] for r in body["spend_by_category"]} == {"EDR", "PAM", "SIEM"}
    assert [r["no_cost_count"] for r in body["spend_by_category"]] == [0, 0, 0]


def test_the_sprawl_rows_carry_the_same_count(app_client) -> None:  # noqa: F811
    """The donut shares the type; its rows are the same categories' counts."""
    c, client, svc_id = _released(app_client)
    _null_costs("CyberArk")
    sprawl = _by_category(_dashboard(c, client, svc_id)["sprawl_by_category"])
    assert sprawl["PAM"]["no_cost_count"] == 1
    assert sprawl["EDR"]["no_cost_count"] == 0
