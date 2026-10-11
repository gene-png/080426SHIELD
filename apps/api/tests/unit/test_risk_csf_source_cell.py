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


#: The record a generate wrote for CSF before #474 D' (`routes/risk.py` at
#: 44caf4a9^: `resolve_target_tier`'s target and source, joined by
#: `_targets_record` to the source's kind and framework).
_PRE_D_PRIME_CSF_TARGET = {
    "target": 4,
    "source": "client",
    "kind": "csf",
    "framework": None,
    "origin": "live_at_generate",
}


@pytest.mark.parametrize("record", ["pre_d_prime", "not_recorded"])
def test_a_register_not_measured_on_the_playbook_keeps_the_questionnaire_label(
    app_client, record: str  # noqa: F811
) -> None:
    """A register generated before D' read the questionnaire, and stays
    re-exportable. Its CSF Source cells must not say "CSF Playbook" beside a
    target line saying its findings were measured against the engagement tier:
    the label follows the register's RECORDED basis, not the code's shape.

    Built the way such a register exists: generated, then its provenance
    rewritten to what an older generate wrote. `pre_d_prime` is the CSF target
    record of `routes/risk.py` at 44caf4a9^ (no `csf_findings` key, which D'
    added); `not_recorded` is a register from before #474 (no `targets` key).
    Both are reachable: a stored register keeps the provenance it was
    generated with, and export re-reads it.
    """
    from sqlalchemy import select

    from app.models.risk_register import RiskRegister
    from tests.unit.test_risk_register import _session

    c, provider = app_client
    bearer, cid = _admin(c)
    technique, capability = _seed_attack_and_zt(c, bearer, cid)
    code = _seed_csf_playbook_at_level(c, bearer, cid, level=1)
    payload = _entries_payload(
        _entry("CSF risk", source="questionnaire_response", source_id=code),
        _entry("ZT risk", source="questionnaire_response", source_id=capability),
        _entry("ATT&CK risk", source="coverage_finding", source_id=technique),
    )
    _generate(c, provider, bearer, cid, payload)
    with _session() as s:
        reg = s.execute(select(RiskRegister)).scalar_one()
        prov = dict(reg.provenance)
        prov.pop("csf_findings")
        if record == "pre_d_prime":
            targets = dict(prov["targets"])
            (csf_key,) = [k for k, v in targets.items() if v["kind"] == "csf"]
            targets[csf_key] = dict(_PRE_D_PRIME_CSF_TARGET)
            prov["targets"] = targets
        else:
            prov.pop("targets")
        reg.provenance = prov
        s.commit()

    texts = _export_texts(c, bearer, cid)
    for fmt in ("pdf", "docx", "xlsx"):
        text = " ".join(texts[fmt].split())
        assert f"questionnaire_response:{code}" in text, fmt  # what must appear, first
        assert "CSF Playbook:" not in text, fmt
        assert f"questionnaire_response:{capability}" in text, fmt
        assert f"coverage_finding:{technique}" in text, fmt
        if record == "pre_d_prime":
            # The register reads as the state it is: measured on the tier.
            assert (
                "NIST CSF findings are measured against target tier 4, "
                "the engagement target when this register was generated." in text
            ), fmt
