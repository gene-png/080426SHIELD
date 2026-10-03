"""#810: a tool marked "Cut, covered by another tool" is a PLANNED RETIREMENT
on ATT&CK, as a Cut tool is.

Gene decided it on 2026-10-03 and the advisor ruled it on #736: the retiring
set is ONE definition (`models/capability.py::RETIRING_DISPOSITIONS`) read by
Tech Debt savings and by ATT&CK's marks. Driven through the deliverable (XLSX)
and the client dashboard. The world: an approved plan with one covered-cut tool
and one kept tool, both cited by one covered technique.
"""

from __future__ import annotations

import pytest

from app.models.capability import CapabilityDisposition, CapabilityListStatus
from tests._attack_rows import standalone_rows
from tests.unit.test_attack_catalog_version_guard import (  # noqa: F401  (fixture)
    _auth,
    _register,
    _service_and_assessment,
    env,
)
from tests.unit.test_attack_planned_retirement import (
    _approve_finalize,
    _download,
    _tech_debt_list,
    _xlsx_tool_cells,
)

pytestmark = pytest.mark.unit

COVERED_CUT = "Splunk Enterprise"
KEPT = "CrowdStrike Falcon"


def _world(env):  # noqa: F811
    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    client_id = client["user"]["client_id"]
    _tech_debt_list(
        Sess,
        client_id,
        admin["user"]["id"],
        status=CapabilityListStatus.APPROVED,
        items=[
            (COVERED_CUT, CapabilityDisposition.CONSOLIDATE),
            (KEPT, CapabilityDisposition.KEEP),
        ],
    )
    svc, a = _service_and_assessment(c, bearer)
    (row,) = standalone_rows(a["coverage"], 1)
    r = c.patch(
        f"/attack/coverage/{row['id']}",
        headers=_auth(bearer),
        json={"status": "covered", "detection_tools": [COVERED_CUT, KEPT]},
    )
    assert r.status_code == 200, r.text
    return c, bearer, client, client_id, svc, a


def test_the_xlsx_marks_a_covered_cut_tool_as_a_planned_retirement(env) -> None:  # noqa: F811
    c, bearer, _client, _cid, svc, a = _world(env)
    fin = _approve_finalize(c, bearer, svc, a)
    cells = _xlsx_tool_cells(_download(c, bearer, fin["xlsx_artifact_id"]))
    assert f"{COVERED_CUT} (planned retirement); {KEPT}" in cells, cells


def test_the_client_dashboard_marks_a_covered_cut_tool(env) -> None:  # noqa: F811
    c, bearer, client, client_id, svc, a = _world(env)
    fin = _approve_finalize(c, bearer, svc, a)
    rel = c.post(f"/attack/deliverables/{fin['id']}/release", headers=_auth(bearer))
    assert rel.status_code == 200, rel.text
    c.headers["X-Client-Id"] = client_id
    dash = c.get(
        f"/clients/{client_id}/attack/{svc}/dashboard",
        headers=_auth(client["tokens"]["access_token"]),
    )
    assert dash.status_code == 200, dash.text
    assert dash.json()["tool_retirement"] == {COVERED_CUT: "planned_retirement"}
