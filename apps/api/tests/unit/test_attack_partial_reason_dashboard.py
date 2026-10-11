"""The client ATT&CK dashboard carries each Partial technique's reason (#554 R1).

Through the route a client calls, on a released assessment under #620's rules:
a standalone Partial with a reason, a computed parent made Partial by its
children, and a Covered row. The wording is the approved text on #554, copied
here, never imported. Rule 1 (an assessment approved before #620) is pinned by
the amended `tests/golden/parent_rules_old/dashboard.json`.
"""

from __future__ import annotations

import pytest

from app.attack.catalog import TECHNIQUES
from tests._attack_rows import standalone_rows
from tests.unit.test_attack_catalog_version_guard import (  # noqa: F401  (fixture)
    _auth,
    _register,
    _service_and_assessment,
    env,
)

pytestmark = pytest.mark.unit

REACH = {
    "label": "Not covered everywhere",
    "sentence": "Defended on most of your environment, but not on some systems, such as "
    "another operating system, a cloud or SaaS service, or unmanaged or off-network devices.",
}
SET_BY = {
    "label": "Set by its sub-techniques",
    "sentence": "This technique's coverage is computed from its sub-techniques; see each "
    "sub-technique for its own coverage and reason.",
}


def _tools_for(status: str) -> dict:
    """#554 R3: the tools that make each status, so the status computed from
    Detect / Prevent / Respond is the one this test sets."""
    if status == "covered":
        return {
            "detection_tools": ["Tool A"],
            "prevention_tools": ["Tool A"],
            "response_tools": ["Tool A"],
        }
    if status == "partial":
        return {"detection_tools": ["Tool A"]}
    return {"detection_tools": []}


def _family() -> tuple[str, list[str]]:
    """Derived from the catalog's parent links, not from `app.attack.parents`."""
    kids: dict[str, list[str]] = {}
    for t in TECHNIQUES:
        if t.parent_id is not None:
            kids.setdefault(t.parent_id, []).append(t.id)
    parent = min((p for p in kids if len(kids[p]) >= 2), key=lambda p: (len(kids[p]), p))
    return parent, sorted(kids[parent])


def test_the_dashboard_says_why_each_partial_is_partial(env) -> None:  # noqa: F811
    c, _Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    by_code = {row["technique_code"]: row for row in a["coverage"]}
    partial_row, covered_row = standalone_rows(a["coverage"], 2)
    parent, (first, *rest) = _family()

    writes = [
        (partial_row["id"], {"status": "partial", "reason_code": "reach_limited"}),
        (covered_row["id"], {"status": "covered"}),
        (by_code[first]["id"], {"status": "covered"}),
        *[(by_code[code]["id"], {"status": "gap"}) for code in rest],
    ]
    for row_id, body in writes:
        r = c.patch(
            f"/attack/coverage/{row_id}",
            headers=_auth(bearer),
            json={**body, **_tools_for(body["status"])},
        )
        assert r.status_code == 200, r.text
    assert (
        c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer)).status_code == 200
    )
    fin = c.post(f"/attack/services/{svc}/deliverables/finalize", headers=_auth(bearer))
    assert fin.status_code in (200, 201), fin.text
    rel = c.post(f"/attack/deliverables/{fin.json()['id']}/release", headers=_auth(bearer))
    assert rel.status_code == 200, rel.text

    client_id = client["user"]["client_id"]
    c.headers["X-Client-Id"] = client_id
    dash = c.get(
        f"/clients/{client_id}/attack/{svc}/dashboard",
        headers=_auth(client["tokens"]["access_token"]),
    )
    assert dash.status_code == 200, dash.text
    techs = {t["code"]: t for t in dash.json()["techniques"]}

    assert techs[partial_row["technique_code"]]["partial_reason"] == REACH
    assert techs[parent]["status"] == "partial", techs[parent]
    assert techs[parent]["partial_reason"] == SET_BY
    # Only a Partial carries the key: a Covered row's response is unchanged.
    assert "partial_reason" not in techs[covered_row["technique_code"]], techs[
        covered_row["technique_code"]
    ]

    # The by-reason table (the advisor's ruling (i), #736 18:34Z): the same
    # rows and counts the deliverable's table prints, from the same function,
    # adding up to the rollup's Partial figure.
    body = dash.json()
    assert body["partial_reasons"] == [
        {**REACH, "count": 1},
        {**SET_BY, "count": 1},
    ], body.get("partial_reasons")
    assert sum(r["count"] for r in body["partial_reasons"]) == body["rollup"]["partial"]


def test_the_dashboard_has_no_reason_table_without_a_partial(env) -> None:  # noqa: F811
    """OMITTED, not empty: a dashboard with no Partial is unchanged."""
    c, _Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    (row,) = standalone_rows(a["coverage"], 1)
    r = c.patch(
        f"/attack/coverage/{row['id']}",
        headers=_auth(bearer),
        json={"status": "covered", **_tools_for("covered")},
    )
    assert r.status_code == 200, r.text
    assert (
        c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer)).status_code == 200
    )
    fin = c.post(f"/attack/services/{svc}/deliverables/finalize", headers=_auth(bearer))
    assert fin.status_code in (200, 201), fin.text
    assert (
        c.post(
            f"/attack/deliverables/{fin.json()['id']}/release", headers=_auth(bearer)
        ).status_code
        == 200
    )
    client_id = client["user"]["client_id"]
    c.headers["X-Client-Id"] = client_id
    body = c.get(
        f"/clients/{client_id}/attack/{svc}/dashboard",
        headers=_auth(client["tokens"]["access_token"]),
    ).json()
    assert body["techniques"], body  # APPEAR before ABSENT
    assert "partial_reasons" not in body, sorted(body)
