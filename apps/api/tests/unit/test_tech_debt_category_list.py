"""#1176: the category field is a dropdown of the extraction prompt's closed list.

Gene decided: "Category becomes a dropdown of the 29 `CATEGORIES` in
`tech_debt/extract.py` plus "Uncategorized"." The plan (#736 6205635962,
strings approved in 6206818759 item 7):

* `GET /tech-debt/categories` serves the list, so the web never copies it.
  This test reads the expected list out of the PROMPT TEXT, not the tuple.
* The item PATCH accepts a listed value, null ("Uncategorized"), or the row's
  current value unchanged. A stored value outside the list is shown and kept,
  never remapped. Any other value is refused, typed `category_not_on_list`.
"""

from __future__ import annotations

import re

import pytest

from tests.unit.test_tech_debt_routes import (  # noqa: F401  (fixture)
    _create_list_with_item,
    _register,
    app_client,
)

pytestmark = pytest.mark.unit


def _prompt_categories() -> list[str]:
    from app.tech_debt.extract import PROMPT

    after = PROMPT.split("Exactly one value from this list, or `null`:", 1)[1]
    line = next(ln for ln in after.splitlines() if ln.strip())
    return re.findall(r"`([^`]+)`", line)


def _h(bearer: str) -> dict:
    return {"Authorization": f"Bearer {bearer}"}


def _world(app_client):  # noqa: F811
    c, sessions, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc_id, item_id = _create_list_with_item(c, bearer, provider)
    return c, sessions, bearer, svc_id, item_id


def _patch(c, bearer: str, item_id: str, body: dict):
    return c.patch(f"/tech-debt/capability-items/{item_id}", headers=_h(bearer), json=body)


def test_the_endpoint_serves_the_prompts_closed_list(app_client) -> None:  # noqa: F811
    c, _s, bearer, _svc, _item = _world(app_client)
    r = c.get("/tech-debt/categories", headers=_h(bearer))
    assert r.status_code == 200, r.text
    body = r.json()
    expected = _prompt_categories()
    assert len(expected) == 29  # Gene's count, so a parse that finds nothing fails here
    assert body["categories"] == expected
    assert body["uncategorized_label"] == "Uncategorized"


def test_a_listed_category_is_accepted(app_client) -> None:  # noqa: F811
    c, _s, bearer, _svc, item_id = _world(app_client)
    r = _patch(c, bearer, item_id, {"category": "SIEM/SOAR"})
    assert r.status_code == 200, r.text
    assert r.json()["category"] == "SIEM/SOAR"


def test_uncategorized_is_null(app_client) -> None:  # noqa: F811
    c, _s, bearer, _svc, item_id = _world(app_client)
    r = _patch(c, bearer, item_id, {"category": None})
    assert r.status_code == 200, r.text
    assert r.json()["category"] is None


def _set_category_raw(sessions, item_id: str, value: str) -> None:
    import uuid

    from app.models.capability import CapabilityItem

    with sessions() as s:
        s.get(CapabilityItem, uuid.UUID(item_id)).category = value
        s.commit()


def test_an_off_list_value_already_stored_may_be_saved_unchanged(app_client) -> None:  # noqa: F811
    """A row extracted before v3.2 (the old "EDR", say) keeps its value until a
    consultant changes it: re-saving the row must not be refused."""
    c, sessions, bearer, _svc, item_id = _world(app_client)
    _set_category_raw(sessions, item_id, "EDR")
    r = _patch(c, bearer, item_id, {"category": "EDR", "notes": "renewal in May"})
    assert r.status_code == 200, r.text
    assert r.json()["category"] == "EDR"


@pytest.mark.parametrize("bad", ["EDR", "Endpoint", "siem/soar", "SIEM/SOAR ", "Uncategorized"])
def test_any_other_off_list_value_is_refused_and_nothing_is_written(
    app_client, bad: str  # noqa: F811
) -> None:
    c, _s, bearer, svc_id, item_id = _world(app_client)
    r = _patch(c, bearer, item_id, {"category": bad, "notes": "should not be written"})
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert error["reason"] == "category_not_on_list"
    assert error["message"] == "Choose a category from the list, or Uncategorized."
    latest = c.get(
        f"/tech-debt/services/{svc_id}/capability-lists/latest", headers=_h(bearer)
    ).json()
    row = next(i for i in latest["items"] if i["id"] == item_id)
    assert row["category"] == "CNAPP"  # the extraction's value, untouched
    assert row["notes"] is None  # the whole patch was refused, not just the field
