"""#806: what the `mitre_map` run sends, and what it refuses, under the R3 prompt.

- M2: every batch carries `technique_details` {code: {name, not_preventable}}
  for its OWN codes only (C10), with the names surviving strict redaction.
- C4 (#736 comment 5984022081): the AI path refuses the four partial reasons
  the prompt forbids into `reason_codes_rejected`; a consultant keeps all seven.
- D1: the run's `llm_calls` rows say prompt_version "v2".
- Q5 (#736 comment 6053562002): the consultant definition of
  `prevention_limited` is the approved text.

Every assertion goes through an endpoint or the payload the provider received.
Expected values are literals from the rulings, the catalogue's own accessors, or
MITRE's published data, never the constants the route reads.
"""

from __future__ import annotations

import pytest

from app.ai.llm import LLMResponse
from tests._ai_runs import attack_run_ai
from tests.unit.test_attack_run_ai import (  # noqa: F401  (fixture)
    _SUGGESTED_RATIONALE,
    _one_row_run,
    _one_row_run_with_reason,
    _run_audit,
    app_client,
)

pytestmark = pytest.mark.unit

FORBIDDEN = [
    "reach_limited",
    "evasive_variant_uncovered",
    "periodic_not_continuous",
    "detection_weak",
]
OFFERED = ["prevention_limited", "recovery_absent", "missing_control_category"]


def _spy_payloads(c, TestSession, provider) -> list[dict]:
    """Run once, recording every batch's payload as the provider received it
    (after redaction)."""
    h, svc_id, _ = _one_row_run(c, TestSession, provider, "covered")
    sent: list[dict] = []

    def _spy(payload: dict) -> LLMResponse:
        sent.append(payload)
        return LLMResponse('{"techniques": []}')

    provider.register("mitre_map", _spy)
    attack_run_ai(c, svc_id, h)
    assert len(sent) > 1, "one batch cannot show that each batch gets only its own slice"
    return sent


def test_each_batch_carries_technique_details_for_its_own_codes_only(
    app_client,  # noqa: F811
) -> None:
    c, TestSession, provider = app_client
    sent = _spy_payloads(c, TestSession, provider)
    union: list[str] = []
    for payload in sent:
        assert sorted(payload["technique_details"]) == sorted(payload["technique_codes"])
        union.extend(payload["technique_details"])
    assert len(union) == len(set(union)), "a code's details went to more than one batch"


def test_technique_details_carry_the_catalogue_name_and_mitres_preventability(
    app_client,  # noqa: F811
) -> None:
    from app.attack.catalog import not_preventable_basis, technique_by_id

    c, TestSession, provider = app_client
    details = {
        code: d
        for payload in _spy_payloads(c, TestSession, provider)
        for code, d in payload["technique_details"].items()
    }
    # Literals from MITRE ATT&CK v19.2: T1595.001 maps only M1056
    # "Pre-compromise", T1070.004 maps no mitigation, and T1003.001 lists
    # preventive mitigations.
    assert details["T1595.001"] == {"name": "Scanning IP Blocks", "not_preventable": True}
    assert details["T1070.004"] == {"name": "File Deletion", "not_preventable": True}
    assert details["T1003.001"] == {"name": "LSASS Memory", "not_preventable": False}
    # Every name survived strict redaction on the way out, and every flag
    # agrees with the catalogue's public accessor.
    for code, d in details.items():
        assert d == {
            "name": technique_by_id(code).name,
            "not_preventable": not_preventable_basis(code) is not None,
        }, code


def test_every_catalogue_technique_name_survives_strict_redaction() -> None:
    """Build note 4: redact all 697 names in strict mode and diff. Measured
    when this was written: no name changed, with or without an org name."""
    from app.ai.redact import redact_payload
    from app.attack.catalog import TECHNIQUES

    names = {t.id: {"name": t.name} for t in TECHNIQUES}
    assert len(names) == 697
    for org in (None, "Acme"):
        out, counts = redact_payload(names, mode="strict", client_org_name=org)
        changed = {k: (names[k]["name"], out[k]["name"]) for k in names if out[k] != names[k]}
        assert changed == {}, changed
        assert counts == {}, counts


@pytest.mark.parametrize("reason", FORBIDDEN)
def test_an_ai_partial_with_a_forbidden_reason_is_refused_whole(
    app_client,  # noqa: F811
    reason,
) -> None:
    c, TestSession, provider = app_client
    h, svc_id, row_id, code = _one_row_run_with_reason(c, TestSession, provider, "partial", reason)
    before = c.patch(f"/attack/coverage/{row_id}", headers=h, json={"status": "gap"})
    assert before.status_code == 200, before.text

    result = attack_run_ai(c, svc_id, h)
    row = next(t for t in result["coverage"] if t["id"] == row_id)
    assert (row["status"], row["reason_code"]) == ("gap", None)
    assert not row["detection_tools"]
    assert row["rationale"] != _SUGGESTED_RATIONALE
    audit = _run_audit(TestSession)
    rejected = audit["reason_codes_rejected"]
    assert rejected, "a refused suggestion must be recorded, not silently dropped"
    assert all(
        e == {"technique_code": code, "status": "partial", "reason_code": reason} for e in rejected
    ), rejected
    assert audit["statuses_rejected"] == []


@pytest.mark.parametrize("reason", OFFERED)
def test_an_ai_partial_with_an_offered_reason_is_stored(app_client, reason) -> None:  # noqa: F811
    c, TestSession, provider = app_client
    h, svc_id, row_id, _ = _one_row_run_with_reason(c, TestSession, provider, "partial", reason)
    result = attack_run_ai(c, svc_id, h)
    row = next(t for t in result["coverage"] if t["id"] == row_id)
    assert (row["status"], row["reason_code"]) == ("partial", reason)
    assert _run_audit(TestSession)["reason_codes_rejected"] == []


@pytest.mark.parametrize("reason", FORBIDDEN)
def test_a_consultant_may_still_give_a_reason_the_ai_may_not(
    app_client,  # noqa: F811
    reason,
) -> None:
    c, TestSession, provider = app_client
    h, _svc_id, row_id, _ = _one_row_run_with_reason(c, TestSession, provider, "gap", None)
    r = c.patch(
        f"/attack/coverage/{row_id}", headers=h, json={"status": "partial", "reason_code": reason}
    )
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["reason_code"]) == ("partial", reason)


def test_the_runs_llm_calls_record_prompt_version_v2(app_client) -> None:  # noqa: F811
    from sqlalchemy import select

    from app.models.llm_call import LLMCall

    c, TestSession, provider = app_client
    _spy_payloads(c, TestSession, provider)
    with TestSession() as db:
        versions = (
            db.execute(select(LLMCall.prompt_version).where(LLMCall.purpose == "mitre_map"))
            .scalars()
            .all()
        )
    assert len(versions) > 1, versions
    assert set(versions) == {"v2"}


def test_the_consultant_definition_of_prevention_limited_is_the_approved_text(
    app_client,  # noqa: F811
) -> None:
    """Q5 (#736 comment 6053562002): the text proposed in 6053026654, approved."""
    c, TestSession, provider = app_client
    h, _svc_id, _row_id, _ = _one_row_run_with_reason(c, TestSession, provider, "gap", None)
    r = c.get("/attack/catalog", headers=h)
    assert r.status_code == 200, r.text
    (entry,) = [e for e in r.json()["reason_codes"] if e["code"] == "prevention_limited"]
    assert entry["definition"] == (
        "Detect is in place and Prevent is not, for a technique MITRE ATT&CK lists "
        "a preventive control for."
    )
