"""TD-5 (for #1060), #1299 folded in: a savings figure built on an AI-estimated
cost says so, with the approved E6 sentence ("1 cost is an AI estimate" /
"{k} costs are AI estimates"), wherever the figure appears: the dashboard's
identified savings, each redundancy card, the home value card and the
deliverable's "Estimated annual savings". Ruled on #736 (6220094031 item 3,
option (a)).

The count is the estimated rows a savings figure INCLUDES: a cut or
cut-and-covered row whose cost is an AI estimate (`savings.SAVINGS_DISPOSITIONS`
and `cost_estimate.is_ai_estimate`). An estimated row that is kept adds
nothing to savings, so it is not counted.
"""

from __future__ import annotations

import pytest

from app.models.capability import CapabilityDisposition
from tests.unit.test_exporters import _item
from tests.unit.test_tech_debt_cost_estimate_surfaces import _dashboard, _mark_estimated
from tests.unit.test_tech_debt_dashboard import (  # noqa: F401  (fixture)
    _register,
    _seed_release,
    app_client,
)
from tests.unit.test_tech_debt_no_cost_count import RENDERERS, _ctx

pytestmark = pytest.mark.unit

CUT = CapabilityDisposition.CUT
KEEP = CapabilityDisposition.KEEP


def _est(name: str, disposition, cost: float = 12_000) -> object:
    return _item(
        name=name, annual_cost_usd=cost, cost_source="ai_estimate", disposition=disposition
    )


# ---------------------------------------------------------------------------
# The deliverable
# ---------------------------------------------------------------------------


@RENDERERS
def test_the_files_say_the_savings_include_an_estimate(render, read) -> None:
    items = [_item(name="A", annual_cost_usd=1_000, disposition=CUT), _est("B", CUT)]
    text = read(render(_ctx(items)))
    assert "1 cost is an AI estimate" in text


@RENDERERS
def test_the_files_use_the_plural_for_several(render, read) -> None:
    items = [_est("A", CUT), _est("B", CUT), _item(name="C", annual_cost_usd=5, disposition=KEEP)]
    text = read(render(_ctx(items)))
    assert "2 costs are AI estimates" in text


@RENDERERS
def test_a_kept_estimate_adds_no_savings_note(render, read) -> None:
    """POSITIVE CONTROL: the estimate is in the total (its own E6 note says
    so), but not in the savings, so the savings carry no sentence."""
    items = [_item(name="A", annual_cost_usd=1_000, disposition=CUT), _est("B", KEEP)]
    text = read(render(_ctx(items)))
    assert "1 cost is an AI estimate" not in text
    assert "Note: 1 annual cost is an AI estimate" in text


# ---------------------------------------------------------------------------
# The client dashboard and the home value card
# ---------------------------------------------------------------------------


def _released(app_client):  # noqa: F811
    c, provider = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    svc_id = _seed_release(c, provider, admin["tokens"]["access_token"], release=True)
    return c, client, svc_id


def _value_summary(c, client) -> dict:
    client_id = client["user"]["client_id"]
    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/value-summary",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_the_dashboard_and_home_card_count_the_estimated_cut_rows(app_client) -> None:  # noqa: F811
    c, client, svc_id = _released(app_client)
    # POSITIVE CONTROL: nothing estimated, nothing counted.
    before = _dashboard(c, client, svc_id)
    assert before["savings_ai_estimate_count"] == 0
    assert _value_summary(c, client)["tech_debt_savings_ai_estimate_count"] == 0
    # BeyondTrust (PAM) is cut; Splunk ES (SIEM) is kept.
    _mark_estimated("BeyondTrust", "Splunk ES")
    body = _dashboard(c, client, svc_id)
    assert body["savings_ai_estimate_count"] == 1
    by_cat = {r["category"]: r["savings_ai_estimate_count"] for r in body["redundancies"]}
    assert by_cat == {"PAM": 1, "EDR": 0}
    assert _value_summary(c, client)["tech_debt_savings_ai_estimate_count"] == 1


# ---------------------------------------------------------------------------
# The deliverable's summary line (the client's Results and Home pages)
# ---------------------------------------------------------------------------


def test_the_deliverable_summary_says_the_savings_include_an_estimate(
    app_client,  # noqa: F811
) -> None:
    """The finalize route stores a one-line summary the client reads on its
    Results and Home pages. It states the savings figure, so it carries the
    same sentence as every other savings figure."""
    c, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id = _seed_release(c, provider, bearer, release=False)

    def finalize() -> str:
        r = c.post(
            f"/tech-debt/services/{svc_id}/deliverables/finalize",
            headers={"Authorization": f"Bearer {bearer}"},
        )
        assert r.status_code == 201, r.text
        return r.json()["summary"]

    # POSITIVE CONTROL: nothing estimated, no sentence.
    assert "AI estimate" not in finalize()
    _mark_estimated("BeyondTrust")  # cut
    summary = finalize()
    assert "estimated annual savings (1 cost is an AI estimate)." in summary, summary
