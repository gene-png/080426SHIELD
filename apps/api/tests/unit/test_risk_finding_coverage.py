"""#844, the advisor's two generate-side findings (cross-prompt check on #806).

1. Nothing checked that each finding got exactly one entry. The prompt asks for
   one per finding (G2), but an omitted or duplicated entry passed silently, and
   `valid_source_ids` is run-wide, so an entry citing another batch's finding
   was accepted too. The register now records, per run, which findings got no
   entry and which got several, and discloses both.
2. `source` was stored verbatim from the model, never checked against the
   `source_id` it travels with, into a `String(32)`. It is now DERIVED from the
   finding the kept `source_id` names; a model value that disagrees is counted
   and never stored.

Through generate, `latest` and export, never by writing rows.
"""

from __future__ import annotations

import pytest

from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _entries_payload,
    _entry,
    _generate,
    _generated_audit,
    _pdf_text,
    _seed_attack_and_zt,
    app_client,
)

pytestmark = pytest.mark.unit


def _seeded(app_client):  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, capability = _seed_attack_and_zt(c, bearer, cid)
    return c, provider, bearer, cid, technique, capability


def _latest(c, bearer, cid) -> dict:
    r = c.get(
        f"/risk/clients/{cid}/register/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_a_finding_with_no_entry_and_one_with_two_are_both_recorded(
    app_client,  # noqa: F811
) -> None:
    c, provider, bearer, cid, technique, capability = _seeded(app_client)
    _generate(
        c,
        provider,
        bearer,
        cid,
        _entries_payload(
            _entry("First", source_id=technique),
            _entry("Second", source_id=technique),
        ),
    )
    # Read back, so the assertion is on the PERSISTED record, not on what the
    # generate response happened to know.
    body = _latest(c, bearer, cid)
    assert body["findings_recorded"] is True
    assert body["findings_total"] == 2
    assert body["findings_without_entry"] == [capability]
    assert body["findings_with_several_entries"] == {technique: 2}


def test_one_entry_per_finding_records_a_clean_result_not_nothing(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid, technique, capability = _seeded(app_client)
    _generate(
        c,
        provider,
        bearer,
        cid,
        _entries_payload(
            _entry("ATT&CK", source_id=technique),
            _entry("ZT", source_id=capability, source="questionnaire_response"),
        ),
    )
    body = _latest(c, bearer, cid)
    assert body["findings_recorded"] is True
    assert body["findings_total"] == 2
    assert body["findings_without_entry"] == []
    assert body["findings_with_several_entries"] == {}


def test_an_entry_whose_source_id_was_dropped_leaves_its_finding_uncovered(
    app_client,  # noqa: F811
) -> None:
    """A dropped `source_id` names no finding, so it must not count toward one."""
    c, provider, bearer, cid, technique, capability = _seeded(app_client)
    _generate(
        c,
        provider,
        bearer,
        cid,
        _entries_payload(
            _entry("Real", source_id=technique),
            _entry("Invented", source_id="T0000"),
        ),
    )
    body = _latest(c, bearer, cid)
    assert body["findings_without_entry"] == [capability]


def test_a_register_without_the_record_says_nobody_counted(app_client) -> None:  # noqa: F811
    from sqlalchemy import select

    from app.models.risk_register import RiskRegister
    from tests.unit.test_risk_register import _session

    c, provider, bearer, cid, technique, _ = _seeded(app_client)
    _generate(c, provider, bearer, cid, _entries_payload(_entry("X", source_id=technique)))
    # The one hand-built state here, and it is a real one: every register
    # generated before this change has provenance without the key.
    with _session() as s:
        reg = s.execute(select(RiskRegister)).scalar_one()
        prov = dict(reg.provenance)
        prov.pop("finding_coverage")
        reg.provenance = prov
        s.commit()
    body = _latest(c, bearer, cid)
    assert body["findings_recorded"] is False
    assert body["findings_total"] is None
    assert body["findings_without_entry"] == []
    assert body["findings_with_several_entries"] == {}


def test_source_is_the_findings_not_the_models(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid, technique, capability = _seeded(app_client)
    body = _generate(
        c,
        provider,
        bearer,
        cid,
        _entries_payload(
            # Wrong pair: an ATT&CK technique labelled as a questionnaire.
            _entry("Mislabelled", source_id=technique, source="questionnaire_response"),
            # Longer than the String(32) column; stored verbatim before this.
            _entry("Long", source_id=capability, source="questionnaire_response_" + "x" * 30),
            # No source at all.
            '{"title": "Absent", "source_id": "' + capability + '", "likelihood": "low",'
            ' "impact": "minor"}',
        ),
    )
    by_title = {e["title"]: e for e in body["entries"]}
    assert by_title["Mislabelled"]["source"] == "coverage_finding"
    assert by_title["Long"]["source"] == "questionnaire_response"
    assert by_title["Absent"]["source"] == "questionnaire_response"
    audit = _generated_audit(c, bearer)
    assert audit["source_mismatches"] == {
        "count": 2,
        "values": ["questionnaire_response", "questionnaire_response_" + "x" * 9],
    }


def test_a_dropped_source_id_stores_no_source(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid, *_ = _seeded(app_client)
    body = _generate(
        c, provider, bearer, cid, _entries_payload(_entry("Orphan", source_id="T0000"))
    )
    [e] = body["entries"]
    assert e["source_id"] is None
    assert e["source"] is None
    assert _generated_audit(c, bearer)["source_mismatches"] == {"count": 0, "values": []}


def test_the_export_states_findings_without_an_entry(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid, technique, capability = _seeded(app_client)
    _generate(
        c,
        provider,
        bearer,
        cid,
        _entries_payload(
            _entry("First", source_id=technique),
            _entry("Second", source_id=technique),
        ),
    )
    bh = {"Authorization": f"Bearer {bearer}"}
    ex = c.post(f"/risk/clients/{cid}/register/export", headers=bh).json()
    pdf = c.get(f"/artifacts/{ex['pdf_artifact_id']}/download", headers={**bh, "X-Client-Id": cid})
    text = " ".join(_pdf_text(pdf.content).split())
    assert "2 findings went into this register; 1 has no entry and 1 has more than one." in text


def test_the_export_says_nothing_about_findings_when_each_has_one_entry(
    app_client,  # noqa: F811
) -> None:
    c, provider, bearer, cid, technique, capability = _seeded(app_client)
    _generate(
        c,
        provider,
        bearer,
        cid,
        _entries_payload(
            _entry("ATT&CK", source_id=technique),
            _entry("ZT", source_id=capability),
        ),
    )
    bh = {"Authorization": f"Bearer {bearer}"}
    ex = c.post(f"/risk/clients/{cid}/register/export", headers=bh).json()
    pdf = c.get(f"/artifacts/{ex['pdf_artifact_id']}/download", headers={**bh, "X-Client-Id": cid})
    assert "findings went into this register" not in " ".join(_pdf_text(pdf.content).split())
