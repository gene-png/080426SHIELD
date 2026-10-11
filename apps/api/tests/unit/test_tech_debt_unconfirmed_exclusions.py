"""#850: a row the AI excluded must be confirmed before the list is delivered.

Extraction stores the uploaded rows it did not turn into capabilities in
`capability_lists.excluded_rows`, and they leave the spend totals. Approve,
finalize and release now refuse while any of them is unconfirmed -- the same
three gates as #639's "every row decided", for the same reason: a list approved
before this gate can hold one with a current approval. A RELEASED list is
carved out (it refuses the remedy), and a missing `confirmed` key is
unconfirmed (missing data defaults to UNCONFIRMED).

Copy X1, approved (736/5986057990, item 3), quoting the control as it renders.
Every expected string is written out here. Everything goes through the routes.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import update

from app.ai.llm import LLMResponse
from app.models.capability import CapabilityList
from tests._ai_runs import tech_debt_extract
from tests.unit.test_tech_debt_routes import (  # noqa: F401  (fixture)
    _register,
    _upload_csv,
    app_client,
)

pytestmark = pytest.mark.unit


def _x1(then: str) -> str:
    return (
        "1 row the AI excluded is not confirmed yet. In step 2, Review and correct the "
        'extracted list, open "Show the 1 excluded row" and choose "Include…" or '
        f'"Correctly excluded" for it, then {then}.'
    )


def _world(app_client, rows: int = 2):  # noqa: F811
    """One decided item from row 0; rows 1.. excluded and unconfirmed."""
    c, Sess, provider = app_client
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
    csv = "name\n" + "".join(f"row{k}\n" for k in range(rows))
    art = _upload_csv(c, bearer, "x.csv", csv.encode())
    body = tech_debt_extract(c, svc, h, art)
    assert len(body["excluded_rows"]) == rows - 1  # APPEAR: there is an exclusion
    r = c.patch(
        f"/tech-debt/capability-items/{body['items'][0]['id']}",
        headers=h,
        json={"disposition": "keep"},
    )
    assert r.status_code == 200, r.text
    return c, Sess, h, svc, body["id"]


def _error(r) -> dict:
    e = r.json()["error"]
    return {"reason": e["reason"], "message": e["message"]}


def _approve(c, h, list_id):
    return c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=h)


def test_approve_refuses_an_unconfirmed_exclusion(app_client) -> None:  # noqa: F811
    c, _S, h, _svc, list_id = _world(app_client)
    r = _approve(c, h, list_id)
    assert r.status_code == 409, r.text
    assert _error(r) == {
        "reason": "capability_list_unconfirmed_exclusions",
        "message": _x1("approve again"),
    }


def test_the_plural_names_the_count_and_the_control(app_client) -> None:  # noqa: F811
    c, _S, h, _svc, list_id = _world(app_client, rows=4)
    r = _approve(c, h, list_id)
    assert _error(r)["message"] == (
        "3 rows the AI excluded are not confirmed yet. In step 2, Review and correct "
        'the extracted list, open "Show the 3 excluded rows" and choose "Include…" or '
        '"Correctly excluded" for each, then approve again.'
    )


def test_confirming_the_exclusion_lets_approve_through(app_client) -> None:  # noqa: F811
    c, _S, h, _svc, list_id = _world(app_client)
    r = c.post(f"/tech-debt/capability-lists/{list_id}/excluded-rows/1/confirm", headers=h)
    assert r.status_code == 200, r.text
    assert _approve(c, h, list_id).status_code == 200


def test_including_the_row_lets_approve_through(app_client) -> None:  # noqa: F811
    c, _S, h, _svc, list_id = _world(app_client)
    r = c.post(
        f"/tech-debt/capability-lists/{list_id}/excluded-rows/1/include",
        headers=h,
        json={"name": "Included"},
    )
    assert r.status_code in (200, 201), r.text
    included = next(i for i in r.json()["items"] if i["name"] == "Included")
    r = c.patch(
        f"/tech-debt/capability-items/{included['id']}", headers=h, json={"disposition": "keep"}
    )
    assert r.status_code == 200, r.text
    assert _approve(c, h, list_id).status_code == 200


def _legacy_unconfirmed(Sess, list_id: str) -> None:
    """A list approved BEFORE this gate: its exclusion was never confirmed, and
    its approval is current. Written directly, as such a list holds it."""
    with Sess() as s:
        s.execute(
            update(CapabilityList)
            .where(CapabilityList.id == uuid.UUID(list_id))
            .values(excluded_rows=[{"index": 1, "summary": "row1"}])
        )
        s.commit()


def _approved_with_a_legacy_exclusion(app_client):  # noqa: F811
    c, Sess, h, svc, list_id = _world(app_client)
    assert (
        c.post(
            f"/tech-debt/capability-lists/{list_id}/excluded-rows/1/confirm", headers=h
        ).status_code
        == 200
    )
    assert _approve(c, h, list_id).status_code == 200
    _legacy_unconfirmed(Sess, list_id)
    return c, Sess, h, svc, list_id


def test_finalize_refuses_an_approved_list_holding_one(app_client) -> None:  # noqa: F811
    c, _S, h, svc, list_id = _approved_with_a_legacy_exclusion(app_client)
    r = c.post(f"/tech-debt/services/{svc}/deliverables/finalize", headers=h)
    assert r.status_code == 409, r.text
    assert _error(r) == {
        "reason": "capability_list_unconfirmed_exclusions",
        "message": _x1("generate the deliverable again"),
    }
    # The remedy works on an approved list: confirm, approve again, finalize.
    assert (
        c.post(
            f"/tech-debt/capability-lists/{list_id}/excluded-rows/1/confirm", headers=h
        ).status_code
        == 200
    )
    assert _approve(c, h, list_id).status_code == 200
    fin = c.post(f"/tech-debt/services/{svc}/deliverables/finalize", headers=h)
    assert fin.status_code in (200, 201), fin.text


def test_release_refuses_an_approved_list_holding_one(app_client) -> None:  # noqa: F811
    c, Sess, h, svc, list_id = _world(app_client)
    assert (
        c.post(
            f"/tech-debt/capability-lists/{list_id}/excluded-rows/1/confirm", headers=h
        ).status_code
        == 200
    )
    assert _approve(c, h, list_id).status_code == 200
    fin = c.post(f"/tech-debt/services/{svc}/deliverables/finalize", headers=h)
    assert fin.status_code in (200, 201), fin.text
    _legacy_unconfirmed(Sess, list_id)
    r = c.post(f"/tech-debt/deliverables/{fin.json()['id']}/release", headers=h)
    assert r.status_code == 409, r.text
    assert _error(r) == {
        "reason": "capability_list_unconfirmed_exclusions",
        "message": _x1("generate the deliverable again before releasing"),
    }


def test_a_released_list_keeps_re_finalizing(app_client) -> None:  # noqa: F811
    """A released list refuses the remedy (step 2 is locked), so it is carved
    out, as #639 carves out a released list's undecided rows."""
    c, Sess, h, svc, list_id = _world(app_client)
    assert (
        c.post(
            f"/tech-debt/capability-lists/{list_id}/excluded-rows/1/confirm", headers=h
        ).status_code
        == 200
    )
    assert _approve(c, h, list_id).status_code == 200
    fin = c.post(f"/tech-debt/services/{svc}/deliverables/finalize", headers=h)
    rel = c.post(f"/tech-debt/deliverables/{fin.json()['id']}/release", headers=h)
    assert rel.status_code == 200, rel.text
    _legacy_unconfirmed(Sess, list_id)
    again = c.post(f"/tech-debt/services/{svc}/deliverables/finalize", headers=h)
    assert again.status_code in (200, 201), again.text
