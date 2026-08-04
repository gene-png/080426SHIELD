"""§15.5 filename convention for the CSF Playbook + Risk Register exports.

These two export sets historically bypassed `deliverable_filename()` and minted
raw `CSF_Playbook_v{n}*` / `Risk_Register_v{n}.*` names with no company/date.
Spec §15.5 requires EVERY download to carry
`{Company_Name}_{Service_Name}{MMDDYY}` (+ optional `_v{n}` re-release suffix).

This locks the helper additions that let those routes comply:
  * a `variant` param for the CSF Playbook's Executive/Full sub-documents, and
  * canonical service slugs for the Playbook and the Risk Register.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.tech_debt.filename import (
    SERVICE_SLUG_CSF_PLAYBOOK,
    SERVICE_SLUG_RISK_REGISTER,
    deliverable_filename,
)

DAY = date(2026, 7, 9)  # -> MMDDYY 070926


@pytest.mark.unit
def test_csf_playbook_slug_is_canonical() -> None:
    assert SERVICE_SLUG_CSF_PLAYBOOK == "CSF_Playbook"


@pytest.mark.unit
def test_risk_register_slug_is_canonical() -> None:
    assert SERVICE_SLUG_RISK_REGISTER == "Risk_Register"


@pytest.mark.unit
def test_csf_playbook_data_workbook_v1() -> None:
    # v1 carries no version suffix (spec §15.5).
    name = deliverable_filename(
        company="Atlas Defense Solutions",
        service_slug=SERVICE_SLUG_CSF_PLAYBOOK,
        extension="xlsx",
        day=DAY,
        version=1,
    )
    assert name == "Atlas_Defense_Solutions_CSF_Playbook070926.xlsx"


@pytest.mark.unit
def test_csf_playbook_executive_v2_variant_after_version() -> None:
    name = deliverable_filename(
        company="Atlas Defense Solutions",
        service_slug=SERVICE_SLUG_CSF_PLAYBOOK,
        extension="pdf",
        day=DAY,
        version=2,
        variant="Executive",
    )
    assert name == "Atlas_Defense_Solutions_CSF_Playbook070926_v2_Executive.pdf"


@pytest.mark.unit
def test_csf_playbook_full_v1_variant_no_version() -> None:
    name = deliverable_filename(
        company="Atlas Defense Solutions",
        service_slug=SERVICE_SLUG_CSF_PLAYBOOK,
        extension="docx",
        day=DAY,
        version=1,
        variant="Full",
    )
    assert name == "Atlas_Defense_Solutions_CSF_Playbook070926_Full.docx"


@pytest.mark.unit
def test_variant_is_slugified() -> None:
    name = deliverable_filename(
        company="X",
        service_slug=SERVICE_SLUG_CSF_PLAYBOOK,
        extension="pdf",
        day=DAY,
        variant="Exec Briefing!",
    )
    assert name == "X_CSF_Playbook070926_Exec_Briefing.pdf"


@pytest.mark.unit
def test_variant_none_leaves_name_unchanged() -> None:
    # Absent variant must not alter the pre-existing §15.5 output.
    name = deliverable_filename(
        company="X",
        service_slug=SERVICE_SLUG_RISK_REGISTER,
        extension="xlsx",
        day=DAY,
        version=3,
        variant=None,
    )
    assert name == "X_Risk_Register070926_v3.xlsx"


@pytest.mark.unit
def test_risk_register_missing_company_falls_back_to_unknown() -> None:
    name = deliverable_filename(
        company=None,
        service_slug=SERVICE_SLUG_RISK_REGISTER,
        extension="pdf",
        day=DAY,
    )
    assert name == "Unknown_Risk_Register070926.pdf"
