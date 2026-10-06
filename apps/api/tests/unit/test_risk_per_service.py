"""#876, Gene's ruling (#736 6018510340, advisor 6019425290): the Risk Register
takes findings from EVERY engaged service, not one per kind.

The case the ruling names is Zero Trust: a client engaged for both CISA ZTMM
2.0 and DoD ZT Reference Architecture gets both frameworks' findings. Until
#876 synthesis read one assessment per kind, so one framework was dropped in
silence -- a client-number gap, not a label.

Two engaged services of the same kind AND framework would produce the same
finding codes, and `source_id` is the key every per-finding record joins on, so
generate refuses that case (Q2 option (a)) with the advisor's sentence.

Everything goes through the real routes; inputs are released through the real
finalize -> release endpoints (`tests/_risk_inputs.py`).
"""

from __future__ import annotations

import io
import json

import pytest

from app.ai.llm import LLMResponse
from tests._risk_inputs import release, seed_attack_and_zt
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _pdf_text,
    _session,
    app_client,
)

pytestmark = pytest.mark.unit

_DUPLICATE = (
    "Two engaged services of the same kind would produce the same findings: {titles}. "
    "The register cannot be generated while both are engaged."
)


def _h(bearer: str, cid: str) -> dict:
    return {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}


def _seed_dod(c, bearer: str, cid: str, *, approve: bool = True) -> tuple[str, str]:
    """A DoD ZT service with one capability at stage 1 (below every target)."""
    h = _h(bearer, cid)
    svc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_dod", "title": "ZT DoD"})
    assert svc.status_code in (200, 201), svc.text
    a = c.post(f"/zt/services/{svc.json()['id']}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    ans = a.json()["answers"][0]
    r = c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"maturity_stage": 1})
    assert r.status_code == 200, r.text
    if approve:
        ap = c.post(f"/zt/assessments/{a.json()['id']}/approve", headers=h)
        assert ap.status_code == 200, ap.text
    return svc.json()["id"], ans["capability_code"]


def _per_finding(seen: list[dict]):
    """One entry per finding, as the real prompt asks; records each payload."""

    def fn(payload: dict) -> LLMResponse:
        seen.append(payload)
        entries = [
            {
                "title": f"Risk for {f['source_id']}",
                "description": "d",
                "axis": "detection",
                "source": f["source"],
                "source_id": f["source_id"],
                "linked_techniques": [],
                "linked_controls": [],
                "likelihood": "high",
                "impact": "major",
                "recommended_action": "remediate",
                "rationale": "r",
            }
            for f in payload.get("findings", [])
        ]
        return LLMResponse(json.dumps({"entries": entries}))

    return fn


def _generate(c, provider, bearer: str, cid: str, seen: list[dict]):
    provider.register("risk_synthesize", _per_finding(seen))
    return c.post(f"/risk/clients/{cid}/register/generate", headers=_h(bearer, cid))


def _both_frameworks(c, bearer: str, cid: str):
    s = seed_attack_and_zt(c, bearer, cid)
    dod_svc, dod_code = _seed_dod(c, bearer, cid)
    return s, dod_svc, dod_code


def _export_texts(c, bearer: str, cid: str) -> dict[str, str]:
    from docx import Document
    from openpyxl import load_workbook

    h = _h(bearer, cid)
    ex = c.post(f"/risk/clients/{cid}/register/export", headers=h)
    assert ex.status_code == 200, ex.text
    body = ex.json()
    raw = {
        k: c.get(f"/artifacts/{body[f'{k}_artifact_id']}/download", headers=h).content
        for k in ("pdf", "docx", "xlsx")
    }
    wb = load_workbook(io.BytesIO(raw["xlsx"]))
    xlsx = "\n".join(
        str(v) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for v in row if v
    )
    doc = Document(io.BytesIO(raw["docx"]))
    docx = "\n".join(
        [p.text for p in doc.paragraphs]
        + [cell.text for t in doc.tables for row in t.rows for cell in row.cells]
    )
    return {"pdf": " ".join(_pdf_text(raw["pdf"]).split()), "docx": docx, "xlsx": xlsx}


def test_both_zero_trust_frameworks_feed_the_register(app_client) -> None:  # noqa: F811
    """CISA and DoD both engaged: findings from BOTH reach the register, each
    entry names its framework's code, and every export carries both."""
    c, provider = app_client
    bearer, cid = _admin(c)
    s, _dod_svc, dod_code = _both_frameworks(c, bearer, cid)
    assert s.capability.startswith("CISA.") and dod_code.startswith("DOD."), (s, dod_code)
    seen: list[dict] = []
    r = _generate(c, provider, bearer, cid, seen)
    assert r.status_code == 201, r.text
    sources = {e["source_id"] for e in r.json()["entries"]}
    assert s.technique in sources, sources  # the positive state first
    assert {s.capability, dod_code} <= sources, sources
    texts = _export_texts(c, bearer, cid)
    for kind, text in texts.items():
        assert s.capability in text and dod_code in text, kind


def test_one_zero_trust_framework_feeds_only_itself(app_client) -> None:  # noqa: F811
    """CISA only: the register has CISA findings and no DoD finding at all."""
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    seen: list[dict] = []
    r = _generate(c, provider, bearer, cid, seen)
    assert r.status_code == 201, r.text
    sources = {e["source_id"] for e in r.json()["entries"]}
    assert s.capability in sources, sources
    assert not [x for x in sources if x.startswith("DOD.")], sources


def test_each_framework_is_held_to_its_own_target(app_client) -> None:  # noqa: F811
    """The CISA engagement targets stage 4; DoD has no target, so it takes the
    default 3, the top of its three-stage ladder. A capability at stage 3 is
    therefore a finding under CISA and none under DoD. Resolving the target
    once per KIND would hold DoD to CISA's 4 and invent a DoD finding."""
    from tests.unit.test_risk_register import _set_zt_stage, _set_zt_target

    c, provider = app_client
    bearer, cid = _admin(c)
    s, _dod_svc, dod_code = _both_frameworks(c, bearer, cid)
    _set_zt_target(cid, 4, kind="zero_trust_cisa")
    _set_zt_stage(cid, s.capability, 3)
    _set_zt_stage(cid, dod_code, 3)
    seen: list[dict] = []
    gen = _generate(c, provider, bearer, cid, seen)
    assert gen.status_code == 201, gen.text
    sources = {e["source_id"] for e in gen.json()["entries"]}
    assert s.capability in sources, sources  # the positive state first
    assert dod_code not in sources, sources


def test_no_batch_mixes_two_zero_trust_services(app_client) -> None:  # noqa: F811
    """Per-service batching (Q4): CISA's and DoD's findings never share a
    request, however few there are."""
    c, provider = app_client
    bearer, cid = _admin(c)
    _both_frameworks(c, bearer, cid)
    seen: list[dict] = []
    assert _generate(c, provider, bearer, cid, seen).status_code == 201
    assert len(seen) >= 2, len(seen)
    for payload in seen:
        frameworks = {
            f["source_id"].split(".")[0]
            for f in payload["findings"]
            if f["source_id"].startswith(("CISA.", "DOD."))
        }
        assert len(frameworks) <= 1, payload["findings"]
    zt_batches = [p for p in seen if any(f["source_id"].startswith("DOD.") for f in p["findings"])]
    assert zt_batches, "no batch carried the DoD finding"


def test_a_finding_carries_its_own_services_state(app_client) -> None:  # noqa: F811
    """CISA released, DoD approved: only the DoD finding is labelled, because
    the label comes from the finding's own service, never from its kind."""
    c, provider = app_client
    bearer, cid = _admin(c)
    s, _dod_svc, dod_code = _both_frameworks(c, bearer, cid)
    release(c, bearer, cid, "zt", s.zt_service)
    seen: list[dict] = []
    r = _generate(c, provider, bearer, cid, seen)
    assert r.status_code == 201, r.text
    states = {e["source_id"]: e["source_state"] for e in r.json()["entries"]}
    assert states[dod_code] == "approved", states
    assert states[s.capability] is None, states


def test_the_provenance_and_scored_coverage_name_each_framework(app_client) -> None:  # noqa: F811
    """One provenance input per service, and the scored-coverage disclosure
    gets one row per framework, labelled with the framework (Q3)."""
    from sqlalchemy import select

    from app.models.risk_register import RiskRegister

    c, provider = app_client
    bearer, cid = _admin(c)
    _both_frameworks(c, bearer, cid)
    seen: list[dict] = []
    assert _generate(c, provider, bearer, cid, seen).status_code == 201
    with _session() as db:
        prov = db.execute(select(RiskRegister)).scalar_one().provenance
    zt_inputs = sorted(i["framework"] for i in prov["inputs"] if i["kind"] == "zt")
    assert zt_inputs == ["cisa_ztmm_2_0", "dod_ztra"], prov["inputs"]
    assert sorted(prov["link_scope"]) == ["attack", "zt:cisa_ztmm_2_0", "zt:dod_ztra"]
    xlsx = _export_texts(c, bearer, cid)["xlsx"]
    assert (
        "Zero Trust (CISA ZTMM 2.0)" in xlsx
        and "Zero Trust (DoD ZT Reference Architecture)" in xlsx
    )


def test_a_single_zero_trust_keeps_its_unqualified_label(app_client) -> None:  # noqa: F811
    """The framework is named only when a kind has more than one row."""
    from sqlalchemy import select

    from app.models.risk_register import RiskRegister

    c, provider = app_client
    bearer, cid = _admin(c)
    seed_attack_and_zt(c, bearer, cid)
    seen: list[dict] = []
    assert _generate(c, provider, bearer, cid, seen).status_code == 201
    with _session() as db:
        prov = db.execute(select(RiskRegister)).scalar_one().provenance
    assert sorted(prov["link_scope"]) == ["attack", "zt"], prov["link_scope"]
    g = c.get(f"/risk/clients/{cid}/gate", headers=_h(bearer, cid)).json()
    assert [r["qualifier"] for r in g["inputs"] if r["kind"] == "zt"] == [None]


def test_the_inputs_panel_names_each_zero_trust_framework(app_client) -> None:  # noqa: F811
    c, _ = app_client
    bearer, cid = _admin(c)
    _both_frameworks(c, bearer, cid)
    g = c.get(f"/risk/clients/{cid}/gate", headers=_h(bearer, cid)).json()
    assert [r["qualifier"] for r in g["inputs"] if r["kind"] == "zt"] == [
        "CISA ZTMM 2.0",
        "DoD ZT Reference Architecture",
    ]


def test_two_services_of_one_kind_and_framework_refuse_generate(app_client) -> None:  # noqa: F811
    """Q2 (a): two CISA services would produce the same finding codes, and
    `source_id` is the key every per-finding record joins on. Refused, typed,
    with the advisor's sentence; the gate carries the same sentence."""
    c, provider = app_client
    bearer, cid = _admin(c)
    seed_attack_and_zt(c, bearer, cid)
    h = _h(bearer, cid)
    svc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "ZT 2"})
    assert c.post(f"/zt/services/{svc.json()['id']}/assessments", headers=h).status_code in (
        200,
        201,
    )
    expected = _DUPLICATE.format(titles="ZT and ZT 2")
    g = c.get(f"/risk/clients/{cid}/gate", headers=h).json()
    assert g["duplicate_inputs"] == expected, g
    seen: list[dict] = []
    r = _generate(c, provider, bearer, cid, seen)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "risk_register_duplicate_inputs", r.json()
    assert r.json()["error"]["message"] == expected
    assert seen == [], "a refused generate must not reach the model"


def test_one_service_per_kind_is_not_a_duplicate(app_client) -> None:  # noqa: F811
    c, _ = app_client
    bearer, cid = _admin(c)
    _both_frameworks(c, bearer, cid)
    g = c.get(f"/risk/clients/{cid}/gate", headers=_h(bearer, cid)).json()
    assert g["unlocked"] is True and g["duplicate_inputs"] is None, g
