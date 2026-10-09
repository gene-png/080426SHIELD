"""#474 D': the files print a CSF entry's Source cell as "CSF Playbook:<code>".

Risk's CSF findings come from the Playbook, but the stored `source` token stays
`questionnaire_response`, the one E's approved prompt and parser use. The
advisor's ruling (#736 6087786886, item 5): change only what the export
prints for CSF. ZT and ATT&CK Source cells are unchanged.

Driven through generate and the three exported files.
"""

from __future__ import annotations

import pytest

from tests.unit.test_risk_per_service import _export_texts
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _entries_payload,
    _entry,
    _generate,
    _seed_attack_and_zt,
    _seed_csf_playbook_at_level,
    app_client,
)

pytestmark = pytest.mark.unit


def test_each_file_prints_the_csf_source_as_the_playbook(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, capability = _seed_attack_and_zt(c, bearer, cid)
    code = _seed_csf_playbook_at_level(c, bearer, cid, level=1)
    payload = _entries_payload(
        _entry("CSF risk", source="questionnaire_response", source_id=code),
        _entry("ZT risk", source="questionnaire_response", source_id=capability),
        _entry("ATT&CK risk", source="coverage_finding", source_id=technique),
    )
    body = _generate(c, provider, bearer, cid, payload)
    stored = {e["title"]: (e["source"], e["source_id"]) for e in body["entries"]}
    # The stored token is unchanged: only the files print it differently.
    assert stored["CSF risk"] == ("questionnaire_response", code), stored

    texts = _export_texts(c, bearer, cid)
    for fmt in ("pdf", "docx", "xlsx"):
        text = " ".join(texts[fmt].split())
        assert f"CSF Playbook:{code}" in text, fmt  # what must appear, first
        assert f"questionnaire_response:{code}" not in text, fmt
        assert f"questionnaire_response:{capability}" in text, fmt
        assert f"coverage_finding:{technique}" in text, fmt
