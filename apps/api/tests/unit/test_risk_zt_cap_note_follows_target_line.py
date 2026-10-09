"""The DoD cap note follows the Zero Trust target line in every Risk file (#944).

#861's target line and #915's cap note read as two baselines when other lines
sat between them. The advisor's ruling on #736 comment 6069566861, option 1:
the cap note renders immediately after the Zero Trust target line on every
surface. No new copy, only order.

Both sentences below are copied from their approved copy, never built from the
code: the target line's wording from #861 (`_target_lines`' approved form, the
intake target of stage 3 being the engagement target), the cap note from S3 at
#736 comment 6049667540. The world is `test_risk_zt_capped_target_disclosed`'s,
reused rather than rebuilt: an ATT&CK gap and a released DoD Zero Trust
assessment whose intake target of 3 the cap lowers for 15 capabilities.

A second world adds a released CISA Zero Trust assessment with an intake target
of 4, so the register holds two Zero Trust targets and each line names its
framework. The cap is DoD's, and `generate` records it per Zero Trust source,
so the note must follow the DoD line, not merely the last target line: the
two-framework case is what tells those apart. Its target lines are #861's
approved two-framework forms.

Each file is checked through the download a client receives. The positive state
is asserted first, so a missing sentence fails as missing and never passes as
"not adjacent" by accident.
"""

from __future__ import annotations

import pytest

from tests._risk_inputs import release
from tests.unit.test_risk_dashboard import (  # noqa: F401  (fixture)
    app_client,
)
from tests.unit.test_risk_zt_capped_target_disclosed import _files, _world

pytestmark = pytest.mark.unit

ZT_TARGET_LINE = (
    "Zero Trust findings are measured against target stage 3, the engagement "
    "target when this register was generated."
)
CAP_NOTE = (
    "In the DoD Zero Trust assessment, 15 capabilities have no DoD Advanced "
    "activities, so their target is Target (2): each is a finding only below "
    "Target. The Zero Trust deliverable names them."
)


def _published(c) -> tuple[str, str, list[str]]:
    cid, h, _client = _world(c, intake_stage=3, own_target=None)
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=h).status_code == 201
    pub = c.post(f"/risk/clients/{cid}/register/publish", headers=h)
    assert pub.status_code in (200, 201), pub.text
    return _files(c, h, pub.json())


def _assert_adjacent_in_text(text: str) -> None:
    assert ZT_TARGET_LINE in text
    assert CAP_NOTE in text
    # test-integrity: the needle is two whole approved sentences joined by the
    # one space the flattened text leaves between paragraphs; no unrelated text
    # can contain it by coincidence.
    assert (
        f"{ZT_TARGET_LINE} {CAP_NOTE}" in text
    ), "the cap note does not immediately follow the Zero Trust target line"


def test_pdf_puts_the_cap_note_right_after_the_zt_target_line(app_client) -> None:  # noqa: F811
    pdf, _docx, _summary = _published(app_client)
    _assert_adjacent_in_text(pdf)


def test_docx_puts_the_cap_note_right_after_the_zt_target_line(app_client) -> None:  # noqa: F811
    _pdf, docx, _summary = _published(app_client)
    _assert_adjacent_in_text(docx)


def test_xlsx_summary_puts_the_cap_note_in_the_row_after_the_zt_target_line(
    app_client,  # noqa: F811
) -> None:
    _pdf, _docx, summary = _published(app_client)
    assert summary.count(ZT_TARGET_LINE) == 1, summary
    assert summary.count(CAP_NOTE) == 1, summary
    at = summary.index(ZT_TARGET_LINE)
    assert summary[at + 1 : at + 2] == [CAP_NOTE], summary[at : at + 3]


CISA_LINE = (
    "Zero Trust (CISA ZTMM 2.0) findings are measured against target stage 4, "
    "the engagement target when this register was generated."
)
DOD_LINE = (
    "Zero Trust (DoD ZT Reference Architecture) findings are measured against "
    "target stage 3, the engagement target when this register was generated."
)


def _published_with_cisa_and_dod(c) -> tuple[str, str, list[str]]:
    from tests.unit.test_zt_dashboard import _attach_intake_target

    cid, h, _client = _world(c, intake_stage=3, own_target=None)
    bearer = h["Authorization"].removeprefix("Bearer ")
    zsvc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "ZT CISA"})
    assert zsvc.status_code in (200, 201), zsvc.text
    _attach_intake_target(zsvc.json()["id"], zt_stage=4)
    za = c.post(f"/zt/services/{zsvc.json()['id']}/assessments", headers=h)
    assert za.status_code in (200, 201), za.text
    r = c.post(f"/zt/assessments/{za.json()['id']}/approve", headers=h)
    assert r.status_code == 200, r.text
    release(c, bearer, cid, "zt", zsvc.json()["id"])
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=h).status_code == 201
    pub = c.post(f"/risk/clients/{cid}/register/publish", headers=h)
    assert pub.status_code in (200, 201), pub.text
    return _files(c, h, pub.json())


def _assert_after_the_dod_line_in_text(text: str) -> None:
    assert CISA_LINE in text
    assert DOD_LINE in text
    assert CAP_NOTE in text
    # test-integrity: the needle is two whole approved sentences joined by the
    # one space the flattened text leaves between paragraphs; no unrelated text
    # can contain it by coincidence.
    assert (
        f"{DOD_LINE} {CAP_NOTE}" in text
    ), "the cap note does not immediately follow the DoD Zero Trust target line"


def test_pdf_with_cisa_and_dod_puts_the_cap_note_right_after_the_dod_line(
    app_client,  # noqa: F811
) -> None:
    pdf, _docx, _summary = _published_with_cisa_and_dod(app_client)
    _assert_after_the_dod_line_in_text(pdf)


def test_docx_with_cisa_and_dod_puts_the_cap_note_right_after_the_dod_line(
    app_client,  # noqa: F811
) -> None:
    _pdf, docx, _summary = _published_with_cisa_and_dod(app_client)
    _assert_after_the_dod_line_in_text(docx)


def test_xlsx_with_cisa_and_dod_puts_the_cap_note_in_the_row_after_the_dod_line(
    app_client,  # noqa: F811
) -> None:
    _pdf, _docx, summary = _published_with_cisa_and_dod(app_client)
    assert summary.count(CISA_LINE) == 1, summary
    assert summary.count(DOD_LINE) == 1, summary
    assert summary.count(CAP_NOTE) == 1, summary
    at = summary.index(DOD_LINE)
    assert summary[at + 1 : at + 2] == [CAP_NOTE], summary[at : at + 3]
