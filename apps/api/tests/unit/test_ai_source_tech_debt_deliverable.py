"""#646 through tech_debt finalize; see test_ai_source_attack.py for the shape."""

from __future__ import annotations

import pytest

from tests._ai_mode import (
    docx_text,
    pdf_text,
    xlsx_ai_sheet,
)
from tests.unit.test_tech_debt_routes import (  # noqa: F401  (fixture)
    _approve_list,
    _decide,
    _register,
    _seed_three_item_list,
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


def test_the_tech_debt_deliverable_states_the_mode_its_real_extraction_ran_in(
    app_client,  # noqa: F811
) -> None:
    c, _Sess, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    # A real extraction run, on the fixture provider: the run records
    # mode=fixture itself, and the file must say so.
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    _decide(c, bearer, item_ids)
    _approve_list(c, bearer, svc_id)
    latest = c.get(f"/tech-debt/services/{svc_id}/capability-lists/latest", headers=h).json()
    sentence = (
        "OFFLINE TEST DATA: every AI suggestion in this capability list came from "
        "built-in test data, not a live AI model. Treat AI-drafted values as "
        "placeholders, not analysis."
    )
    assert latest["ai_source"]["sentence"] == sentence

    fin = c.post(f"/tech-debt/services/{svc_id}/deliverables/finalize", headers=h)
    assert fin.status_code == 201, fin.text
    pdf, docx, sheet = _files(c, h, fin.json())
    assert sentence in pdf
    assert sentence in docx
    assert sheet[0][:2] == ["AI source", "fixture"]
