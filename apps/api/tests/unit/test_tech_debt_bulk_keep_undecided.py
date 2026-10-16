"""TD-11 (for #1055): "Keep {n} undecided rows" cannot overwrite a decision.

The web button sends the rows that were undecided when the page loaded, with
`only_if_undecided: true`. Another consultant may have decided one of them
since. The route is all-or-nothing, as #641's bulk route already is: one
already-decided row refuses the whole request, typed, and nothing is written,
so "Set {n} rows to Keep." stays exact. Ruled on #736 (6206818759 item 6): the
flag is in this PR.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.audit_entry import AuditEntry
from tests.unit.test_tech_debt_routes import (  # noqa: F401  (fixture)
    _bulk,
    _list_id,
    _plan,
    _register,
    _seed_three_item_list,
    app_client,
)

pytestmark = pytest.mark.unit


def _revision(sessions, list_id: str) -> int:
    """The list's edit revision: a refused click must not move it, or an
    approved list would silently need approving again (#640)."""
    import uuid

    from app.models.capability import CapabilityList

    with sessions() as s:
        return s.get(CapabilityList, uuid.UUID(list_id)).revision


def _world(app_client):  # noqa: F811
    c, sessions, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    return c, sessions, bearer, svc_id, _list_id(c, bearer, svc_id), item_ids


def test_keeping_undecided_rows_writes_them(app_client) -> None:  # noqa: F811
    c, _s, bearer, svc_id, list_id, item_ids = _world(app_client)
    r = _bulk(
        c,
        bearer,
        list_id,
        {"item_ids": item_ids, "disposition": "keep", "only_if_undecided": True},
    )
    assert r.status_code == 200, r.text
    assert [i["disposition"] for i in r.json()["items"]] == ["keep"] * 3
    assert _plan(c, bearer, svc_id)["keep_count"] == 3


def test_one_decided_row_refuses_the_whole_request_and_writes_nothing(
    app_client,  # noqa: F811
) -> None:
    c, sessions, bearer, svc_id, list_id, item_ids = _world(app_client)
    # Another consultant decides one row after the page loaded.
    first = _bulk(c, bearer, list_id, {"item_ids": item_ids[:1], "disposition": "cut"})
    assert first.status_code == 200, first.text
    with sessions() as s:
        audits_before = len(s.execute(select(AuditEntry)).scalars().all())
    revision_before = _revision(sessions, list_id)

    r = _bulk(
        c,
        bearer,
        list_id,
        {"item_ids": item_ids, "disposition": "keep", "only_if_undecided": True},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "capability_items_already_decided"
    # Copy approved on #736 (6216024281 item 2), typed here.
    assert r.json()["error"]["message"] == (
        "1 of the 3 undecided rows now have a decision. Nothing was changed. "
        "Reload the list and try again."
    )
    plan = _plan(c, bearer, svc_id)
    # The decision stands, and the two undecided rows were not written either.
    assert (plan["cut_count"], plan["keep_count"], plan["undecided_count"]) == (1, 0, 2)
    with sessions() as s:
        assert len(s.execute(select(AuditEntry)).scalars().all()) == audits_before
    # The revision bump `_record_edit` made was rolled back with the rows.
    assert _revision(sessions, list_id) == revision_before


def test_the_refusal_for_one_undecided_row_is_singular(app_client) -> None:  # noqa: F811
    """Copy approved on #736 (6216024281 item 2), typed here."""
    c, _s, bearer, _svc, list_id, item_ids = _world(app_client)
    first = _bulk(c, bearer, list_id, {"item_ids": item_ids[:1], "disposition": "cut"})
    assert first.status_code == 200, first.text
    r = _bulk(
        c,
        bearer,
        list_id,
        {"item_ids": item_ids[:1], "disposition": "keep", "only_if_undecided": True},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == (
        "The undecided row now has a decision. Nothing was changed. "
        "Reload the list and try again."
    )


def test_a_decision_landing_just_before_the_write_is_not_overwritten(
    app_client, monkeypatch  # noqa: F811
) -> None:
    """The race the flag exists for. A consultant's decision commits after the
    route read the rows and immediately before it writes, from its own
    session, as a concurrent PATCH would. The route's single conditional
    UPDATE sees it, rolls back and refuses; the decision stands."""
    import uuid

    import sqlalchemy as sa

    import app.routes.tech_debt as td
    from app.models.capability import CapabilityDisposition, CapabilityItem

    c, sessions, bearer, svc_id, list_id, item_ids = _world(app_client)
    real_update = sa.update

    def decide_then_update(*args, **kwargs):
        with sessions() as s:
            s.get(CapabilityItem, uuid.UUID(item_ids[1])).disposition = CapabilityDisposition.CUT
            s.commit()
        return real_update(*args, **kwargs)

    revision_before = _revision(sessions, list_id)
    monkeypatch.setattr(td, "update", decide_then_update)
    r = _bulk(
        c,
        bearer,
        list_id,
        {"item_ids": item_ids, "disposition": "keep", "only_if_undecided": True},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "capability_items_already_decided"
    plan = _plan(c, bearer, svc_id)
    assert (plan["cut_count"], plan["keep_count"], plan["undecided_count"]) == (1, 0, 2)
    # The refused request's own bump was rolled back.
    assert _revision(sessions, list_id) == revision_before


def test_a_refused_click_on_an_approved_list_moves_nothing(app_client) -> None:  # noqa: F811
    """The approved-list case, as it can actually arise. Approve refuses
    undecided rows, so on an approved list the button is offered only after
    rows were set back to undecided -- which already made the approval stale.
    A refused click must not move the revision AGAIN, or the list's state, so
    re-approving the reviewed rows stays a single step."""
    from tests.unit.test_tech_debt_routes import _approve_list, _decide

    c, sessions, bearer, svc_id, list_id, item_ids = _world(app_client)
    _decide(c, bearer, item_ids)
    _approve_list(c, bearer, svc_id)
    back = _bulk(c, bearer, list_id, {"item_ids": item_ids[:2], "disposition": None})
    assert back.status_code == 200, back.text
    # Another consultant decides one of them after this page loaded.
    assert (
        _bulk(c, bearer, list_id, {"item_ids": item_ids[:1], "disposition": "cut"}).status_code
        == 200
    )
    latest_before = c.get(
        f"/tech-debt/services/{svc_id}/capability-lists/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    ).json()
    assert latest_before["status"] == "approved"  # positive control: the state under test
    revision_before = _revision(sessions, list_id)

    r = _bulk(
        c,
        bearer,
        list_id,
        {"item_ids": item_ids[:2], "disposition": "keep", "only_if_undecided": True},
    )
    assert r.status_code == 409, r.text
    assert _revision(sessions, list_id) == revision_before
    latest_after = c.get(
        f"/tech-debt/services/{svc_id}/capability-lists/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    ).json()
    assert latest_after["status"] == "approved"
    assert latest_after["approval_current"] == latest_before["approval_current"]


def test_without_the_flag_the_route_still_overwrites_as_before(app_client) -> None:  # noqa: F811
    """The flag is opt-in: #641's select-and-set keeps its meaning."""
    c, _s, bearer, svc_id, list_id, item_ids = _world(app_client)
    assert (
        _bulk(c, bearer, list_id, {"item_ids": item_ids[:1], "disposition": "cut"}).status_code
        == 200
    )
    r = _bulk(c, bearer, list_id, {"item_ids": item_ids, "disposition": "keep"})
    assert r.status_code == 200, r.text
    assert _plan(c, bearer, svc_id)["keep_count"] == 3


def test_a_successful_keep_writes_one_audit_row_saying_it_was_guarded(
    app_client,  # noqa: F811
) -> None:
    c, sessions, bearer, _svc, list_id, item_ids = _world(app_client)
    r = _bulk(
        c,
        bearer,
        list_id,
        {"item_ids": item_ids, "disposition": "keep", "only_if_undecided": True},
    )
    assert r.status_code == 200, r.text
    with sessions() as s:
        rows = (
            s.execute(
                select(AuditEntry).where(AuditEntry.action == "capability_items.disposition_set")
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].details["item_count"] == 3
    assert rows[0].details["only_if_undecided"] is True
