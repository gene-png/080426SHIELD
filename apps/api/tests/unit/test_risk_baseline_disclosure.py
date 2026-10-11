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

Each stored entry carries its `kind` and `framework` (advisor, #736
6054419744, approving 6053630989): the dict key is a scope key, an id that is
never rendered. The framework is named only when the record holds more than
one Zero Trust entry (Q3, ruling 2a). The expected lines below are the
approved table's strings, verbatim.
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
    _seed_csf_playbook_at_level,
    _session,
    app_client,
)

pytestmark = pytest.mark.unit

#: #474 D': CSF is measured per subcategory against the Playbook.
_CSF_PLAYBOOK_LINE = (
    "NIST CSF findings are measured against each subcategory's target level in the CSF Playbook."
)


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


def _world(app_client, *, csf: bool = False):  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    if csf:
        _seed_csf_playbook_at_level(c, bearer, cid, level=1, target=4)
    _generate(c, provider, bearer, cid, _entries_payload(_entry("R")))
    return c, bearer, cid


def test_the_register_records_each_services_target(app_client) -> None:  # noqa: F811
    c, bearer, cid = _world(app_client, csf=True)
    body = _latest(c, bearer, cid)
    assert body["targets_recorded"] is True
    by_kind = {t["kind"]: t for t in body["targets"]}
    assert by_kind["csf"] == {
        "kind": "csf",
        "framework": None,
        "target": None,
        "source": "playbook",
        "origin": "live_at_generate",
    }
    # No ZT target was set, so ZT used the engine default and says so.
    assert by_kind["zt"]["framework"] == "cisa_ztmm_2_0"
    assert by_kind["zt"]["source"] == "default"
    assert by_kind["zt"]["origin"] == "live_at_generate"


def test_the_export_states_the_baseline(app_client) -> None:  # noqa: F811
    c, bearer, cid = _world(app_client, csf=True)
    text = _export_pdf_text(c, bearer, cid)
    assert _CSF_PLAYBOOK_LINE in text
    # One ZT entry: the framework is not named (Q3).
    assert (
        "Zero Trust findings are measured against target stage 3, "
        "SHIELD's default: no engagement target was set." in text
    )
    assert "Zero Trust (" not in text


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
    c, bearer, cid = _world(app_client, csf=True)
    body = _client_dashboard(c, bearer, cid)
    assert body["targets_recorded"] is True
    csf = {t["kind"]: t for t in body["targets"]}["csf"]
    assert (csf["target"], csf["source"]) == (None, "playbook")


# ---------------------------------------------------------------------------
# CISA (client 4) plus DoD (default), the approved table's two-ZT row, through
# generate and every surface. Literal strings, positive first.
# ---------------------------------------------------------------------------

_CISA_LINE = (
    "Zero Trust (CISA ZTMM 2.0) findings are measured against target stage 4, "
    "the engagement target when this register was generated."
)
_DOD_LINE = (
    "Zero Trust (DoD ZT Reference Architecture) findings are measured against "
    "target stage 3, SHIELD's default: no engagement target was set."
)
_TWO_ZT_TARGETS = [
    {
        "kind": "zt",
        "framework": "cisa_ztmm_2_0",
        "target": 4,
        "source": "client",
        "origin": "live_at_generate",
    },
    {
        "kind": "zt",
        "framework": "dod_ztra",
        "target": 3,
        "source": "default",
        "origin": "live_at_generate",
    },
]


def _two_zt_world(app_client):  # noqa: F811
    from tests.unit.test_risk_register import _set_zt_target

    c, provider = app_client
    bearer, cid = _admin(c)
    _both_frameworks(c, bearer, cid)
    _set_zt_target(cid, 4, kind="zero_trust_cisa")
    r = _generate_per_finding(c, provider, bearer, cid, [])
    assert r.status_code == 201, r.text
    return c, bearer, cid


def _stored_targets() -> dict:
    from sqlalchemy import select

    from app.models.risk_register import RiskRegister

    with _session() as s:
        return dict(s.execute(select(RiskRegister)).scalar_one().provenance["targets"])


def test_two_zero_trust_services_store_kind_and_framework(app_client) -> None:  # noqa: F811
    _two_zt_world(app_client)
    assert _stored_targets() == {
        "zt:cisa_ztmm_2_0": {
            "target": 4,
            "source": "client",
            "kind": "zt",
            "framework": "cisa_ztmm_2_0",
            "origin": "live_at_generate",
        },
        "zt:dod_ztra": {
            "target": 3,
            "source": "default",
            "kind": "zt",
            "framework": "dod_ztra",
            "origin": "live_at_generate",
        },
    }


def test_two_zero_trust_services_reach_the_admin_response(app_client) -> None:  # noqa: F811
    c, bearer, cid = _two_zt_world(app_client)
    body = _latest(c, bearer, cid)
    assert body["targets_recorded"] is True
    assert body["targets"] == _TWO_ZT_TARGETS


def test_two_zero_trust_services_reach_the_client_dashboard(app_client) -> None:  # noqa: F811
    c, bearer, cid = _two_zt_world(app_client)
    body = _client_dashboard(c, bearer, cid)
    assert body["targets_recorded"] is True
    assert body["targets"] == _TWO_ZT_TARGETS


def test_two_zero_trust_services_name_each_framework_in_every_file(
    app_client,  # noqa: F811
) -> None:
    c, bearer, cid = _two_zt_world(app_client)
    texts = _export_texts(c, bearer, cid)
    # All three files: the XLSX summary sheet prints `_summary_lines` too.
    for fmt in ("pdf", "docx", "xlsx"):
        text = " ".join(texts[fmt].split())
        assert _CISA_LINE in text, (fmt, text)
        assert _DOD_LINE in text, (fmt, text)
        assert text.index(_CISA_LINE) < text.index(_DOD_LINE), fmt
        assert "zt:" not in text, fmt
        assert "target level" not in text, fmt


def test_csf_plus_cisa_plus_dod_print_the_csf_line_then_cisa_then_dod(
    app_client,  # noqa: F811
) -> None:
    """The table's last recorded row: the CSF line, then the two ZT lines,
    sorted by (kind, framework), in every file."""
    from tests.unit.test_risk_register import _set_zt_target

    c, provider = app_client
    bearer, cid = _admin(c)
    _both_frameworks(c, bearer, cid)
    _seed_csf_playbook_at_level(c, bearer, cid, level=1, target=4)
    _set_zt_target(cid, 4, kind="zero_trust_cisa")
    r = _generate_per_finding(c, provider, bearer, cid, [])
    assert r.status_code == 201, r.text
    texts = _export_texts(c, bearer, cid)
    for fmt in ("pdf", "docx", "xlsx"):
        text = " ".join(texts[fmt].split())
        positions = [text.find(line) for line in (_CSF_PLAYBOOK_LINE, _CISA_LINE, _DOD_LINE)]
        assert -1 not in positions, (fmt, positions, text)  # the positive state first
        assert positions == sorted(positions), (fmt, positions)


@pytest.mark.parametrize(
    "chosen, line",
    [
        (
            None,
            "NIST CSF findings are measured against target tier 3, SHIELD's default: "
            "no engagement target was set.",
        ),
        (
            9,
            "NIST CSF findings are measured against target tier 3, SHIELD's default: "
            "the engagement target could not be used.",
        ),
    ],
    ids=["none-set", "unusable"],
)
def test_one_csf_default_and_unusable_lines(chosen, line) -> None:
    """The table's "One CSF, none set" and "One CSF, unusable" rows. The
    target and source come from the resolver generate calls, so the state is
    one a register can hold."""
    from app.csf.gap import resolve_target_tier
    from app.risk.exporters import _target_lines

    target, source = resolve_target_tier(chosen)
    assert _target_lines((("csf", None, target, source, "live_at_generate"),)) == [line]


# ---------------------------------------------------------------------------
# The reader (`app/risk/baseline.py::targets_used`), every stored shape.
# Fail closed (ruling 2d): anything it cannot read is "not recorded", logged.
# ---------------------------------------------------------------------------

_E = {"target": 4, "source": "client", "origin": "live_at_generate"}


def _read(raw):
    from app.risk.baseline import targets_used

    rows, recorded = targets_used({"targets": raw})
    return [(r.kind, r.framework, r.target, r.source, r.origin) for r in rows], recorded


def test_the_reader_reads_kind_and_framework(capsys) -> None:
    raw = {
        "zt:dod_ztra": {**_E, "target": 3, "kind": "zt", "framework": "dod_ztra"},
        "csf": {**_E, "kind": "csf", "framework": None},
        "zt:cisa_ztmm_2_0": {**_E, "kind": "zt", "framework": "cisa_ztmm_2_0"},
    }
    # Sorted by (kind, framework), whatever the stored order.
    assert _read(raw) == (
        [
            ("csf", None, 4, "client", "live_at_generate"),
            ("zt", "cisa_ztmm_2_0", 4, "client", "live_at_generate"),
            ("zt", "dod_ztra", 3, "client", "live_at_generate"),
        ],
        True,
    )
    assert "risk_register_targets_unreadable" not in capsys.readouterr().out


def test_the_reader_reads_a_legacy_bare_entry_as_before(capsys) -> None:
    raw = {"csf": dict(_E), "zt": {**_E, "target": 3, "source": "default"}}
    assert _read(raw) == (
        [
            ("csf", None, 4, "client", "live_at_generate"),
            ("zt", None, 3, "default", "live_at_generate"),
        ],
        True,
    )
    assert "risk_register_targets_unreadable" not in capsys.readouterr().out


def test_no_targets_key_is_not_recorded_and_not_logged(capsys) -> None:
    from app.risk.baseline import targets_used

    assert targets_used({"inputs": []}) == ([], False)
    assert targets_used(None) == ([], False)
    assert "risk_register_targets_unreadable" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "raw",
    [
        # Ruling 2d: an empty record is unreachable and reads as not recorded.
        {},
        [],
        None,
        # A framework-qualified key without `kind`: the key is never parsed.
        {"zt:cisa_ztmm_2_0": dict(_E)},
        # A legacy entry under a key that is not a bare kind.
        {"attack": dict(_E)},
        # `kind` present but not a pair the reader knows.
        {"csf": {**_E, "kind": "csf", "framework": "cisa_ztmm_2_0"}},
        {"zt": {**_E, "kind": "zt", "framework": None}},
        {"zt": {**_E, "kind": "zt"}},
        {"zt": {**_E, "kind": "zt", "framework": "zt_unknown"}},
        {"attack": {**_E, "kind": "attack", "framework": None}},
        {"zt": {**_E, "kind": "zt", "framework": ["dod_ztra"]}},
        # Two entries the lines could not tell apart.
        {
            "zt:a": {**_E, "kind": "zt", "framework": "dod_ztra"},
            "zt:b": {**_E, "kind": "zt", "framework": "dod_ztra"},
        },
        # The value shapes, as before.
        {"csf": {**_E, "target": "4"}},
        {"csf": {**_E, "target": True}},
        {"csf": {**_E, "origin": "frozen_at_release"}},
        {"csf": {**_E, "source": 1}},
        {"csf": dict(_E), "zt": "stage 3"},
    ],
    ids=[
        "empty",
        "list",
        "null",
        "qualified-key-no-kind",
        "legacy-unknown-key",
        "csf-with-framework",
        "zt-null-framework",
        "zt-no-framework",
        "zt-unknown-framework",
        "unknown-kind",
        "unhashable-framework",
        "duplicate-kind-framework",
        "string-target",
        "bool-target",
        "unknown-origin",
        "non-string-source",
        "one-bad-entry",
    ],
)
def test_an_unreadable_record_is_not_recorded_and_logged(raw, capsys) -> None:
    assert _read(raw) == ([], False)
    assert "risk_register_targets_unreadable" in capsys.readouterr().out


def test_attack_alone_cannot_generate_so_no_register_records_no_targets(
    app_client,  # noqa: F811
) -> None:
    """Why the empty record is unreachable (ruling 2d): generate requires
    `has_attack and (has_csf or has_zt)`, and every CSF or ZT source gets a
    target."""
    from tests._attack_rows import first_standalone

    c, _provider = app_client
    bearer, cid = _admin(c)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    asvc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    assert asvc.status_code in (200, 201), asvc.text
    a = c.post(f"/attack/services/{asvc.json()['id']}/assessments", headers=h)
    cov = first_standalone(a.json()["coverage"])
    r = c.patch(f"/attack/coverage/{cov['id']}", headers=h, json={"status": "gap"})
    assert r.status_code == 200, r.text
    ar = c.post(f"/attack/assessments/{a.json()['id']}/approve", headers=h)
    assert ar.status_code == 200, ar.text
    gen = c.post(f"/risk/clients/{cid}/register/generate", headers=h)
    assert gen.status_code == 409, gen.text
    assert "a CSF or Zero Trust assessment" in gen.text


def test_a_target_with_no_source_raises_rather_than_guessing() -> None:
    """Fail closed: `_gather_findings` keys every target by a source's
    `scope_key`, so no path produces an orphan, and a record that guessed
    would name a service it could not identify."""
    from app.routes.risk import _targets_record

    with pytest.raises(RuntimeError, match="'zt:dod_ztra' has no source"):
        _targets_record({"zt:dod_ztra": {"target": 3, "source": "default"}}, ())
