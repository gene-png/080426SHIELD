"""#646 through csf finalize; see test_ai_source_attack.py for the shape."""

from __future__ import annotations

import pytest

from app.models.llm_call import LLMCallMode
from tests._ai_mode import (
    FIXTURE,
    docx_text,
    env_sessions,
    mixed,
    pdf_text,
    seed_run,
    xlsx_ai_sheet,
)
from tests.unit.test_csf_deliverable_routes import (  # noqa: F401  (fixture)
    _register,
    _seed_approved,
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


def test_the_csf_deliverable_states_its_ai_source(app_client) -> None:  # noqa: F811
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id, assessment_id = _seed_approved(c, bearer)
    Sess = env_sessions()
    seed_run(
        Sess,
        service_id=svc_id,
        subject_id=assessment_id,
        purpose="csf_score",
        mode=LLMCallMode.FIXTURE,
    )
    seed_run(
        Sess,
        service_id=svc_id,
        subject_id=assessment_id,
        purpose="csf_score",
        mode=LLMCallMode.LIVE,
    )

    fin = c.post(f"/csf/services/{svc_id}/deliverables/finalize", headers=h)
    assert fin.status_code == 201, fin.text
    pdf, docx, sheet = _files(c, h, fin.json())
    sentence = mixed(1, 2)
    assert sentence in pdf
    assert sentence in docx
    assert sheet[0][:2] == ["AI source", "mixed"]
    assert sheet[1][0] == sentence
    assert sheet[2:4] == [["Live AI runs", 1], ["Offline test-data runs", 1]]


def test_every_file_of_the_playbook_export_states_its_ai_source(app_client) -> None:  # noqa: F811
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()[
        "id"
    ]
    a = c.post(f"/csf/services/{svc_id}/assessments", headers=h).json()
    seeded = c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})
    assert seeded.status_code in (200, 201), seeded.text
    seed_run(
        env_sessions(),
        service_id=svc_id,
        subject_id=a["id"],
        purpose="csf_score",
        mode=LLMCallMode.FIXTURE,
    )

    ex = c.post(f"/csf/services/{svc_id}/playbook/export", headers=h)
    assert ex.status_code == 200, ex.text
    files = ex.json()["artifacts"]
    assert len(files) == 5
    for f in files:
        raw = c.get(f"/artifacts/{f['artifact_id']}/download", headers=h).content
        if f["kind"] == "xlsx":
            # Under the Playbook's approval banner (#294), like its every sheet.
            rows = xlsx_ai_sheet(raw)
            assert rows[0][0].startswith("NOT APPROVED"), rows[0]
            assert rows[1][:2] == ["AI source", "fixture"], rows[1]
            assert rows[2][0] == FIXTURE, f["kind"]
        elif f["kind"].endswith("pdf"):
            assert FIXTURE in pdf_text(raw), f["kind"]
        else:
            assert FIXTURE in docx_text(raw), f["kind"]
