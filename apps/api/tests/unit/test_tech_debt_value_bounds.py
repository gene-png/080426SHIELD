"""#879: a consultant's cost and licence count are bounded like the extraction's.

`PATCH /capability-items/{id}` and `POST .../excluded-rows/{i}/include` took
`annual_cost_usd` and `license_count` with no bounds: a cost of 1e13 overflows
`Numeric(14, 2)` and 2**31 overflows `Integer` -- untyped 500s on Postgres that
SQLite never shows -- and a negative was stored. Both routes now refuse with a
typed 422, using the SAME bounds the extraction uses (`tech_debt/bounds.py`).

The copy (V1-V3) is the plan's, pending the advisor's approval on #736; every
expected string is written out here.
"""

from __future__ import annotations

import json

import pytest

from app.ai.llm import LLMResponse
from tests._ai_runs import tech_debt_extract
from tests.unit.test_tech_debt_routes import (  # noqa: F401  (fixture)
    _register,
    _upload_csv,
    app_client,
)

pytestmark = pytest.mark.unit

V1 = {
    "reason": "capability_cost_out_of_range",
    "message": "Annual cost must be between $0 and $999,999,999,999.99.",
}
V2 = {
    "reason": "capability_license_count_out_of_range",
    "message": "License count must be a whole number between 0 and 2,147,483,647.",
}
V3 = {
    "reason": "capability_cost_not_whole_cents",
    "message": "Annual cost can have at most two decimal places.",
}


def _world(app_client):  # noqa: F811
    """A list with one item (row 0) and one excluded row (row 1)."""
    c, _Sess, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    item = {
        "name": "Tool",
        "vendor": None,
        "category": None,
        "function": None,
        "annual_cost_usd": 100,
        "license_count": 5,
        "notes": None,
        "security_related": True,
        "security_functions": ["detect"],
        "confidence_pct": 90,
        "source_row_index": 0,
    }
    provider.register("extract.capabilities", lambda _p: LLMResponse(json.dumps({"items": [item]})))
    svc = c.post("/tech-debt/services", headers=h, json={"title": "x"}).json()["id"]
    art = _upload_csv(c, bearer, "x.csv", b"name\nrow0\nrow1\n")
    body = tech_debt_extract(c, svc, h, art)
    assert [e["index"] for e in body["excluded_rows"]] == [1]  # APPEAR
    return c, h, body["id"], body["items"][0]["id"], svc


def _latest(c, h, svc) -> dict:
    r = c.get(f"/tech-debt/services/{svc}/capability-lists/latest", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _error(r) -> dict:
    e = r.json()["error"]
    return {"reason": e["reason"], "message": e["message"]}


REFUSED = [
    ({"annual_cost_usd": -1}, V1),
    ({"annual_cost_usd": 1e13}, V1),
    ({"annual_cost_usd": 999999999999.995}, V1),
    ({"annual_cost_usd": 12.345}, V3),
    ({"license_count": -1}, V2),
    ({"license_count": 2**31}, V2),
]
ACCEPTED = [
    ({"annual_cost_usd": 999999999999.99}, ("annual_cost_usd", 999999999999.99)),
    ({"annual_cost_usd": 0}, ("annual_cost_usd", 0.0)),
    ({"annual_cost_usd": 12.5}, ("annual_cost_usd", 12.5)),
    ({"license_count": 2**31 - 1}, ("license_count", 2**31 - 1)),
    ({"license_count": 0}, ("license_count", 0)),
]


@pytest.mark.parametrize(("patch", "error"), REFUSED)
def test_the_patch_refuses_a_value_the_column_cannot_hold(
    app_client, patch, error  # noqa: F811
) -> None:
    c, h, _list_id, item_id, svc = _world(app_client)
    r = c.patch(f"/tech-debt/capability-items/{item_id}", headers=h, json=patch)
    assert r.status_code == 422, r.text
    assert _error(r) == error
    (item,) = _latest(c, h, svc)["items"]
    assert (item["annual_cost_usd"], item["license_count"]) == (100.0, 5)  # nothing written


@pytest.mark.parametrize(("patch", "stored"), ACCEPTED)
def test_the_patch_accepts_the_boundary(app_client, patch, stored) -> None:  # noqa: F811
    c, h, _list_id, item_id, _svc = _world(app_client)
    r = c.patch(f"/tech-debt/capability-items/{item_id}", headers=h, json=patch)
    assert r.status_code == 200, r.text
    field, value = stored
    assert r.json()[field] == value


@pytest.mark.parametrize(("extra", "error"), REFUSED)
def test_including_a_row_refuses_a_value_the_column_cannot_hold(
    app_client, extra, error  # noqa: F811
) -> None:
    c, h, list_id, _item_id, svc = _world(app_client)
    r = c.post(
        f"/tech-debt/capability-lists/{list_id}/excluded-rows/1/include",
        headers=h,
        json={"name": "Included", **extra},
    )
    assert r.status_code == 422, r.text
    assert _error(r) == error
    latest = _latest(c, h, svc)
    assert [i["name"] for i in latest["items"]] == ["Tool"]  # nothing written
    assert [e["index"] for e in latest["excluded_rows"]] == [1]


def test_including_a_row_accepts_the_boundary(app_client) -> None:  # noqa: F811
    c, h, list_id, _item_id, _svc = _world(app_client)
    r = c.post(
        f"/tech-debt/capability-lists/{list_id}/excluded-rows/1/include",
        headers=h,
        json={"name": "Included", "annual_cost_usd": 999999999999.99, "license_count": 2**31 - 1},
    )
    assert r.status_code in (200, 201), r.text
    included = next(i for i in r.json()["items"] if i["name"] == "Included")
    assert (included["annual_cost_usd"], included["license_count"]) == (999999999999.99, 2**31 - 1)
