"""A bundle part names the bundle that carries its cost (for #929).

A split bundle's part (`parent_item_id` set) has no cost of its own: the parent
row holds the whole license value (`tech_debt/components.py`). The client's
inventory table and redundancy card rendered the part's cost cell as "—", which
reads as an unknown cost where the cost is known and counted on the bundle.

The dashboard therefore sends, on every item, `bundle`:

  - the bundle's name, stripped, for a part;
  - "" for a part whose bundle has a blank name (the item PATCH accepts a
    whitespace-only name, so this state is reachable), and the web shows
    "Included in its bundle" for it;
  - None for a row that is not a part.

Every assertion goes through the client dashboard route, never a helper.
"""

from __future__ import annotations

import pytest

from tests.unit.test_tech_debt_bundle_components import (
    BUNDLE,
    SPLIT_BESIDE_TOOLS,
    _extract_and_split,
    _store_legacy_part_cost,
)
from tests.unit.test_tech_debt_dashboard import (  # noqa: F401  (fixture)
    _register,
    app_client,
)

pytestmark = pytest.mark.unit

PART_NAMES = {c["name"] for c in SPLIT_BESIDE_TOOLS}


@pytest.fixture()
def env(app_client):  # noqa: F811
    return app_client


def _dashboard(c, provider, *, bundle_name: str | None = None, part_cost=None) -> dict:
    """Extract, split, optionally rename the bundle, approve, finalize and
    release; return the client's dashboard."""
    h, svc, lst, items, bundle_id = _extract_and_split(c, provider, SPLIT_BESIDE_TOOLS)
    client = _register(c, "client@example.com")
    if bundle_name is not None:
        r = c.patch(
            f"/tech-debt/capability-items/{bundle_id}", headers=h, json={"name": bundle_name}
        )
        assert r.status_code == 200, r.text
    if part_cost is not None:
        _store_legacy_part_cost(bundle_id, part_cost, expected=len(SPLIT_BESIDE_TOOLS))
    for it in items:
        r = c.patch(
            f"/tech-debt/capability-items/{it['id']}", headers=h, json={"disposition": "keep"}
        )
        assert r.status_code == 200, r.text
    assert c.post(f"/tech-debt/capability-lists/{lst['id']}/approve", headers=h).status_code == 200
    fin = c.post(f"/tech-debt/services/{svc}/deliverables/finalize", headers=h)
    assert fin.status_code == 201, fin.text
    rel = c.post(f"/tech-debt/deliverables/{fin.json()['id']}/release", headers=h)
    assert rel.status_code == 200, rel.text
    cid = client["user"]["client_id"]
    ch = {"Authorization": f"Bearer {client['tokens']['access_token']}", "X-Client-Id": cid}
    dash = c.get(f"/clients/{cid}/tech-debt/{svc}/dashboard", headers=ch)
    assert dash.status_code == 200, dash.text
    return dash.json()


def _bundles(rows: list[dict]) -> dict[str, object]:
    return {r["name"]: r["bundle"] for r in rows}


def test_a_part_in_the_inventory_names_its_bundle(env) -> None:
    c, provider = env
    got = _bundles(_dashboard(c, provider)["items"])
    assert {n: got[n] for n in PART_NAMES} == dict.fromkeys(PART_NAMES, BUNDLE)
    # Every other row, the bundle itself included, is not a part.
    assert {n: b for n, b in got.items() if n not in PART_NAMES} == {
        BUNDLE: None,
        "CrowdStrike Falcon": None,
        "Okta": None,
        "Slack": None,
    }


def test_a_part_in_a_redundancy_names_its_bundle(env) -> None:
    c, provider = env
    dash = _dashboard(c, provider)
    edr = next(r for r in dash["redundancies"] if r["category"] == "EDR")
    assert _bundles(edr["items"]) == {
        "Microsoft Defender for Endpoint": BUNDLE,
        "CrowdStrike Falcon": None,
    }


def test_the_bundle_name_is_sent_stripped(env) -> None:
    c, provider = env
    got = _bundles(_dashboard(c, provider, bundle_name="  Microsoft 365 E3  ")["items"])
    assert {n: got[n] for n in PART_NAMES} == dict.fromkeys(PART_NAMES, "Microsoft 365 E3")


def test_a_blank_bundle_name_is_sent_as_an_empty_string(env) -> None:
    """Not None: "" still says "this is a part", and the web words it
    "Included in its bundle"; None would render the part as a plain tool."""
    c, provider = env
    got = _bundles(_dashboard(c, provider, bundle_name="   ")["items"])
    assert {n: got[n] for n in PART_NAMES} == dict.fromkeys(PART_NAMES, "")


def test_a_part_holding_a_legacy_cost_still_names_its_bundle(env) -> None:
    """A pre-#927 cost on a part does not make it a plain tool: spend already
    excludes that cost, so the web must say where the cost is instead."""
    c, provider = env
    got = _bundles(_dashboard(c, provider, part_cost=20000)["items"])
    assert {n: got[n] for n in PART_NAMES} == dict.fromkeys(PART_NAMES, BUNDLE)
