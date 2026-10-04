"""The ZT catalogs' source of record (#838): CISA ZTMM 2.0, as committed.

`reference-docs/cisa/` holds CISA's PDF and `scripts/extract_zt_sources.py`'s
extraction of it. The extraction is what the corrected catalog will be tested
against (#838 PR 2), so it must be the PDF's, not anything SHIELD wrote.

These checks run without the PDF tooling (the api image has no pdfplumber):

* the committed PDF is the pinned one, byte for byte (sha256), so the
  extraction cannot quietly refer to a different file;
* the extraction has CISA's structure and CISA's row names. The literals below
  are copied from the PDF itself (the Section 5.1-5.5 headings, the
  cross-cutting row names, and the 22 function names with their "New
  Function" / "Formerly ..." annotations), never from SHIELD's catalog, which
  is what is being corrected. The Optimal texts are not pinned here; they are
  checked against the PDF by the script's compare mode.

Re-deriving the extraction FROM the PDF is the script's own `cisa` mode
(without `--write`), run with pdfplumber; see the script's docstring.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter
from pathlib import Path

import pytest

from tests._paths import find_zt_source

pytestmark = pytest.mark.unit

#: A checkout's `reference-docs/cisa`, or the api container's read-only mount.
#: Never a skip: an unreadable source is a failure (#838).
_CISA = find_zt_source(Path(__file__).resolve(), "cisa") or Path("/nonexistent/reference-docs/cisa")
_PDF = _CISA / "zero_trust_maturity_model_v2_508.pdf"
_JSON = _CISA / "cisa_ztmm_v2_rows.json"

#: The pinned file, as downloaded from cisa.gov on 2026-10-04.
_PINNED_SHA256 = "4a95fdff55a64e2468b69af075b7f208176b88c751af92aefc3b7dacad26fdb4"

#: CISA ZTMM 2.0 Section 5.1-5.5 headings, in order.
_PILLARS = ("Identity", "Devices", "Networks", "Applications and Workloads", "Data")
#: Each pillar table's last three first-column cells, in order.
_CROSS_CUTTING = (
    "Visibility and Analytics Capability",
    "Automation and Orchestration Capability",
    "Governance Capability",
)
#: Tables 2-6's function rows, in order: (pillar, name, annotation). Copied
#: from the PDF (pp13-27) and checked against `pdftotext` there: each name is
#: followed by its parenthesised annotation, or by none.
_FUNCTIONS = (
    ("Identity", "Authentication", None),
    ("Identity", "Identity Stores", None),
    ("Identity", "Risk Assessments", None),
    ("Identity", "Access Management", "New Function"),
    ("Devices", "Policy Enforcement & Compliance Monitoring", "New Function"),
    ("Devices", "Asset & Supply Chain Risk Management", "New Function"),
    ("Devices", "Resource Access", "Formerly Data Access"),
    ("Devices", "Device Threat Protection", "New Function"),
    ("Networks", "Network Segmentation", None),
    ("Networks", "Network Traffic Management", "New Function"),
    ("Networks", "Traffic Encryption", "Formerly Encryption"),
    ("Networks", "Network Resilience", "New Function"),
    ("Applications and Workloads", "Application Access", "Formerly Access Authorization"),
    ("Applications and Workloads", "Application Threat Protections", "Formerly Threat Protections"),
    ("Applications and Workloads", "Accessible Applications", "Formerly Accessibility"),
    (
        "Applications and Workloads",
        "Secure Application Development and Deployment Workflow",
        "New Function",
    ),
    ("Applications and Workloads", "Application Security Testing", "Formerly Application Security"),
    ("Data", "Data Inventory Management", None),
    ("Data", "Data Categorization", "New Function"),
    ("Data", "Data Availability", "New Function"),
    ("Data", "Data Access", None),
    ("Data", "Data Encryption", None),
)
#: Rows per pillar table: its functions plus the three cross-cutting rows.
_ROWS_PER_PILLAR = {
    "Identity": 7,
    "Devices": 7,
    "Networks": 7,
    "Applications and Workloads": 8,
    "Data": 8,
}


def _extraction() -> dict:
    if not _JSON.is_file():
        pytest.fail(f"{_JSON} is not readable: the CISA extraction must be committed (#838).")
    return json.loads(_JSON.read_text(encoding="utf-8"))


def test_the_committed_pdf_is_the_pinned_one() -> None:
    if not _PDF.is_file():
        pytest.fail(f"{_PDF} is not readable: CISA's PDF must be committed (#838).")
    assert hashlib.sha256(_PDF.read_bytes()).hexdigest() == _PINNED_SHA256


def test_the_extraction_names_the_pdf_it_was_taken_from() -> None:
    source = _extraction()["source"]
    assert source["sha256"] == _PINNED_SHA256
    assert source["title"] == "Zero Trust Maturity Model"
    assert source["version"] == "2.0"
    assert source["date"] == "April 2023"
    assert source["bytes"] == _PDF.stat().st_size


def test_the_extraction_has_cisas_five_pillars_in_order() -> None:
    data = _extraction()
    assert [p["name"] for p in data["pillars"]] == list(_PILLARS)
    assert [r["pillar"] for r in data["rows"]] == sorted(
        (r["pillar"] for r in data["rows"]), key=_PILLARS.index
    ), "rows are grouped by pillar, in CISA's order"


def test_each_pillar_has_its_functions_then_its_three_cross_cutting_rows() -> None:
    rows = _extraction()["rows"]
    assert Counter(r["pillar"] for r in rows) == Counter(_ROWS_PER_PILLAR)
    assert len(rows) == 37
    for pillar in _PILLARS:
        own = [r for r in rows if r["pillar"] == pillar]
        assert [r["name"] for r in own[-3:]] == list(_CROSS_CUTTING), pillar
        assert {r["kind"] for r in own[:-3]} == {"function"}, pillar
        assert {r["kind"] for r in own[-3:]} == {"cross_cutting"}, pillar
    kinds = Counter(r["kind"] for r in rows)
    assert kinds == {"function": 22, "cross_cutting": 15}


def test_every_row_carries_cisa_text_and_nothing_invisible() -> None:
    data = _extraction()
    for r in data["rows"]:
        assert r["name"] and r["optimal"], r
        assert r["optimal"].startswith("Agency"), r["name"]  # "Agency …" / "Agency’s …"
        assert r["annotation"] in (None, "New Function") or r["annotation"].startswith(
            "Formerly "
        ), r["annotation"]
    for p in data["pillars"]:
        assert p["definition"], p["name"]
    text = json.dumps(data, ensure_ascii=False)
    invisible = [c for c in text if unicodedata.category(c) in ("Cc", "Cf") and c != "\n"]
    assert invisible == []


def test_the_function_rows_are_cisas_names_and_annotations() -> None:
    rows = [r for r in _extraction()["rows"] if r["kind"] == "function"]
    assert [(r["pillar"], r["name"], r["annotation"]) for r in rows] == list(_FUNCTIONS)


# --- the script's exit codes: could-not-read (2) is not DIFFERS (1) -----------


def _script_world(monkeypatch, tmp_path: Path, extract):
    """A checkout holding a stand-in PDF the hash check accepts, with
    `extract_cisa` replaced: the exit code alone is under test, and the api
    image has no pdfplumber."""
    import scripts.extract_zt_sources as ez

    cisa = tmp_path / "reference-docs" / "cisa"
    cisa.mkdir(parents=True)
    (cisa / ez.CISA_PDF_NAME).write_bytes(b"%PDF-stand-in")
    (cisa / ez.CISA_JSON_NAME).write_text('{"committed": true}\n', encoding="utf-8")
    monkeypatch.setattr(ez, "find_checkout", lambda start: tmp_path)
    monkeypatch.setattr(ez, "_sha256", lambda path: ez.CISA_SOURCE["sha256"])
    monkeypatch.setattr(ez, "extract_cisa", extract)
    return ez


def test_a_pdf_the_script_cannot_read_exits_2_not_1(monkeypatch, tmp_path: Path, capsys) -> None:
    def unreadable(path):
        from scripts.extract_zt_sources import SourceUnreadable

        raise SourceUnreadable("'Table 2: Identity Pillar' not found")

    ez = _script_world(monkeypatch, tmp_path, unreadable)
    assert ez.main(["cisa"]) == 2
    err = capsys.readouterr().err
    assert "COULD NOT READ the PDF" in err and "Table 2: Identity Pillar" in err
    assert "DIFFERS" not in err


def test_any_reader_failure_exits_2(monkeypatch, tmp_path: Path, capsys) -> None:
    def crashes(path):
        raise StopIteration

    ez = _script_world(monkeypatch, tmp_path, crashes)
    assert ez.main(["cisa"]) == 2
    assert "COULD NOT READ the PDF: StopIteration" in capsys.readouterr().err


def test_a_real_difference_still_exits_1(monkeypatch, tmp_path: Path, capsys) -> None:
    ez = _script_world(monkeypatch, tmp_path, lambda path: {"rows": []})
    assert ez.main(["cisa"]) == 1
    err = capsys.readouterr().err
    assert "DIFFERS from the committed extraction" in err
    assert "COULD NOT READ" not in err


def test_a_pdf_that_cannot_be_opened_exits_2(monkeypatch, tmp_path: Path, capsys) -> None:
    ez = _script_world(monkeypatch, tmp_path, lambda path: {"rows": []})

    def locked(path):
        raise PermissionError("locked")

    monkeypatch.setattr(ez, "_sha256", locked)
    assert ez.main(["cisa"]) == 2
    err = capsys.readouterr().err
    assert "COULD NOT READ the PDF: PermissionError" in err
    assert "DIFFERS" not in err


def test_a_committed_extraction_that_cannot_be_decoded_exits_2(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    ez = _script_world(monkeypatch, tmp_path, lambda path: {"rows": []})
    (tmp_path / "reference-docs" / "cisa" / ez.CISA_JSON_NAME).write_bytes(b"\xff\xfe\xfa")
    assert ez.main(["cisa"]) == 2
    err = capsys.readouterr().err
    assert "COULD NOT READ the committed extraction: UnicodeDecodeError" in err
    assert "DIFFERS" not in err


def test_a_missing_committed_extraction_says_so_and_exits_1(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    ez = _script_world(monkeypatch, tmp_path, lambda path: {"rows": []})
    (tmp_path / "reference-docs" / "cisa" / ez.CISA_JSON_NAME).unlink()
    assert ez.main(["cisa"]) == 1
    err = capsys.readouterr().err
    assert "NO COMMITTED EXTRACTION at" in err
    assert "DIFFERS" not in err
