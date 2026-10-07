"""The DoD catalog IS the 2025 DoD CIO roadmap (#839), held to its own text.

Two independent anchors, so neither the extraction nor the catalog can drift
from the PDF without a red test:

* **The PDF and the extraction.** `ZT-CapabilitiesActivities.pdf` (DoD CIO,
  2025, 25-T-1465) is pinned here by sha256, and the committed extraction
  `dod_zt_2025_rows.json` must record that same hash and size.
* **The 45 capabilities, as literals.** `_PDF_CAPABILITIES` was typed from the
  PDF's own text, read with `pdftotext -raw` (poppler) rather than pdfplumber,
  which is the extraction's engine. Wrapped cells are joined with one space.
  They are compared against the catalog the app SERVES (`GET /zt/catalog`), not
  against the JSON.

Then the rest of the catalog (pillars, descriptions, every activity) is
compared with the extraction, never with `app.zt.catalog`'s own constants.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.zt.catalog import capabilities, pillars
from app.zt.maturity import ZtFrameworkCode
from tests._paths import find_zt_source
from tests.unit.test_zt_acceptance import (  # noqa: F401  (fixture)
    _register,
    app_client,
)

pytestmark = pytest.mark.unit

_DOD = find_zt_source(Path(__file__).resolve(), "dod") or Path("/nonexistent/reference-docs/dod")
_FW = ZtFrameworkCode.DOD_ZTRA
_PDF = _DOD / "ZT-CapabilitiesActivities.pdf"

#: The pinned file, as downloaded from dodcio.defense.gov (#839 comment
#: 5983310584). Computed with `sha256sum` on 2026-10-07.
_PINNED_SHA256 = "756abc470d22dfddf399bcf3264b23c23fecedd8ac32b98b4f3461c96ed43be1"

#: (code, name) for every capability, in the PDF's order. Typed from
#: `pdftotext -raw ZT-CapabilitiesActivities.pdf` ("ID #" / "Capability"
#: columns). The code is DOD.<pillar>.<minor number>, so 4.6 is DAT.06.
_PDF_CAPABILITIES = (
    ("DOD.USR.01", "User Inventory"),
    ("DOD.USR.02", "Conditional User Access"),
    ("DOD.USR.03", "Multi-Factor Authentication (MFA)"),
    ("DOD.USR.04", "Privileged Access Management (PAM)"),
    ("DOD.USR.05", "Identity Federation & User Credentialing"),
    ("DOD.USR.06", "Behavioral, Contextual ID, and Biometrics"),
    ("DOD.USR.07", "Least Privileged Access"),
    ("DOD.USR.08", "Continuous Authentication"),
    ("DOD.USR.09", "Integrated ICAM Platform"),
    ("DOD.DEV.01", "Device Inventory"),
    ("DOD.DEV.02", "Device Detection and Compliance"),
    ("DOD.DEV.03", "Device Authorization w/ Real Time Inspection"),
    ("DOD.DEV.04", "Remote Access"),
    ("DOD.DEV.05", "Partially & Fully Automated Asset, Vulnerability and Patch Management"),
    ("DOD.DEV.06", "Unified Endpoint Management (UEM) & Mobile Device Management (MDM)"),
    ("DOD.DEV.07", "Endpoint & Extended Detection & Response (EDR & XDR)"),
    ("DOD.APP.01", "Application Inventory"),
    ("DOD.APP.02", "Secure Software Development & Integration"),
    ("DOD.APP.03", "Software Risk Management"),
    ("DOD.APP.04", "Resource Authorization & Integration"),
    ("DOD.APP.05", "Continuous Monitoring and Ongoing Authorizations"),
    ("DOD.DAT.01", "Data Catalog Risk Alignment"),
    ("DOD.DAT.02", "DoD Enterprise Data Governance"),
    ("DOD.DAT.03", "Data Labeling and Tagging"),
    ("DOD.DAT.04", "Data Monitoring and Sensing"),
    ("DOD.DAT.05", "Data Encryption & Rights Management"),
    ("DOD.DAT.06", "Data Loss Prevention (DLP)"),
    ("DOD.DAT.07", "Data Access Control"),
    ("DOD.NET.01", "Data Flow Mapping"),
    ("DOD.NET.02", "Software Defined Networking (SDN)"),
    ("DOD.NET.03", "Macro Segmentation"),
    ("DOD.NET.04", "Micro Segmentation"),
    ("DOD.AUT.01", "Policy Decision Point (PDP) & Policy Orchestration"),
    ("DOD.AUT.02", "Critical Process Automation"),
    ("DOD.AUT.03", "Machine Learning"),
    ("DOD.AUT.04", "Artificial Intelligence"),
    ("DOD.AUT.05", "Security Orchestration, Automation & Response (SOAR)"),
    ("DOD.AUT.06", "API Standardization"),
    ("DOD.AUT.07", "Security Operations Center (SOC) & Incident Response (IR)"),
    ("DOD.VIS.01", "Log All Traffic (Network, Data, Apps, Users)"),
    ("DOD.VIS.02", "Security Information and Event Management (SIEM)"),
    ("DOD.VIS.03", "Common Security and Risk Analytics"),
    ("DOD.VIS.04", "User and Entity Behavior Analytics"),
    ("DOD.VIS.05", "Threat Intelligence Integration"),
    ("DOD.VIS.06", "Automated Dynamic Policies"),
)


def test_the_committed_pdf_is_the_pinned_one() -> None:
    if not _PDF.is_file():
        pytest.fail(f"{_PDF} is not readable: DoD's PDF must be committed (#839).")
    assert hashlib.sha256(_PDF.read_bytes()).hexdigest() == _PINNED_SHA256


def test_the_extraction_names_the_pdf_it_was_taken_from() -> None:
    source = _source()["source"]
    assert source["sha256"] == _PINNED_SHA256
    assert source["marking"] == "25-T-1465"
    assert source["bytes"] == _PDF.stat().st_size


def test_the_served_catalog_is_the_pdfs_capabilities(app_client) -> None:  # noqa: F811
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    r = c.get("/zt/catalog?framework=dod_ztra", headers={"Authorization": f"Bearer {bearer}"})
    assert r.status_code == 200, r.text
    served = tuple(
        (cap["code"], cap["name"]) for p in r.json()["pillars"] for cap in p["capabilities"]
    )
    assert len(_PDF_CAPABILITIES) == 45  # the literal list itself, typed in full
    assert served == _PDF_CAPABILITIES


def _source() -> dict:
    path = _DOD / "dod_zt_2025_rows.json"
    if not path.is_file():
        pytest.fail(f"{path} is not readable: the DoD extraction is the catalog's spec (#839).")
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_pillars_are_dods_seven_in_dods_order() -> None:
    src = _source()["capabilities"]
    in_order = list(dict.fromkeys((c["pillar_number"], c["pillar"]) for c in src))
    assert [p.name for p in pillars(_FW)] == [name for _, name in in_order]


def test_every_capability_is_dods_in_dods_order() -> None:
    src = _source()["capabilities"]
    by_code = {p.code: p.name for p in pillars(_FW)}
    got = capabilities(_FW)
    assert len(got) == len(src) == 45
    for cap, row in zip(got, src, strict=True):
        assert cap.dod_number == row["id"], cap.code
        assert cap.code.endswith(f".{int(row['id'].split('.')[1]):02d}"), cap.code
        assert cap.name == row["name"], cap.code
        assert by_code[cap.pillar_code] == row["pillar"], cap.code
        assert cap.outcome == f"DoD: {row['description']}", cap.code


def test_every_activity_is_dods_under_its_capability() -> None:
    src = _source()["activities"]
    got = [(cap, a) for cap in capabilities(_FW) for a in cap.activities]
    assert len(got) == len(src) == 152
    for (cap, act), row in zip(got, src, strict=True):
        assert act.id == row["id"]
        assert act.id.startswith(f"{cap.dod_number}."), (cap.code, act.id)
        assert act.name == row["name"], act.id
        assert act.level == row["level"], act.id
        expected = row["description"]
        if row["outcomes"]:
            expected += " Outcomes: " + row["outcomes"]
        if row["end_state"]:
            expected += " End state: " + row["end_state"]
        assert act.description == expected, act.id


def test_activities_are_sorted_by_id_within_each_capability() -> None:
    for cap in capabilities(_FW):
        ids = [tuple(int(x) for x in a.id.split(".")) for a in cap.activities]
        assert ids == sorted(ids), cap.code
        assert ids, f"{cap.code} has no activities"


def test_cisa_rows_carry_no_activities_and_no_dod_number() -> None:
    for cap in capabilities(ZtFrameworkCode.CISA_ZTMM_2_0):
        assert cap.activities == ()
        assert cap.dod_number is None
