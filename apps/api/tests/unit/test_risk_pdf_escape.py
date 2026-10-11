"""#862: the Risk Register PDF prints its text as text, not as markup.

reportlab's `Paragraph` parses its input as markup. Unescaped, "ATT&CK" printed
as "ATT&CK;", a client named "R&D <Labs> Co" printed as "R&D; Co" (the tag
dropped in silence), and a name carrying "</b>" made the whole PDF export fail
with ValueError. `render_pdf` now escapes every string it hands `Paragraph`
(advisor, #736 6067815887: Risk only, the escape in `render_pdf` only). DOCX
and XLSX are plain text and must not gain entities.

Through the export endpoint and the downloaded bytes: the client reads the
file. The legal name is set through the admin route that creates a client, the
way a consultant would type it.
"""

from __future__ import annotations

import re

import pytest

from tests.unit.test_risk_export_unrated import _docx_text
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _entries_payload,
    _entry,
    _generate,
    _pdf_text,
    _seed_attack_and_zt,
    app_client,
)

pytestmark = pytest.mark.unit

#: Any HTML/XML entity, which is what a markup round trip leaves behind.
_ENTITY = re.compile(r"&\w+;")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _export(app_client, legal_name: str):  # noqa: F811
    """A client with this legal name, a generated register, and the export's
    PDF and DOCX bytes. Returns the export response too, so a refusal is read
    rather than assumed."""
    c, provider = app_client
    admin = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    bearer = admin.json()["tokens"]["access_token"]
    bh = {"Authorization": f"Bearer {bearer}"}
    created = c.post("/admin/clients", headers=bh, json={"legal_name": legal_name})
    assert created.status_code in (200, 201), created.text
    cid = created.json()["id"]
    _seed_attack_and_zt(c, bearer, cid)
    _generate(c, provider, bearer, cid, _entries_payload(_entry("R")))
    ex = c.post(f"/risk/clients/{cid}/register/export", headers=bh)
    assert ex.status_code == 200, ex.text
    dh = {**bh, "X-Client-Id": cid}
    files = {}
    for kind in ("pdf", "docx"):
        d = c.get(f"/artifacts/{ex.json()[f'{kind}_artifact_id']}/download", headers=dh)
        assert d.status_code == 200, d.text
        files[kind] = d.content
    return files


def test_the_scored_coverage_line_prints_atandck_without_an_entity(
    app_client,  # noqa: F811
) -> None:
    pdf = _flat(_pdf_text(_export(app_client, "Acme")["pdf"]))
    assert "ATT&CK coverage 1 of 697" in pdf  # the positive state first
    assert _ENTITY.search(pdf) is None, _ENTITY.findall(pdf)


def test_a_legal_name_with_ampersand_and_angle_brackets_prints_exactly(
    app_client,  # noqa: F811
) -> None:
    pdf = _flat(_pdf_text(_export(app_client, "R&D <Labs> Co")["pdf"]))
    assert "R&D <Labs> Co" in pdf
    assert _ENTITY.search(pdf) is None, _ENTITY.findall(pdf)


def test_a_legal_name_with_a_closing_tag_renders(app_client) -> None:  # noqa: F811
    """Unescaped, `Paragraph` raised ValueError and the export failed."""
    pdf = _flat(_pdf_text(_export(app_client, "Acme </b> Inc")["pdf"]))
    assert "Acme </b> Inc" in pdf


def test_the_docx_is_plain_text_and_gains_no_entity(app_client) -> None:  # noqa: F811
    """Parity: the escape is in `render_pdf` only, so the Word file, which
    shares `_summary_lines`, prints the same line with no `&amp;`."""
    files = _export(app_client, "R&D <Labs> Co")
    docx = _docx_text(files["docx"])
    assert "ATT&CK coverage 1 of 697" in docx
    assert "R&D <Labs> Co" in docx
    assert "&amp;" not in docx
