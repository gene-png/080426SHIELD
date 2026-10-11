"""#646 through risk finalize; see test_ai_source_attack.py for the shape."""

from __future__ import annotations

import pytest

from tests._ai_mode import (
    docx_text,
    pdf_text,
    xlsx_ai_sheet,
)
from tests.unit.test_risk_dashboard import (  # noqa: F401  (fixture)
    _register,
    _seed_attack_and_zt,
    app_client,
)

pytestmark = pytest.mark.unit

#: The approved "not recorded" sentence, in the register's own word (the
#: coordinator's copy verdict, as Tech Debt says "capability list").
REGISTER = (
    "It is not recorded whether the AI suggestions in this register came from a live "
    "AI model or from offline test data."
)


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


def test_the_risk_register_states_it_is_not_recorded(app_client) -> None:  # noqa: F811
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    cid = client["user"]["client_id"]
    c.headers["X-Client-Id"] = cid
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    _seed_attack_and_zt(c, bearer, cid)
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=h).status_code == 201
    # #737: publish renders the files AND opens the client dashboard read below.
    ex = c.post(f"/risk/clients/{cid}/register/publish", headers=h)
    assert ex.status_code in (200, 201), ex.text
    pdf, docx, sheet = _files(c, h, ex.json())
    assert REGISTER in pdf
    assert REGISTER in docx
    assert sheet[0][:2] == ["AI source", "unknown"]

    dash = c.get(
        f"/clients/{cid}/risk/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    )
    assert dash.status_code == 200, dash.text
    assert dash.json()["ai_source"]["sentence"] == REGISTER
