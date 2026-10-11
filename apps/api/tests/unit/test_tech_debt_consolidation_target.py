"""#807: the capability-item PATCH validates `consolidation_target_id`.

The tool a row is "covered by" must be another row on the SAME list. Anything
else is a typed 422 and nothing in the body is written:
  * the row itself;
  * a row on another list of this tenant;
  * a row on ANOTHER TENANT's list -- refused with exactly the reply an id that
    does not exist gets, so the PATCH cannot be used to learn whether another
    tenant's id exists;
  * an id that does not exist.
`null` clears it.

Every expected string is written out here, never imported from the route.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.capability import CapabilityItem
from app.models.client import Client
from tests.unit.test_tech_debt_routes import (  # noqa: F401  (fixture)
    _register,
    _seed_three_item_list,
    app_client,
)

pytestmark = pytest.mark.unit

SELF = {
    "reason": "consolidation_target_self",
    "message": "A tool cannot be marked as covered by itself.",
}
NOT_IN_LIST = {
    "reason": "consolidation_target_not_in_list",
    "message": "The covering tool must be on the same list.",
}


def _patch(c, bearer: str, item_id: str, body: dict):
    headers = {"Authorization": f"Bearer {bearer}"}
    return c.patch(f"/tech-debt/capability-items/{item_id}", headers=headers, json=body)


def _error(r) -> dict:
    """The typed error, without the per-request fields the envelope adds."""
    e = r.json()["error"]
    return {"reason": e["reason"], "message": e["message"]}


def _stored(Sess, item_id: str) -> CapabilityItem:
    with Sess() as s:
        item = s.get(CapabilityItem, uuid.UUID(item_id))
        s.expunge(item)
        return item


def _admin_with_list(app_client) -> tuple:  # noqa: F811
    c, Sess, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    _svc, ids = _seed_three_item_list(c, bearer, provider)
    return c, Sess, provider, bearer, ids


def test_a_row_on_the_same_list_is_accepted_and_null_clears_it(app_client) -> None:  # noqa: F811
    c, Sess, _p, bearer, ids = _admin_with_list(app_client)
    r = _patch(c, bearer, ids[0], {"disposition": "consolidate", "consolidation_target_id": ids[1]})
    assert r.status_code == 200, r.text
    assert r.json()["consolidation_target_id"] == ids[1]
    assert str(_stored(Sess, ids[0]).consolidation_target_id) == ids[1]

    r = _patch(c, bearer, ids[0], {"consolidation_target_id": None})
    assert r.status_code == 200, r.text
    assert _stored(Sess, ids[0]).consolidation_target_id is None


def test_the_row_itself_is_refused_and_nothing_is_written(app_client) -> None:  # noqa: F811
    c, Sess, _p, bearer, ids = _admin_with_list(app_client)
    r = _patch(c, bearer, ids[0], {"vendor": "Changed", "consolidation_target_id": ids[0]})
    assert r.status_code == 422, r.text
    assert _error(r) == SELF
    stored = _stored(Sess, ids[0])
    assert stored.consolidation_target_id is None
    assert stored.vendor != "Changed"


def test_a_row_on_another_list_of_this_tenant_is_refused(app_client) -> None:  # noqa: F811
    c, Sess, provider, bearer, ids = _admin_with_list(app_client)
    _svc, other = _seed_three_item_list(c, bearer, provider)
    assert set(other).isdisjoint(ids)  # APPEAR: a second list exists
    r = _patch(c, bearer, ids[0], {"consolidation_target_id": other[0]})
    assert r.status_code == 422, r.text
    assert _error(r) == NOT_IN_LIST
    assert _stored(Sess, ids[0]).consolidation_target_id is None


def test_another_tenants_row_is_refused_exactly_like_an_unknown_id(
    app_client,  # noqa: F811
) -> None:
    c, Sess, provider, bearer, ids = _admin_with_list(app_client)
    home_tenant = c.headers["X-Client-Id"]
    with Sess() as s:
        tenant = Client(legal_name="Other Tenant")
        s.add(tenant)
        s.commit()
        other_tenant = str(tenant.id)
    # The admin works in the other tenant and builds a list there.
    c.headers["X-Client-Id"] = other_tenant
    _svc, foreign = _seed_three_item_list(c, bearer, provider)
    c.headers["X-Client-Id"] = home_tenant
    assert len(foreign) == 3  # APPEAR: the other tenant's rows exist

    cross = _patch(c, bearer, ids[0], {"consolidation_target_id": foreign[0]})
    unknown = _patch(c, bearer, ids[0], {"consolidation_target_id": str(uuid.uuid4())})
    assert cross.status_code == 422, cross.text
    assert _error(cross) == NOT_IN_LIST
    assert (unknown.status_code, _error(unknown)) == (cross.status_code, _error(cross))
    assert _stored(Sess, ids[0]).consolidation_target_id is None
