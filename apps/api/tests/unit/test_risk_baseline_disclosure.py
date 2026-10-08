"""#474, the minimum: a register says which target its findings were measured
against.

`_gather_findings` returned `target_sources`, and it reached only the audit
row: no schema, no screen, no export. So the baseline a register was computed
against was invisible to the client and to the consultant, and a register
measured against a different target than the released CSF or ZT report had
nothing on it that would let anyone notice.

It is now persisted with the register (provenance `targets`, a generate-time
fact) and reaches the admin response, the client dashboard and the three
exports. Three states: recorded, recorded with the default, and not recorded
(a register generated before this), which the export states rather than
leaving silent.
"""

from __future__ import annotations

import pytest

from tests.unit.test_risk_per_service import _both_frameworks, _export_texts
from tests.unit.test_risk_per_service import _generate as _generate_per_finding
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _entries_payload,
    _entry,
    _generate,
    _pdf_text,
    _seed_attack_and_zt,
    _seed_csf_answer_at_tier,
    _session,
    _set_csf_target,
    app_client,
)

pytestmark = pytest.mark.unit


def _latest(c, bearer: str, cid: str) -> dict:
    r = c.get(
        f"/risk/clients/{cid}/register/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _export_pdf_text(c, bearer: str, cid: str) -> str:
    bh = {"Authorization": f"Bearer {bearer}"}
    ex = c.post(f"/risk/clients/{cid}/register/export", headers=bh)
    assert ex.status_code == 200, ex.text
    pdf = c.get(
        f"/artifacts/{ex.json()['pdf_artifact_id']}/download",
        headers={**bh, "X-Client-Id": cid},
    )
    return " ".join(_pdf_text(pdf.content).split())


def _world(app_client, *, csf_target: int | None = None):  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    if csf_target is not None:
        _seed_csf_answer_at_tier(c, bearer, cid, tier=1)
        _set_csf_target(cid, csf_target)
    _generate(c, provider, bearer, cid, _entries_payload(_entry("R")))
    return c, bearer, cid


def test_the_register_records_each_services_target(app_client) -> None:  # noqa: F811
    c, bearer, cid = _world(app_client, csf_target=4)
    body = _latest(c, bearer, cid)
    assert body["targets_recorded"] is True
    by_service = {t["service"]: t for t in body["targets"]}
    assert by_service["csf"] == {
        "service": "csf",
        "target": 4,
        "source": "client",
        "origin": "live_at_generate",
    }
    # No ZT target was set, so ZT used the engine default and says so.
    assert by_service["zt"]["source"] == "default"
    assert by_service["zt"]["origin"] == "live_at_generate"


def test_the_export_states_the_baseline(app_client) -> None:  # noqa: F811
    c, bearer, cid = _world(app_client, csf_target=4)
    zt = {t["service"]: t for t in _latest(c, bearer, cid)["targets"]}["zt"]
    text = _export_pdf_text(c, bearer, cid)
    assert (
        "NIST CSF findings are measured against target tier 4, the engagement "
        "target when this register was generated." in text
    )
    assert (
        f"Zero Trust findings are measured against target stage {zt['target']}, "
        "SHIELD's default: no engagement target was set." in text
    )


def test_a_register_without_the_record_says_so(app_client) -> None:  # noqa: F811
    from sqlalchemy import select

    from app.models.risk_register import RiskRegister

    c, bearer, cid = _world(app_client)
    with _session() as s:
        reg = s.execute(select(RiskRegister)).scalar_one()
        prov = dict(reg.provenance)
        prov.pop("targets")
        reg.provenance = prov
        s.commit()
    body = _latest(c, bearer, cid)
    assert body["targets_recorded"] is False
    assert body["targets"] == []
    text = _export_pdf_text(c, bearer, cid)
    assert (
        "The targets these findings were measured against were not recorded for "
        "this register." in text
    )
    assert "findings are measured against target" not in text


def _client_dashboard(c, bearer: str, cid: str) -> dict:
    """The client's screen, read as a client user, after publication."""
    ah = {"Authorization": f"Bearer {bearer}"}
    c.post(f"/admin/clients/{cid}/domains", headers=ah, json={"domain": "acme.example"})
    user = c.post(
        "/auth/register",
        json={
            "email": "user@acme.example",
            "password": "correct horse battery staple!",
            "display_name": "U",
        },
    )
    ch = {"Authorization": f"Bearer {user.json()['tokens']['access_token']}", "X-Client-Id": cid}
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.models.risk_register import RiskRegister

    # Released the way `seed_demo.py` releases one: this PR is stacked under
    # #737's publish route and must not depend on it.
    with _session() as s:
        reg = s.execute(select(RiskRegister)).scalar_one()
        reg.finalized_at = datetime.now(UTC)
        s.commit()
    r = c.get(f"/clients/{cid}/risk/dashboard", headers=ch)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_client_dashboard_carries_the_baseline(app_client) -> None:  # noqa: F811
    """The client's screen, read as a client user, after publication."""
    c, bearer, cid = _world(app_client, csf_target=4)
    body = _client_dashboard(c, bearer, cid)
    assert body["targets_recorded"] is True
    assert {t["service"]: t["target"] for t in body["targets"]}["csf"] == 4


# ---------------------------------------------------------------------------
# Two Zero Trust services (#876): the scope keys are "zt:<framework>", and the
# target line names each framework the way the scored-coverage line already
# does (`scope_label`), with the ZT unit. It printed the raw key and "level".
# ---------------------------------------------------------------------------

_ZT_LABELS = {
    "zt:cisa_ztmm_2_0": "Zero Trust (CISA ZTMM 2.0)",
    "zt:dod_ztra": "Zero Trust (DoD ZT Reference Architecture)",
}


def _two_zt_world(app_client):  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    _both_frameworks(c, bearer, cid)
    r = _generate_per_finding(c, provider, bearer, cid, [])
    assert r.status_code == 201, r.text
    return c, bearer, cid


def test_two_zero_trust_services_each_name_their_framework_in_every_file(
    app_client,  # noqa: F811
) -> None:
    c, bearer, cid = _two_zt_world(app_client)
    targets = {t["service"]: t["target"] for t in _latest(c, bearer, cid)["targets"]}
    assert set(targets) == set(_ZT_LABELS), targets  # the positive state first
    texts = _export_texts(c, bearer, cid)
    # All three files: the XLSX summary sheet prints `_summary_lines` too.
    for fmt in ("pdf", "docx", "xlsx"):
        text = " ".join(texts[fmt].split())
        for key, label in _ZT_LABELS.items():
            assert f"{label} findings are measured against target stage {targets[key]}," in text, (
                fmt,
                key,
                text,
            )
        assert "zt:" not in text, fmt
        assert "against target level" not in text, fmt


def test_two_zero_trust_services_reach_the_client_dashboard_keyed_by_framework(
    app_client,  # noqa: F811
) -> None:
    """The dashboard carries the scope keys; the web formatter labels them
    (`lib/risk/baseline.test.ts` uses these exact keys)."""
    c, bearer, cid = _two_zt_world(app_client)
    body = _client_dashboard(c, bearer, cid)
    assert body["targets_recorded"] is True
    assert sorted(t["service"] for t in body["targets"]) == sorted(_ZT_LABELS)


# ---------------------------------------------------------------------------
# The third state: no CSF or ZT input, which `generate` would record as
# `"targets": {}` (`targets_record` is built from `target_sources`, which has an
# entry per CSF and ZT source). That is a record of no targets, not a missing
# one, and it read as unreadable: an error logged on every read and "not
# recorded" printed.
#
# NO CURRENT WRITER PRODUCES IT. Generate unlocks only with a CSF or ZT
# assessment, and synthesis reads drafts too, so every register that can be
# generated has at least one target (pinned below). This is a RATCHET for the
# day that changes: an unlock on ATT&CK alone, or a CSF/ZT input the gate
# counts and synthesis skips. So the state is written onto a real register.
# ---------------------------------------------------------------------------

_NOT_RECORDED = (
    "The targets these findings were measured against were not recorded for this register."
)


def _seed_attack_only(c, bearer: str, cid: str) -> None:
    """The ATT&CK half of `_seed_attack_and_zt`: one gap, approved."""
    from tests._attack_rows import first_standalone

    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    asvc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    assert asvc.status_code in (200, 201), asvc.text
    a = c.post(f"/attack/services/{asvc.json()['id']}/assessments", headers=h)
    cov = first_standalone(a.json()["coverage"])
    r = c.patch(f"/attack/coverage/{cov['id']}", headers=h, json={"status": "gap"})
    assert r.status_code == 200, r.text
    ar = c.post(f"/attack/assessments/{a.json()['id']}/approve", headers=h)
    assert ar.status_code == 200, ar.text


def test_attack_alone_cannot_generate_which_is_why_no_register_has_empty_targets(
    app_client,  # noqa: F811
) -> None:
    c, _provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_only(c, bearer, cid)
    r = c.post(
        f"/risk/clients/{cid}/register/generate",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 409, r.text
    assert "a CSF or Zero Trust assessment" in r.text


def _with_empty_targets(cid: str) -> None:
    from sqlalchemy import select

    from app.models.risk_register import RiskRegister

    with _session() as s:
        reg = s.execute(select(RiskRegister)).scalar_one()
        prov = dict(reg.provenance)
        assert prov["targets"], prov  # the real record first
        prov["targets"] = {}
        reg.provenance = prov
        s.commit()


def test_an_empty_record_prints_no_target_line_and_no_not_recorded_line(
    app_client, capsys  # noqa: F811
) -> None:
    c, bearer, cid = _world(app_client)
    _with_empty_targets(cid)
    capsys.readouterr()
    body = _latest(c, bearer, cid)
    assert body["targets_recorded"] is True
    assert body["targets"] == []
    text = _export_pdf_text(c, bearer, cid)
    assert "Risk Register (v1)" in text  # the positive state first
    assert _NOT_RECORDED not in text
    assert "findings are measured against target" not in text
    assert "risk_register_targets_unreadable" not in capsys.readouterr().out


def test_an_empty_record_on_the_client_dashboard(app_client) -> None:  # noqa: F811
    c, bearer, cid = _world(app_client)
    _with_empty_targets(cid)
    body = _client_dashboard(c, bearer, cid)
    assert body["total_entries"] == 1  # the positive state first
    assert body["targets_recorded"] is True
    assert body["targets"] == []


_GOOD = {"target": 4, "source": "client", "origin": "live_at_generate"}


def test_the_reader_reads_an_empty_record_as_recorded(capsys) -> None:
    from app.risk.baseline import targets_used

    assert targets_used({"targets": {}}) == ([], True)
    assert "risk_register_targets_unreadable" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "raw",
    [
        [],
        None,
        {"csf": {**_GOOD, "target": "4"}},
        {"csf": {**_GOOD, "target": True}},
        {"csf": {**_GOOD, "origin": "frozen_at_release"}},
        {"csf": _GOOD, "zt": "stage 3"},
    ],
    ids=["list", "null", "string-target", "bool-target", "unknown-origin", "one-bad-entry"],
)
def test_a_malformed_record_still_fails_closed_and_logs(raw, capsys) -> None:
    from app.risk.baseline import targets_used

    assert targets_used({"targets": raw}) == ([], False)
    assert "risk_register_targets_unreadable" in capsys.readouterr().out
