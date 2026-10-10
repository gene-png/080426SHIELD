"""#474 E: what each Risk finding carries to the model, per the approved text.

The payload shape is ruling 6's (#736 6086417594, approved as written in
6087027524): `findings` is an object keyed by `source_id`, each finding carries
`source`, `kind`, `label` and an `evidence` object, and the catalog text sits in
three top-level maps (`technique_details`, `subcategory_definitions`,
`zt_capability_details`), so `evidence` holds only client values. Rulings 2, 3
and 5 (#736 6085510246) decide `evidence_capped`, `tier_notes` and the ZT
`target_stage`.

Driven through the generate endpoint and read at the provider. Every expected
value is written from the scenario and the approved text, never read from the
route that builds the payload:

* the evidence keys per kind are the approved text's field lists, as literals;
* CSF levels come from the spec's table (CSF_Flow_Spec section 8, the copy in
  `tests/_csf_playbook_rows.py`) and its evidence-cap rule: without evidence,
  Implementation cannot exceed 1 and the level cannot exceed 2;
* ATT&CK states come from the prompt's own definitions (`in_place`: a confirmed
  tool provides it; `awaiting_review`: tools cited, none confirmed);
* the ZT target is the scenario's: a client target of 3, and a DoD capability
  with no Advanced activity, whose highest stage is 2 (#839).
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from app.ai.llm import LLMResponse
from app.attack._catalog_data import NOT_PREVENTABLE_DATA
from app.attack.catalog import TECHNIQUES
from app.csf.catalog import SUBCATEGORIES
from app.models.attack_assessment import AttackCoverage
from app.models.user import User, UserRole
from app.zt.catalog import DOD_CAPABILITIES, DOD_PILLARS
from tests._csf_playbook_rows import DIMS_FOR_LEVEL

from .test_risk_register import (
    _admin,
    app_client,  # noqa: F401  -- the fixture, used by name below.
)
from .test_zt_dashboard import _attach_intake_target

pytestmark = pytest.mark.unit

#: The approved text's `evidence` fields, per kind (ruling 6), as literals.
ATTACK_KEYS = {
    "status",
    "missing_functions",
    "detection",
    "prevention",
    "response",
    "rationale",
    "notes",
}
CSF_KEYS = {"enterprise_level", "target_level", "tier_levels", "evidence_capped", "tier_notes"}
ZT_KEYS = {"stage", "target_stage", "notes"}

NO_ADVANCED = "DOD.USR.01"  # 1.1 User Inventory: no Advanced activity, highest stage 2
HAS_ADVANCED = "DOD.USR.02"  # 1.2 Conditional User Access: has Advanced activities

#: A standalone technique (no parent, no sub-techniques) MITRE lists a
#: preventive control for, and one it lists none for. From the catalog's data
#: tables, so the setup does not agree with the route by construction.
_NOT_PREVENTABLE = {code for code, _basis in NOT_PREVENTABLE_DATA}
_HAS_CHILDREN = {t.parent_id for t in TECHNIQUES if t.parent_id is not None}
_STANDALONE = [t.id for t in TECHNIQUES if t.parent_id is None and t.id not in _HAS_CHILDREN]
PREVENTABLE = next(c for c in _STANDALONE if c not in _NOT_PREVENTABLE)
NOT_PREVENTABLE = next(c for c in _STANDALONE if c in _NOT_PREVENTABLE)

#: Two CSF subcategories, in the catalog's order.
CSF_A, CSF_B = [s.code for s in SUBCATEGORIES[:2]]


def _engine():
    return create_engine(os.environ["DATABASE_URL"], future=True)


def _set_coverage(assessment_id: str, code: str, **values: Any) -> None:
    """World-building only: the AI run is the writer of `rationale` and of the
    citation record, so a test standing in for it writes them directly."""
    engine = _engine()
    try:
        with Session(engine) as db:
            db.execute(
                update(AttackCoverage)
                .where(
                    AttackCoverage.assessment_id == uuid.UUID(assessment_id),
                    AttackCoverage.technique_code == code,
                )
                .values(**values)
            )
            db.commit()
    finally:
        engine.dispose()


def _seed_attack(c, h: dict) -> None:
    """PREVENTABLE: Detect by a confirmed tool, Prevent by none, Respond by a
    cited tool not yet confirmed: Partial. NOT_PREVENTABLE: no tools: Gap."""
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    a = c.post(f"/attack/services/{svc.json()['id']}/assessments", headers=h).json()
    by_code = {row["technique_code"]: row["id"] for row in a["coverage"]}
    r = c.patch(
        f"/attack/coverage/{by_code[PREVENTABLE]}",
        headers=h,
        json={
            "status": "partial",
            "detection_tools": ["Tool D"],
            "prevention_tools": [],
            "response_tools": ["Tool R"],
            "notes": "Consultant note on the technique.",
        },
    )
    assert r.status_code == 200, r.text
    _set_coverage(
        a["id"],
        PREVENTABLE,
        rationale="AI rationale for the technique.",
        # The shape the citation resolver writes for an inferred match.
        unconfirmed_citations=[
            {
                "tool": "Tool R",
                "cited": "Tool-R",
                "reason": "punctuation",
                "field": "response_tools",
                "cleared_at": None,
            }
        ],
    )
    r = c.patch(f"/attack/coverage/{by_code[NOT_PREVENTABLE]}", headers=h, json={"status": "gap"})
    assert r.status_code == 200, r.text
    r = c.post(f"/attack/assessments/{a['id']}/approve", headers=h)
    assert r.status_code == 200, r.text


def _patch_tier(c, h: dict, svc_id: str, tier: str, code: str, body: dict) -> None:
    rows = c.get(f"/csf/services/{svc_id}/profile/{tier}", headers=h).json()["rows"]
    (row_id,) = [r["id"] for r in rows if r["subcategory_code"] == code]
    r = c.patch(f"/csf/dimension-scores/{row_id}", headers=h, json=body)
    assert r.status_code == 200, r.text


def _dims(level: int) -> dict:
    g, p, i, m, imp = DIMS_FOR_LEVEL[level]
    return {"governance": g, "policy": p, "implementation": i, "monitoring": m, "improvement": imp}


def _seed_csf(c, h: dict) -> None:
    """CSF_A, two tiers. high: level 2 with evidence, target 3, both notes.
    moderate: level-4 dimensions WITHOUT evidence, so Implementation drops to 1
    (total 7, level 3) and the level is capped at 2; only `what_we_found`.
    Both tiers at 2, so the Enterprise level is 2, below the target of 3.

    The questionnaire note on CSF_A is set too: ruling 3 says it is no longer
    sent, and the Playbook does not read it."""
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()
    a = c.post(f"/csf/services/{svc['id']}/assessments", headers=h).json()
    seeded = c.post(
        f"/csf/services/{svc['id']}/profiles/seed", headers=h, json={"tiers": ["high", "moderate"]}
    )
    assert seeded.status_code in (200, 201), seeded.text
    _patch_tier(
        c,
        h,
        svc["id"],
        "high",
        CSF_A,
        {
            **_dims(2),
            "has_evidence": True,
            "target_level": 3,
            "rationale": "High-tier rationale.",
            "what_we_found": "High-tier finding.",
        },
    )
    _patch_tier(
        c,
        h,
        svc["id"],
        "moderate",
        CSF_A,
        {**_dims(4), "has_evidence": False, "what_we_found": "Moderate-tier finding."},
    )
    (answer,) = [x for x in a["answers"] if x["subcategory_code"] == CSF_A]
    r = c.patch(
        f"/csf/answers/{answer['id']}", headers=h, json={"notes": "QUESTIONNAIRE-NOTE-4417"}
    )
    assert r.status_code == 200, r.text
    r = c.post(f"/csf/assessments/{a['id']}/approve", headers=h)
    assert r.status_code == 200, r.text


def _seed_zt(c, h: dict) -> None:
    """A DoD assessment whose client chose stage 3 at intake: NO_ADVANCED and
    HAS_ADVANCED both at stage 1, so both are findings, against 2 and 3."""
    svc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_dod", "title": "ZT"}).json()
    _attach_intake_target(svc["id"], zt_stage=3)
    za = c.post(f"/zt/services/{svc['id']}/assessments", headers=h).json()
    for ans in za["answers"]:
        if ans["capability_code"] == NO_ADVANCED:
            body = {"maturity_stage": 1, "notes": "ZT note on user inventory."}
        elif ans["capability_code"] == HAS_ADVANCED:
            body = {"maturity_stage": 1}
        else:
            continue
        r = c.patch(f"/zt/answers/{ans['id']}", headers=h, json=body)
        assert r.status_code == 200, r.text
    r = c.post(f"/zt/assessments/{za['id']}/approve", headers=h)
    assert r.status_code == 200, r.text


def _generate(c, provider, bearer: str, cid: str) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    def _spy(payload: dict[str, Any]) -> LLMResponse:
        sent.append(payload)
        return LLMResponse(json.dumps({"entries": []}))

    provider.register("risk_synthesize", _spy)
    r = c.post(
        f"/risk/clients/{cid}/register/generate", headers={"Authorization": f"Bearer {bearer}"}
    )
    assert r.status_code == 201, r.text
    assert sent, "no risk_synthesize payload reached the provider"
    return sent


def _world(app_client) -> tuple[Any, Any, str, str]:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    _seed_attack(c, h)
    _seed_csf(c, h)
    _seed_zt(c, h)
    return c, provider, bearer, cid


def _findings(sent: list[dict[str, Any]]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for payload in sent:
        out.update(payload["findings"])
    return out


def test_findings_are_keyed_by_source_id_and_carry_the_approved_fields(
    app_client,  # noqa: F811
) -> None:
    c, provider, bearer, cid = _world(app_client)
    findings = _findings(_generate(c, provider, bearer, cid))
    # What must appear, first.
    assert {PREVENTABLE, NOT_PREVENTABLE, CSF_A, NO_ADVANCED, HAS_ADVANCED} <= set(findings)
    for code, f in findings.items():
        assert set(f) == {"source", "kind", "label", "evidence"}, code
        expected = {"attack": ATTACK_KEYS, "csf": CSF_KEYS, "zt": ZT_KEYS}[f["kind"]]
        assert set(f["evidence"]) == expected, code
    assert findings[CSF_A]["source"] == "questionnaire_response"
    assert findings[PREVENTABLE]["source"] == "coverage_finding"


def test_attack_evidence_names_states_and_confirmed_tools(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid = _world(app_client)
    findings = _findings(_generate(c, provider, bearer, cid))

    assert findings[PREVENTABLE]["evidence"] == {
        "status": "partial",
        "missing_functions": ["prevention", "response"],
        "detection": {"state": "in_place", "tools": ["Tool D"]},
        "prevention": {"state": "not_in_place", "tools": []},
        # Cited, not confirmed: awaiting review, and never listed as a tool.
        "response": {"state": "awaiting_review", "tools": []},
        "rationale": "AI rationale for the technique.",
        "notes": "Consultant note on the technique.",
    }
    # Prevention is not expected, so it is never a missing function.
    assert findings[NOT_PREVENTABLE]["evidence"] == {
        "status": "gap",
        "missing_functions": ["detection", "response"],
        "detection": {"state": "not_in_place", "tools": []},
        "prevention": {"state": "cannot_be_prevented", "tools": []},
        "response": {"state": "not_in_place", "tools": []},
        "rationale": None,
        "notes": None,
    }


def test_csf_evidence_is_the_playbook_per_tier(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid = _world(app_client)
    sent = _generate(c, provider, bearer, cid)
    findings = _findings(sent)

    assert findings[CSF_A]["evidence"] == {
        "enterprise_level": 2,
        "target_level": 3,
        "tier_levels": {"high": 2, "moderate": 2},
        # Ruling 2: per tier, true only where the cap lowered that tier.
        "evidence_capped": {"high": False, "moderate": True},
        # Ruling 3.
        "tier_notes": {
            "high": {"rationale": "High-tier rationale.", "what_we_found": "High-tier finding."},
            "moderate": {"rationale": None, "what_we_found": "Moderate-tier finding."},
        },
    }
    # The label is the code-built one (D'), and the questionnaire note is not sent.
    assert findings[CSF_A]["label"] == f"CSF {CSF_A}: level 2 of target 3"
    assert "QUESTIONNAIRE-NOTE-4417" not in json.dumps(sent)


def test_zt_evidence_carries_the_capped_target(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid = _world(app_client)
    findings = _findings(_generate(c, provider, bearer, cid))

    # HAS_ADVANCED first: the uncapped target, what must appear.
    assert findings[HAS_ADVANCED]["evidence"] == {"stage": 1, "target_stage": 3, "notes": None}
    # Ruling 5: the target the finding was compared against, never the asked 3.
    assert findings[NO_ADVANCED]["evidence"] == {
        "stage": 1,
        "target_stage": 2,
        "notes": "ZT note on user inventory.",
    }


def _more_attack_gaps(c, h: dict, n: int) -> None:
    """A second ATT&CK service is refused (#876), so the extra gaps go on a
    fresh assessment's standalone rows in the SAME world: `n` more findings,
    enough that the run takes more than one batch."""
    from tests._attack_rows import standalone_rows

    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "B"})
    a = c.post(f"/attack/services/{svc.json()['id']}/assessments", headers=h).json()
    for cov in standalone_rows(a["coverage"], n):
        r = c.patch(f"/attack/coverage/{cov['id']}", headers=h, json={"status": "gap"})
        assert r.status_code == 200, r.text
    assert c.post(f"/attack/assessments/{a['id']}/approve", headers=h).status_code == 200


def test_catalog_text_rides_in_the_top_level_maps_per_batch(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    # 21 ATT&CK gaps, the CSF and ZT findings beside them: more than one batch.
    _more_attack_gaps(c, h, 21)
    _seed_csf(c, h)
    _seed_zt(c, h)
    sent = _generate(c, provider, bearer, cid)
    assert len(sent) > 1, "precondition: more than one batch"
    by_code_tech = {t.id: t.name for t in TECHNIQUES}
    by_code_csf = {s.code: s.outcome for s in SUBCATEGORIES}
    by_code_zt = {cap.code: cap for cap in DOD_CAPABILITIES}
    pillar_names = {p.code: p.name for p in DOD_PILLARS}

    seen_kinds: set[str] = set()
    for payload in sent:
        f = payload["findings"]
        by_kind = {
            k: {sid for sid, x in f.items() if x["kind"] == k} for k in ("attack", "csf", "zt")
        }
        seen_kinds |= {k for k, v in by_kind.items() if v}
        assert payload["technique_details"] == {
            code: {"name": by_code_tech[code], "not_preventable": code in _NOT_PREVENTABLE}
            for code in sorted(by_kind["attack"], key=list(f).index)
        }
        assert payload["subcategory_definitions"] == {
            code: by_code_csf[code] for code in sorted(by_kind["csf"], key=list(f).index)
        }
        assert payload["zt_capability_details"] == {
            code: {
                "framework": "dod_ztra",
                "pillar": pillar_names[by_code_zt[code].pillar_code],
                "name": by_code_zt[code].name,
            }
            for code in sorted(by_kind["zt"], key=list(f).index)
        }
    assert seen_kinds == {"attack", "csf", "zt"}


def test_a_tenant_users_name_in_a_note_reaches_the_ai_redacted(app_client) -> None:  # noqa: F811
    """#1006's Risk half (advisor, #736 6090870696): the notes E sends get the
    tenant's name list, as Tech Debt's extraction and the ATT&CK what-if do."""
    c, provider = app_client
    bearer, cid = _admin(c)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    engine = _engine()
    try:
        with Session(engine) as db:
            db.add(
                User(
                    email="dana.whitfield@acme.example",
                    password_hash="x" * 64,
                    role=UserRole.CLIENT,
                    display_name="Dana Whitfield",
                    client_id=uuid.UUID(cid),
                )
            )
            db.commit()
    finally:
        engine.dispose()
    _seed_attack(c, h)
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()
    a = c.post(f"/csf/services/{svc['id']}/assessments", headers=h).json()
    seeded = c.post(f"/csf/services/{svc['id']}/profiles/seed", headers=h, json={"tiers": ["high"]})
    assert seeded.status_code in (200, 201), seeded.text
    _patch_tier(
        c,
        h,
        svc["id"],
        "high",
        CSF_B,
        {
            **_dims(1),
            "has_evidence": True,
            "target_level": 3,
            "what_we_found": "Walked through the runbook with Dana Whitfield.",
        },
    )
    assert c.post(f"/csf/assessments/{a['id']}/approve", headers=h).status_code == 200

    findings = _findings(_generate(c, provider, bearer, cid))
    note = findings[CSF_B]["evidence"]["tier_notes"]["high"]["what_we_found"]
    assert "[NAME]" in note
    assert "Dana" not in note and "Whitfield" not in note
