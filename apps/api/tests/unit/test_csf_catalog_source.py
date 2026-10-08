"""The CSF catalog IS NIST CSWP 29's Core, held to the PDF itself (for #852).

Two anchors to the document:

* **The PDF.** `reference-docs/nist/NIST.CSWP.29.pdf` (NIST CSWP 29, The NIST
  Cybersecurity Framework (CSF) 2.0, February 2024), supplied by Gene and
  pinned here by sha256.
* **The subcategory code set, read FROM the PDF.** Appendix A lists every
  subcategory as `<code>: <outcome>`. The expected set is extracted from the
  PDF's text at test time (pypdf, the test-only reader every other PDF test
  here uses), never typed from or read out of `app.csf.catalog`. It is
  compared with the two things the app does with the catalog: the catalog it
  SERVES (`GET /csf/catalog`) and the answer rows it SEEDS into a new
  assessment (`provisioning.py`, through `POST /csf/services/{id}/assessments`).

pypdf sometimes splits a code across a space ("R C.CO -03"), so the pattern
tolerates whitespace between characters and the match is joined back. What is
pinned to the PDF here: the file's hash and every subcategory code. The
outcome text and short names are not (`test_csf_catalog_cswp29.py` holds
RC.CO-04's outcome as a literal).
"""

from __future__ import annotations

import hashlib
import io
import re
import uuid
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.csf_assessment import CsfAnswer
from tests._ai_mode import env_sessions
from tests._paths import find_zt_source
from tests.unit.test_csf_dashboard import (  # noqa: F401  (fixture)
    _register,
    app_client,
)

pytestmark = pytest.mark.unit

# `find_zt_source` is the reference-docs finder: a checkout's
# `reference-docs/<name>`, else the api container's read-only mount
# `/zt-sources/<name>` (docker-compose.yml mounts `reference-docs/nist` there).
_NIST = find_zt_source(Path(__file__).resolve(), "nist") or Path("/nonexistent/reference-docs/nist")
_PDF = _NIST / "NIST.CSWP.29.pdf"

#: The pinned file, supplied by Gene (advisor/nist-cswp29, 71e401c2).
#: Computed with `sha256sum` on 2026-10-08.
_PINNED_SHA256 = "3c31f46fee98cac0c4323453e5109291a213b4de7fef8c058af9bf67f717433c"

#: `<function>.<category>-<nn>:` as Appendix A writes each subcategory, with
#: any whitespace pypdf inserts between characters allowed.
_CORE_ENTRY = re.compile(
    r"(?<![A-Z])(G\s*V|I\s*D|P\s*R|D\s*E|R\s*S|R\s*C)\s*\.\s*([A-Z]\s*[A-Z])\s*-\s*(\d\s*\d)\s*:"
)


def _pdf_bytes() -> bytes:
    if not _PDF.is_file():
        pytest.fail(f"{_PDF} is not readable: NIST CSWP 29 must be committed (#852).")
    return _PDF.read_bytes()


def _pdf_codes() -> list[str]:
    """Every subcategory code Appendix A lists, in the PDF's order."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(_pdf_bytes()))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return [
        re.sub(r"\s+", "", f"{m.group(1)}.{m.group(2)}-{m.group(3)}")
        for m in _CORE_ENTRY.finditer(text)
    ]


def test_the_committed_pdf_is_the_pinned_one() -> None:
    assert hashlib.sha256(_pdf_bytes()).hexdigest() == _PINNED_SHA256


def test_the_pdf_lists_each_subcategory_once() -> None:
    codes = _pdf_codes()
    assert "GV.OC-01" in codes and "RC.CO-04" in codes, codes[:5]
    assert [c for c, n in Counter(codes).items() if n > 1] == []


def test_the_served_catalog_is_the_pdfs_subcategories(app_client) -> None:  # noqa: F811
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    r = c.get("/csf/catalog", headers={"Authorization": f"Bearer {bearer}"})
    assert r.status_code == 200, r.text
    served = {
        s["code"]
        for f in r.json()["functions"]
        for cat in f["categories"]
        for s in cat["subcategories"]
    }
    pdf = set(_pdf_codes())
    assert sorted(pdf - served) == [], "in CSWP 29, missing from the served catalog"
    assert sorted(served - pdf) == [], "served, but not a CSWP 29 subcategory"


def test_a_new_assessment_seeds_exactly_the_pdfs_subcategories(app_client) -> None:  # noqa: F811
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    r = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    assert r.status_code in (200, 201), r.text
    a = c.post(f"/csf/services/{r.json()['id']}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    with env_sessions()() as db:
        seeded = list(
            db.scalars(
                select(CsfAnswer.subcategory_code).where(
                    CsfAnswer.assessment_id == uuid.UUID(a.json()["id"])
                )
            )
        )
    pdf = set(_pdf_codes())
    assert sorted(pdf - set(seeded)) == [], "in CSWP 29, not seeded"
    assert sorted(set(seeded) - pdf) == [], "seeded, but not a CSWP 29 subcategory"
    assert len(seeded) == len(set(seeded))


def test_de_ae_01_and_05_are_csf_1_1_codes_cswp_29_does_not_list() -> None:
    """CSF 1.1's DE.AE-01 and DE.AE-05 are not CSF 2.0 subcategories: CSWP 29's
    Adverse Event Analysis lists DE.AE-02, -03, -04, -06, -07 and -08 only.
    The catalog does not have them either (the served-catalog test above holds
    it to the PDF's set); `_IG_METADATA` still carries both as keys no
    catalog code reaches, which is outside this test."""
    de_ae = [c for c in _pdf_codes() if c.startswith("DE.AE-")]
    assert "DE.AE-02" in de_ae, de_ae  # the reader found the category at all
    assert "DE.AE-01" not in de_ae
    assert "DE.AE-05" not in de_ae
