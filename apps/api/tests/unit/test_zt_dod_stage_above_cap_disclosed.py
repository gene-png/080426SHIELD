"""A stage stored above its capability's maximum is disclosed everywhere (#839, S1).

The advisor's ruling (#736 comment 6048561596): such a stage is LEFT as stored,
counted at the capped level in every figure, and disclosed on the screen and in
all three files. S1 was approved verbatim at 6049667540; the expected sentence
below is the example in 6049167247, copied from that comment.

The world: a DoD engagement with every capability at stage 2 through the API,
then 1.1 User Inventory (no Advanced activity) set to 3 straight in the store,
as a row written before the write-path guard would be. Then approve, finalize
and release. Checked through the endpoints a consultant and a client reach and
the files a client receives.
"""

from __future__ import annotations

import io
import uuid

import pytest
from sqlalchemy import update

from app.models.zt_assessment import ZtAnswer
from tests._ai_mode import docx_text, env_sessions, pdf_text
from tests.unit.test_zt_dashboard import (  # noqa: F401  (fixture)
    _register,
    app_client,
)

pytestmark = pytest.mark.unit

S1 = (
    "1.1 User Inventory is recorded at stage 3, but it has no DoD Advanced "
    "activities, so every figure here counts it as Target (2)."
)


def _world(c, *, over_cap: bool) -> tuple[str, str, dict, dict]:
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = c.post(
        "/zt/services", headers=h, json={"kind": "zero_trust_dod", "title": "ZT"}
    ).json()["id"]
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h).json()
    for ans in a["answers"]:
        r = c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"maturity_stage": 2})
        assert r.status_code == 200, r.text
    if over_cap:
        with env_sessions()() as db:
            db.execute(
                update(ZtAnswer)
                .where(
                    ZtAnswer.assessment_id == uuid.UUID(a["id"]),
                    ZtAnswer.capability_code == "DOD.USR.01",
                )
                .values(maturity_stage=3)
            )
            db.commit()
    assert c.post(f"/zt/assessments/{a['id']}/approve", headers=h).status_code == 200
    deliv = c.post(f"/zt/services/{svc_id}/deliverables/finalize", headers=h)
    assert deliv.status_code in (200, 201), deliv.text
    rel = c.post(f"/zt/deliverables/{deliv.json()['id']}/release", headers=h)
    assert rel.status_code == 200, rel.text
    return svc_id, bearer, h, client


def _files(c, svc_id: str, h: dict) -> tuple[str, str, object]:
    from openpyxl import load_workbook

    body = c.get(f"/zt/services/{svc_id}/deliverables/latest", headers=h).json()

    def _bytes(key: str) -> bytes:
        dl = c.get(f"/artifacts/{body[key]}/download", headers=h)
        assert dl.status_code == 200, dl.text
        return dl.content

    wb = load_workbook(io.BytesIO(_bytes("xlsx_artifact_id")))
    return pdf_text(_bytes("pdf_artifact_id")), docx_text(_bytes("docx_artifact_id")), wb


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_workspace_gap_endpoint_discloses_it(app_client) -> None:  # noqa: F811
    c = app_client
    svc_id, _bearer, h, _client = _world(c, over_cap=True)
    r = c.get(f"/zt/services/{svc_id}/gap-analysis?target_stage=3", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["stage_above_max_notes"] == [S1]


def test_the_client_dashboard_discloses_it(app_client) -> None:  # noqa: F811
    c = app_client
    svc_id, _bearer, _h, client = _world(c, over_cap=True)
    client_id = client["user"]["client_id"]
    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["stage_above_max_notes"] == [S1]


def test_every_released_file_discloses_it_and_keeps_the_stored_stage(
    app_client,  # noqa: F811
) -> None:
    c = app_client
    svc_id, _bearer, h, _client = _world(c, over_cap=True)
    pdf, docx, wb = _files(c, svc_id, h)
    assert S1 in _flat(pdf)
    assert S1 in _flat(docx)
    summary = [str(v) for row in wb["Score Summary"].iter_rows(values_only=True) for v in row if v]
    assert S1 in summary
    # The Answers sheet keeps the stored stage: never rewritten (6049667540).
    answers = {row[0]: row for row in wb["Answers"].iter_rows(values_only=True)}
    assert answers["DOD.USR.01"][4] == 3


def test_nothing_is_disclosed_when_every_stage_is_reachable(app_client) -> None:  # noqa: F811
    c = app_client
    svc_id, _bearer, h, _client = _world(c, over_cap=False)
    r = c.get(f"/zt/services/{svc_id}/gap-analysis?target_stage=3", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["stage_above_max_notes"] == []
    pdf, docx, _wb = _files(c, svc_id, h)
    # A real rendered file, so the absences below mean something.
    assert "DoD ZT Reference Architecture" in _flat(pdf)
    assert "DoD ZT Reference Architecture" in _flat(docx)
    assert "is recorded at stage" not in _flat(pdf)
    assert "is recorded at stage" not in _flat(docx)
