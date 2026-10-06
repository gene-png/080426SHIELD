"""#646 through zt finalize; see test_ai_source_attack.py for the shape."""

from __future__ import annotations

import pytest

from app.models.llm_call import LLMCallMode
from tests._ai_mode import (
    FIXTURE,
    docx_text,
    env_sessions,
    pdf_text,
    seed_run,
    xlsx_ai_sheet,
)
from tests.unit.test_zt_acceptance import (  # noqa: F401  (fixture)
    _register,
    app_client,
)

pytestmark = pytest.mark.unit


def _files(c, headers: dict, body: dict) -> tuple[str, str, list[list[object]]]:
    def _bytes(key: str) -> bytes:
        dl = c.get(f"/artifacts/{body[key]}/download", headers=headers)
        assert dl.status_code == 200, dl.text
        return dl.content

    return (
        pdf_text(_bytes("pdf_artifact_id")),
        docx_text(_bytes("docx_artifact_id")),
        xlsx_ai_sheet(_bytes("xlsx_artifact_id")),
    )


def test_the_zt_deliverable_states_its_ai_source(app_client) -> None:  # noqa: F811
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = c.post(
        "/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "ZT"}
    ).json()["id"]
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h).json()
    for ans in a["answers"]:
        c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"maturity_stage": 3})
    seed_run(
        env_sessions(),
        service_id=svc_id,
        subject_id=a["id"],
        purpose="zt_score",
        mode=LLMCallMode.FIXTURE,
    )
    assert c.post(f"/zt/assessments/{a['id']}/approve", headers=h).status_code == 200

    fin = c.post(f"/zt/services/{svc_id}/deliverables/finalize", headers=h)
    assert fin.status_code == 201, fin.text
    pdf, docx, sheet = _files(c, h, fin.json())
    assert FIXTURE in pdf
    assert FIXTURE in docx
    assert sheet[0][:2] == ["AI source", "fixture"]
