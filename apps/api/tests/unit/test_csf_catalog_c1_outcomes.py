"""Seven CSF outcome strings are NIST CSWP 29's own text, read from the PDF (for #806, C1).

The #806 build plan (C1) found seven catalog outcomes that were condensed
paraphrases of the official text: GV.OC-02, GV.OC-03, GV.OC-04, GV.RM-04,
GV.RM-05, GV.RM-07 and ID.RA-02. The advisor ruled (#736 comment 6070708992)
that they must be CSWP 29 verbatim, held by a test that reads each from the
pinned PDF.

The expected text is extracted from `reference-docs/nist/NIST.CSWP.29.pdf`
(sha256-pinned in `test_csf_catalog_source.py`, re-checked here) at test time,
never typed from or read out of `app.csf.catalog`. It is compared with the
catalog the app SERVES (`GET /csf/catalog`), which is what the questionnaire
and every client surface read.

The comparison rules are the ruling's, each named below and nothing more:

* WHITESPACE: pypdf writes a printed line wrap as `" \\n"`, so whitespace runs
  collapse to one space.
* HYPHEN JOINS: a `-` followed by whitespace is joined only for a row listed in
  `_HYPHEN_JOINS` with the page that shows a hyphenated word. None of the seven
  wraps at a hyphen, so the list is empty, and a row that does is refused rather
  than guessed.
* APOSTROPHE: CSWP 29 prints U+2019; the catalog writes `'`. Mapped in the
  comparison. None of the seven contains one.
* EM DASH: kept. GV.OC-03 prints two U+2014, and the catalog carries them.
* PERIOD: CSWP 29 prints no closing period; every catalog outcome ends with
  one, so the catalog string is the PDF text plus `"."`.
"""

from __future__ import annotations

import hashlib
import io
import re

import pytest

from tests.unit.test_csf_catalog_source import _PDF, _PINNED_SHA256
from tests.unit.test_csf_dashboard import (  # noqa: F401  (fixture)
    _register,
    app_client,
)

pytestmark = pytest.mark.unit

#: The rows #806's C1 names (the build plan, #806 comment 5983938383). Scope,
#: not expected values: the text comes from the PDF.
_C1_CODES = ("GV.OC-02", "GV.OC-03", "GV.OC-04", "GV.RM-04", "GV.RM-05", "GV.RM-07", "ID.RA-02")

#: `code -> PDF page` for a row whose line wrap falls after a hyphen that the
#: rendered page shows belongs to the word. Empty: none of the seven wraps at a
#: hyphen (pages 21 and 24, rendered and read 2026-10-08).
_HYPHEN_JOINS: dict[str, int] = {}

#: The named apostrophe rule: U+2019 as printed, `'` as the catalog writes it.
_RIGHT_SINGLE_QUOTE = "’"


def _pdf_text() -> str:
    from pypdf import PdfReader

    data = _PDF.read_bytes()
    assert hashlib.sha256(data).hexdigest() == _PINNED_SHA256, "not the pinned CSWP 29"
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _pdf_outcome_raw(text: str, code: str) -> str:
    """The text after `<code>:` in Appendix A, up to the next bullet (`o `,
    `• `) or the running page header (`NIST CSWP 29`)."""
    head = r"\s*".join(re.escape(ch) for ch in code) + r"\s*:"
    starts = [m.end() for m in re.finditer(head, text)]
    assert len(starts) == 1, f"{code}: listed {len(starts)} times in the PDF"
    rest = text[starts[0] :]
    end = re.search(r"\n(?:o |• |NIST CSWP 29)", rest)
    assert end is not None, f"{code}: no end to its outcome in the PDF text"
    return rest[: end.start()]


def _normalised(code: str, raw: str) -> str:
    out = raw
    if code in _HYPHEN_JOINS:
        out = re.sub(r"-\s+", "-", out)
    else:
        assert not re.search(
            r"-\s+\S", out
        ), f"{code} wraps after a hyphen; render its page and list it in _HYPHEN_JOINS"
    out = re.sub(r"\s+", " ", out).strip()
    return out.replace(_RIGHT_SINGLE_QUOTE, "'")


@pytest.fixture(scope="module")
def pdf_outcomes() -> dict[str, str]:
    text = _pdf_text()
    return {code: _normalised(code, _pdf_outcome_raw(text, code)) for code in _C1_CODES}


def _served_outcomes(c) -> dict[str, str]:
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    r = c.get("/csf/catalog", headers={"Authorization": f"Bearer {bearer}"})
    assert r.status_code == 200, r.text
    return {
        s["code"]: s["outcome"]
        for f in r.json()["functions"]
        for cat in f["categories"]
        for s in cat["subcategories"]
    }


@pytest.mark.parametrize("code", _C1_CODES)
def test_the_served_outcome_is_cswp_29_verbatim(
    app_client, pdf_outcomes, code  # noqa: F811
) -> None:
    served = _served_outcomes(app_client)
    assert served[code] == pdf_outcomes[code] + "."


def test_gv_oc_03_keeps_both_em_dashes_as_printed(pdf_outcomes) -> None:
    """The EM DASH rule: a normaliser that dropped them would make the
    comparison above agree with a catalog that dropped them too."""
    assert pdf_outcomes["GV.OC-03"].count("—") == 2
    assert "cybersecurity — including privacy" in pdf_outcomes["GV.OC-03"]
