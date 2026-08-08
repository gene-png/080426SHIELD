"""mitre_map Run-AI: D/P/R suggestions, tool validation, lock-skip (Work Order D2)."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus
from app.models.service import Service, ServiceKind, ServiceStatus


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker, FixtureProvider]]:
    url = f"sqlite:///{tmp_path / 'shield-attackai.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app
    from app.routes.attack import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    provider = FixtureProvider()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
    with TestClient(app) as c:
        yield c, TestSession, provider


def _admin(c: TestClient) -> tuple[str, str]:
    admin = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    bearer = admin.json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Acme"},
    ).json()["id"]
    return bearer, cid


def _seed_tech_debt_tools(
    TestSession: sessionmaker,
    cid: str,
    user_id,
    tools: list[str],
    *,
    security_related: bool | None = None,
    confirmed: bool = False,
    vendor: str | None = None,
    category: str | None = None,
    security_functions: list[str] | None = None,
    notes: str | None = None,
    annual_cost_usd: int | None = None,
    title: str = "Acme Tech Debt",
    version: int = 1,
    status: str = "APPROVED",
) -> None:
    """A Tech Debt service + approved capability list with the given tool names.

    `security_related` / `confirmed` set the security classification, which is
    what `security_scope_filter` keys on — see `tech_debt/security_scope.py`.
    The default (None, False) is the pre-0038 shape: in scope.
    """
    import uuid as _uuid

    with TestSession() as db:
        svc = Service(
            kind=ServiceKind.TECH_DEBT,
            status=ServiceStatus.IN_PROGRESS,
            title=title,
            client_id=_uuid.UUID(cid),
            opened_by=_uuid.UUID(user_id),
        )
        db.add(svc)
        db.flush()
        cl = CapabilityList(service_id=svc.id, version=version, status=CapabilityListStatus[status])
        db.add(cl)
        db.flush()
        for name in tools:
            db.add(
                CapabilityItem(
                    capability_list_id=cl.id,
                    name=name,
                    vendor=vendor,
                    category=category,
                    security_functions=security_functions,
                    notes=notes,
                    annual_cost_usd=annual_cost_usd,
                    security_related=security_related,
                    security_class_confirmed=confirmed,
                )
            )
        db.commit()


@pytest.mark.unit
def test_run_ai_applies_validated_dpr_and_reports_changes(app_client) -> None:
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon", "Splunk"])

    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "Acme ATT&CK"}
    )
    svc_id = svc.json()["id"]
    a = c.post(f"/attack/services/{svc_id}/assessments", headers=h)
    code = a.json()["coverage"][0]["technique_code"]

    # The AI suggests covered + D/P/R, citing one real tool and one not in the list.
    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": [{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["CrowdStrike Falcon", "Nonexistent Tool"],'
            ' "prevention_tools": [], "response_tools": ["Splunk"],'
            ' "rationale": "EDR detects, SIEM responds."}]}'
        ),
    )

    r = c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tools_available"] == 2
    row = next(t for t in body["coverage"] if t["technique_code"] == code)
    assert row["status"] == "covered"
    # The invented tool was dropped; only the validated one remains.
    assert row["detection_tools"] == ["CrowdStrike Falcon"]
    assert row["response_tools"] == ["Splunk"]
    assert row["rationale"] == "EDR detects, SIEM responds."
    # The change list reflects what the AI changed.
    fields = {ch["field"] for ch in body["changed"] if ch["technique_code"] == code}
    assert {"status", "detection_tools", "response_tools", "rationale"} <= fields


@pytest.mark.unit
def test_run_ai_refuses_when_the_client_has_no_security_capabilities(app_client) -> None:
    """An empty allow-list cannot produce an assessment — only a fabricated one.

    `valid_tools` is a hard allow-list: a tool absent from it cannot be cited, so
    with ZERO tools every technique can only come back uncovered. On 2026-08-07 a
    live run in exactly this state wrote 607 gaps and 26 not-applicable across
    633 techniques, billed for the call, and left a releasable assessment stating
    a catastrophic security posture that was an artifact of missing input. The
    audit row recorded `tools_available: 0` — the system knew.

    Refuse before spending anything. The consultant's real problem is that this
    client has no approved Tech Debt inventory, and that is what we say.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "Acme ATT&CK"}
    )
    svc_id = svc.json()["id"]
    created = c.post(f"/attack/services/{svc_id}/assessments", headers=h)
    before = {row["technique_code"]: row["status"] for row in created.json()["coverage"]}

    # Deliberately NO Tech Debt list for this client.
    called: list[dict] = []

    def _spy(payload: dict) -> LLMResponse:
        called.append(payload)
        return LLMResponse('{"techniques": []}')

    provider.register("mitre_map", _spy)

    r = c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["reason"] == "no_security_capabilities"
    # The message has to name the actual remedy, not the symptom.
    assert "Tech Debt" in err["message"]

    # The expensive part never happened — this is the whole point of blocking
    # rather than warning after the fact.
    assert called == [], "the provider must not be called with an empty allow-list"

    # And nothing was written: no fabricated gaps left behind to be released.
    after = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h)
    assert after.status_code == 200, after.text
    assert {row["technique_code"]: row["status"] for row in after.json()["coverage"]} == before


@pytest.mark.unit
def test_run_ai_allows_a_client_whose_only_capabilities_are_non_security(app_client) -> None:
    """A row the consultant confirmed as non-security leaves the ATT&CK subset.

    If that empties the subset the run is refused for the same reason as above —
    the distinction that matters is "no security tooling", not "no rows".
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(
        TestSession, cid, me["id"], ["Figma"], security_related=False, confirmed=True
    )
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "Acme"})
    svc_id = svc.json()["id"]
    c.post(f"/attack/services/{svc_id}/assessments", headers=h)

    r = c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "no_security_capabilities"


@pytest.mark.unit
def test_run_ai_skips_locked_rows(app_client) -> None:
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    # This spec is about lock-skipping, not about the empty-list guard — give it
    # a real tool so it exercises the path it is named for.
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Splunk"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "Acme"})
    svc_id = svc.json()["id"]
    a = c.post(f"/attack/services/{svc_id}/assessments", headers=h)
    cov = a.json()["coverage"][0]
    code, cov_id = cov["technique_code"], cov["id"]

    # Lock the row.
    c.patch(f"/attack/coverage/{cov_id}", headers=h, json={"locked": True})

    provider.register_static(
        "mitre_map",
        LLMResponse('{"techniques": [{"technique_code": "' + code + '", "status": "covered"}]}'),
    )
    r = c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    # Locked row untouched + absent from the change list.
    row = next(t for t in body["coverage"] if t["technique_code"] == code)
    assert row["status"] is None
    assert all(ch["technique_code"] != code for ch in body["changed"])


@pytest.mark.unit
def test_run_ai_marks_documents_stale(app_client) -> None:
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    # Staleness is what this spec is about; seed a tool so the empty-list guard
    # does not short-circuit the run before it can mark anything.
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Splunk"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "Acme"})
    svc_id = svc.json()["id"]
    a = c.post(f"/attack/services/{svc_id}/assessments", headers=h)
    code = a.json()["coverage"][0]["technique_code"]
    assert a.json()["documents_stale"] is False

    provider.register_static(
        "mitre_map",
        LLMResponse('{"techniques": [{"technique_code": "' + code + '", "status": "covered"}]}'),
    )
    c.post(f"/attack/services/{svc_id}/run-ai", headers=h)

    latest = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h)
    assert latest.status_code == 200, latest.text
    assert latest.json()["documents_stale"] is True  # Work Order C3


# ---------------------------------------------------------------------------
# The enriched capability payload (2026-08-08).
#
# The model used to receive bare strings, so it re-derived detection /
# prevention / response from a product name alone — while the extractor had
# already classified exactly that and the ATT&CK path discarded it. These tests
# pin what egresses, and — more importantly — what must NOT.
# ---------------------------------------------------------------------------


def _capture_payload(provider, response: str = '{"techniques": []}') -> list[dict]:
    """Register a mitre_map fixture that records every payload it is handed."""
    seen: list[dict] = []

    def _spy(payload: dict) -> LLMResponse:
        seen.append(payload)
        return LLMResponse(response)

    provider.register("mitre_map", _spy)
    return seen


@pytest.mark.unit
def test_capability_payload_carries_the_fields_the_extractor_already_found(app_client) -> None:
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(
        TestSession,
        cid,
        me["id"],
        ["CrowdStrike Falcon"],
        vendor="CrowdStrike",
        category="Endpoint Security",
        security_functions=["detect", "respond"],
    )
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    svc_id = svc.json()["id"]
    c.post(f"/attack/services/{svc_id}/assessments", headers=h)
    seen = _capture_payload(provider)

    assert c.post(f"/attack/services/{svc_id}/run-ai", headers=h).status_code == 200

    entry = seen[0]["capability_list"][0]
    assert entry["name"] == "CrowdStrike Falcon"
    assert entry["vendor"] == "CrowdStrike"
    assert entry["category"] == "Endpoint Security"
    assert entry["security_functions"] == ["detect", "respond"]


@pytest.mark.unit
def test_payload_names_are_exactly_the_allow_list(app_client) -> None:
    """The invariant. If these drift, the model is offered tools it may not cite.

    `valid_tools` is a HARD allow-list — a citation outside it is dropped and the
    technique reads as uncovered. So every name in the payload must be in the
    allow-list and vice versa, by construction rather than by coincidence.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Splunk", "Okta", "  Padded  "])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    svc_id = svc.json()["id"]
    c.post(f"/attack/services/{svc_id}/assessments", headers=h)
    seen = _capture_payload(provider)

    body = c.post(f"/attack/services/{svc_id}/run-ai", headers=h).json()
    names = {e["name"] for e in seen[0]["capability_list"]}

    assert names == {"Splunk", "Okta", "Padded"}, "names must be stripped, as the allow-list is"
    # tools_available counts distinct NAMES, not payload entries or dicts.
    assert body["tools_available"] == 3


@pytest.mark.unit
def test_a_cited_vendor_resolves_to_the_product_it_can_only_mean(app_client) -> None:
    """The risk enrichment introduces, and how it is now handled.

    CONTRACT CHANGED 2026-08-08. This test previously asserted that a vendor-only
    citation was DROPPED. Dropping was the wrong answer: the technique then read
    as a gap, and "gap" in a client report cannot mean "the model phrased the
    name wrong". A near miss is now RESOLVED when it can only mean one thing.

    Handing the model `vendor` and `category` gives it three plausible strings
    per tool where it had one, so this path got more likely, not less. What must
    still hold: an unresolvable string ("Endpoint Security" names no product
    here) is refused, and the resolved and exact citations collapse to ONE tool
    rather than inflating coverage.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(
        TestSession,
        cid,
        me["id"],
        ["CrowdStrike Falcon"],
        vendor="CrowdStrike",
        category="Endpoint Security",
    )
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    svc_id = svc.json()["id"]
    a = c.post(f"/attack/services/{svc_id}/assessments", headers=h)
    code = a.json()["coverage"][0]["technique_code"]

    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": [{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["CrowdStrike", "Endpoint Security",'
            ' "CrowdStrike Falcon"], "prevention_tools": [], "response_tools": []}]}'
        ),
    )
    body = c.post(f"/attack/services/{svc_id}/run-ai", headers=h).json()
    row = next(t for t in body["coverage"] if t["technique_code"] == code)
    # "CrowdStrike" resolved to the one product it can mean; "CrowdStrike Falcon"
    # matched exactly; the two collapse. "Endpoint Security" resolved to nothing.
    assert row["detection_tools"] == ["CrowdStrike Falcon"]
    # Counted per citation event, and the static fixture answers every batch, so
    # assert the RELATIONSHIP rather than a batch-count-dependent number.
    assert body["citations_normalized"] > 0, "the vendor citation was resolved, not dropped"
    assert body["citations_rejected"] > 0, "the category names no product and stays refused"
    assert (
        body["citations_normalized"] == body["citations_rejected"]
    ), "one resolved vendor and one refused category per response"


@pytest.mark.unit
def test_notes_and_cost_never_egress(app_client) -> None:
    """A security boundary, not a preference.

    `notes` is free-text consultant commentary and the highest-PII field on the
    row; cost and licence counts are commercially sensitive and useless for
    mapping. Redaction is a compensating control, not a licence to widen what
    leaves the building.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(
        TestSession,
        cid,
        me["id"],
        ["Splunk"],
        notes="Renewal owner is Jane Doe, jane@acme.example — see contract 88231",
        annual_cost_usd=200000,
    )
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    svc_id = svc.json()["id"]
    c.post(f"/attack/services/{svc_id}/assessments", headers=h)
    seen = _capture_payload(provider)

    assert c.post(f"/attack/services/{svc_id}/run-ai", headers=h).status_code == 200

    blob = json.dumps(seen[0])
    assert "Jane Doe" not in blob
    assert "jane@acme.example" not in blob
    assert "88231" not in blob
    assert "200000" not in blob
    assert seen[0]["capability_list"] == [{"name": "Splunk"}], "empty fields are omitted"


@pytest.mark.unit
def test_every_batch_receives_the_same_capability_list(app_client) -> None:
    """The list is re-sent per batch; all batches must agree on the allow-list."""
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Splunk"], vendor="Splunk Inc")
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    svc_id = svc.json()["id"]
    c.post(f"/attack/services/{svc_id}/assessments", headers=h)
    seen = _capture_payload(provider)

    assert c.post(f"/attack/services/{svc_id}/run-ai", headers=h).status_code == 200

    assert len(seen) > 1, "the full matrix must batch"
    first = seen[0]["capability_list"]
    assert all(p["capability_list"] == first for p in seen)
