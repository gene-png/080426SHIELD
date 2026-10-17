"""#1277: two ATT&CK counts include UNSCORED rows (tools, no status), the shape
#1010 fixed for C1 ("{n} technique rows credit a tool that is not in the
client's security tool list, so their status may count a tool ...").

An unscored row has no status, so a sentence about what a status counts is not
about it, and the client dashboard's matrix does not draw it:

* the dashboard's "Retirement status could not be determined for {n} cited
  tools" counted tools cited ONLY by an unscored row, which no row on the page
  shows;
* the scenario panel's base line counted unscored rows beside C1, so on one
  assessment the two screens gave different numbers for the same sentence.

Expected values are the approved sentences written out and the rows each screen
itself shows, never a count read from the module under test.
"""

from __future__ import annotations

import pytest

from app.models.capability import CapabilityListStatus
from tests._attack_rows import standalone_rows
from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)
from tests.unit.test_attack_planned_retirement import (
    PLANNED_SENTENCE,
    ROWS,
    UNKNOWN_SENTENCE,
    _approve_finalize,
    _auth,
    _tech_debt_list,
    env,  # noqa: F401  (fixture)
)
from tests.unit.test_attack_planned_retirement import (
    _world as _retirement_world,
)
from tests.unit.test_attack_subset_count_matches_rows import _drifting_world
from tests.unit.test_attack_subset_drift import LEGACY

pytestmark = pytest.mark.unit

ORPHAN = "Orphan Tool"

BASE_LINE_ONE = 1  # rows crediting LEGACY that have a status (row one only)


def test_the_dashboard_does_not_count_a_tool_only_an_unscored_row_cites(env) -> None:  # noqa: F811
    c, Sess, bearer, client, client_id, svc, a, _ids = _retirement_world(env)
    # A DRAFT list names ORPHAN, so approve accepts the citation (#851) and a
    # draft does not vote on retirement: the tool is UNKNOWN, on a row with no
    # status.
    _tech_debt_list(
        Sess,
        client_id,
        client["user"]["id"],
        status=CapabilityListStatus.DRAFT,
        items=[(ORPHAN, None)],
    )
    unscored = standalone_rows(a["coverage"], len(ROWS) + 1)[len(ROWS)]
    r = c.patch(
        f"/attack/coverage/{unscored['id']}",
        headers=_auth(bearer),
        json={"detection_tools": [ORPHAN]},
    )
    assert r.status_code == 200, r.text
    fin = _approve_finalize(c, bearer, svc, a)
    rel = c.post(f"/attack/deliverables/{fin['id']}/release", headers=_auth(bearer))
    assert rel.status_code == 200, rel.text
    c.headers["X-Client-Id"] = client_id
    dash = c.get(
        f"/clients/{client_id}/attack/{svc}/dashboard",
        headers=_auth(client["tokens"]["access_token"]),
    )
    assert dash.status_code == 200, dash.text
    body = dash.json()
    # Positive first: the page shows the five scored rows and not the unscored
    # one, and ORPHAN is on no drawn row.
    shown_tools = {
        t
        for row in body["techniques"]
        for t in (*row["detection_tools"], *row["prevention_tools"], *row["response_tools"])
    }
    assert ORPHAN not in shown_tools, sorted(shown_tools)
    assert "Tenable" in shown_tools and "Homegrown Script" in shown_tools
    # Two unknown tools are on the page; ORPHAN is not one of them.
    assert body["retirement_notes"] == [PLANNED_SENTENCE, UNKNOWN_SENTENCE], body.get(
        "retirement_notes"
    )
    # The document still counts it: the unscored row's tools are printed and
    # marked there (the Unscored sheet), so its sentence says three. A
    # deliberate difference between the screen and the file, pinned so a fix
    # that moves the filter into the shared count is seen.
    assert "Retirement status could not be determined for 3 cited tools." in fin["summary"], fin[
        "summary"
    ]


def test_the_scenario_base_counts_only_rows_with_a_status(
    app_parts, tmp_path  # noqa: F811
) -> None:
    w, one, two = _drifting_world(app_parts, tmp_path)
    assert w.approve().status_code == 200
    w.confirm_not_security(LEGACY)
    r = w.c.get(f"/attack/services/{w.svc_id}/scenarios", headers=w.h)
    assert r.status_code == 200, r.text
    base = r.json()["base"]
    assert base is not None
    # Row one (Covered) and row two (no status) both credit LEGACY, which has
    # left the security tool list; only row one has a status.
    assert base["citations_outside_subset"] == BASE_LINE_ONE, base
