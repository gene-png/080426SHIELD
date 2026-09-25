"""mitre_map Run-AI: D/P/R suggestions, tool validation, lock-skip (Work Order D2)."""

from __future__ import annotations

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
            title="Acme Tech Debt",
            client_id=_uuid.UUID(cid),
            opened_by=_uuid.UUID(user_id),
        )
        db.add(svc)
        db.flush()
        cl = CapabilityList(service_id=svc.id, version=1, status=CapabilityListStatus.APPROVED)
        db.add(cl)
        db.flush()
        for name in tools:
            db.add(
                CapabilityItem(
                    capability_list_id=cl.id,
                    name=name,
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


@pytest.mark.unit
def test_run_ai_non_list_techniques_is_an_error_not_a_silent_empty_run(app_client) -> None:
    """A non-list `techniques` must be refused, not treated as "nothing to say".

    `attack.py` reads `(data.get("techniques") or [])`, so a scalar collapsed to
    an empty list and the run reported zero changes — indistinguishable from a
    model that genuinely had no suggestions. That is a default-value fallback on
    a bad shape, which FAIL LOUDLY forbids, and it is the same defect
    `parse_json_object_with_list` was written to close for csf_score (#41) and
    zt_score (D-047).

    Note what this does NOT do. mitre_map is BATCHED, and `run_ai` counts a
    failed batch and continues, raising only when every batch failed. So one
    malformed batch of 26 still returns 200 with `batches_failed=1`, and that
    field is now rendered in the web app by `AttackCitationAccounting`
    (#115): a partial run raises a role=alert naming the failed-batch
    count. It was rendered nowhere when this docstring was written, and
    F7 recorded that gap; this test still covers the all-batches-fail
    path only, which is a different case from the partial one.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "Acme ATT&CK"}
    ).json()["id"]
    c.post(f"/attack/services/{svc_id}/assessments", headers=h)

    provider.register_static("mitre_map", LLMResponse('{"techniques": 0}'))
    r = c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 502, r.text
    assert r.json()["error"]["reason"] == "ai_call_failed"
    assert "drifted apart" in r.json()["error"]["message"]


@pytest.mark.unit
def test_run_ai_object_techniques_is_refused_not_iterated_as_keys(app_client) -> None:
    """The subtler half: a dict is TRUTHY, so `or []` did not catch it.

    `for t in {"T1003": ...}` iterates the KEYS — strings — which the
    `isinstance(t, dict)` filter then discards one by one. Zero changes, no
    error, no trace. A scalar at least had the decency to be falsy.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "Acme ATT&CK"}
    ).json()["id"]
    c.post(f"/attack/services/{svc_id}/assessments", headers=h)

    provider.register_static(
        "mitre_map", LLMResponse('{"techniques": {"T1003": {"status": "covered"}}}')
    )
    r = c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 502, r.text
    assert r.json()["error"]["reason"] == "ai_call_failed"


# --- W2: citations are resolved and ACCOUNTED FOR, not silently dropped -----


def _run_with_citations(c, TestSession, tools: list[str], cited: list[str]) -> dict:
    """One technique, `cited` as its detection_tools, against `tools`."""
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], tools)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"}
    ).json()["id"]
    code = c.post(f"/attack/services/{svc_id}/assessments", headers=h).json()["coverage"][0][
        "technique_code"
    ]
    import json as _json

    provider = c.app.dependency_overrides  # noqa: F841 - provider set by fixture
    return (
        code,
        svc_id,
        h,
        _json.dumps(
            {
                "techniques": [
                    {
                        "technique_code": code,
                        "status": "covered",
                        "detection_tools": cited,
                        "prevention_tools": [],
                        "response_tools": [],
                        "rationale": "r",
                    }
                ]
            }
        ),
    )


@pytest.mark.unit
def test_a_near_miss_citation_is_resolved_and_flagged_not_dropped(app_client) -> None:
    """The defect this exists to close.

    Exact match dropped "CrowdStrike" against `CrowdStrike Falcon Enterprise`
    silently: no count, no reason, and the technique kept its `covered` status
    with an EMPTY tool list. A reader cannot tell that from a client who owns
    nothing.
    """
    c, TestSession, provider = app_client
    code, svc_id, h, payload = _run_with_citations(
        c, TestSession, ["CrowdStrike Falcon Enterprise"], ["CrowdStrike"]
    )
    provider.register_static("mitre_map", LLMResponse(payload))

    body = c.post(f"/attack/services/{svc_id}/run-ai", headers=h).json()
    row = next(t for t in body["coverage"] if t["technique_code"] == code)
    assert row["detection_tools"] == ["CrowdStrike Falcon Enterprise"], "the citation was dropped"
    # `mitre_map` runs concurrent BATCHES and the fixture answers each one with
    # the same payload, so this citation is resolved once per batch. Pin the
    # count to `batches_total` rather than `> 0`: the first version asserted
    # `> 0`, which cannot tell 1 from 26 from 500, so a real inflation of the
    # number shown on the panel would never have failed a test.
    assert body["citations_confirmed"] == 0
    assert body["citations_needs_review"] == body["batches_total"]
    assert body["citations_rejected"] == 0
    assert body["citations_needs_review_tools"] == ["CrowdStrike Falcon Enterprise"]


@pytest.mark.unit
def test_an_exact_citation_is_confirmed_not_flagged(app_client) -> None:
    """#11: a verbatim citation must not be reported as a near miss. With the
    counter surfaced, that is a false statement a consultant can act on."""
    c, TestSession, provider = app_client
    code, svc_id, h, payload = _run_with_citations(c, TestSession, ["Tenable.io"], ["Tenable.io"])
    provider.register_static("mitre_map", LLMResponse(payload))

    body = c.post(f"/attack/services/{svc_id}/run-ai", headers=h).json()
    assert body["citations_confirmed"] == body["batches_total"]
    assert body["citations_needs_review"] == 0, "a verbatim citation was called an inference"


@pytest.mark.unit
def test_an_unknown_citation_is_counted_and_quoted_verbatim(app_client) -> None:
    c, TestSession, provider = app_client
    code, svc_id, h, payload = _run_with_citations(
        c, TestSession, ["Splunk Enterprise"], ["Qradar"]
    )
    provider.register_static("mitre_map", LLMResponse(payload))

    body = c.post(f"/attack/services/{svc_id}/run-ai", headers=h).json()
    row = next(t for t in body["coverage"] if t["technique_code"] == code)
    assert row["detection_tools"] == []
    assert body["citations_rejected"] == body["batches_total"]
    assert body["citations_rejected_examples"] == ["Qradar"]
    assert body["citations_confirmed"] == 0


@pytest.mark.unit
def test_an_ambiguous_citation_is_refused_rather_than_attributed(app_client) -> None:
    """Two Splunk products. The accuracy tiebreak: a dropped citation is counted
    and visible, a wrong attribution is invisible and reaches the client."""
    c, TestSession, provider = app_client
    code, svc_id, h, payload = _run_with_citations(
        c, TestSession, ["Splunk Enterprise", "Splunk Phantom"], ["Splunk"]
    )
    provider.register_static("mitre_map", LLMResponse(payload))

    body = c.post(f"/attack/services/{svc_id}/run-ai", headers=h).json()
    row = next(t for t in body["coverage"] if t["technique_code"] == code)
    assert row["detection_tools"] == []
    assert body["citations_rejected"] == body["batches_total"]
    assert body["citations_needs_review"] == 0, "guessed between two Splunk products"


@pytest.mark.unit
def test_a_rejected_citation_leaves_the_status_the_model_gave_it(app_client) -> None:
    """The consequence the panel has to describe honestly.

    `run_ai` assigns `row.status` independently of what happens to that row's
    citations, so a technique whose every citation was rejected keeps `covered`
    with an EMPTY tool list and carries full weight in coverage_pct and the
    client PDF. The panel used to say such a technique "reads as uncovered",
    which is the inverse — and understated the harm, because the real risk is
    coverage OVERSTATED with nothing behind it.

    Pinned so the copy and the behaviour cannot drift apart again. 5.1's
    `pending_review` enforcement is the fix and is not in W2.
    """
    c, TestSession, provider = app_client
    code, svc_id, h, payload = _run_with_citations(
        c, TestSession, ["Splunk Enterprise"], ["Qradar"]
    )
    provider.register_static("mitre_map", LLMResponse(payload))

    body = c.post(f"/attack/services/{svc_id}/run-ai", headers=h).json()
    row = next(t for t in body["coverage"] if t["technique_code"] == code)
    assert row["detection_tools"] == []
    assert row["status"] == "covered", (
        "if this ever becomes 'gap' or a pending state, 5.1 landed and the panel "
        "copy must be revisited"
    )
    assert body["citations_rejected"] > 0


@pytest.mark.unit
def test_a_wrong_shaped_tool_list_is_counted_not_silently_dropped(app_client) -> None:
    """A bare string where a list belongs overwrote the row's tools with [] and
    reported nothing — indistinguishable from the model citing nothing."""
    import json as _json

    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Splunk Enterprise"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"}
    ).json()["id"]
    code = c.post(f"/attack/services/{svc_id}/assessments", headers=h).json()["coverage"][0][
        "technique_code"
    ]
    provider.register_static(
        "mitre_map",
        LLMResponse(
            _json.dumps(
                {
                    "techniques": [
                        {
                            "technique_code": code,
                            "status": "covered",
                            "detection_tools": "Splunk Enterprise",
                            "rationale": "r",
                        }
                    ]
                }
            )
        ),
    )
    body = c.post(f"/attack/services/{svc_id}/run-ai", headers=h).json()
    assert body["citations_unusable"] > 0, "a wrong-shaped tool list vanished uncounted"

    # #109. The COUNTER above was green before the per-row record existed -- it
    # is what the issue says already worked. This is the half that was missing,
    # and it is asserted HERE, through the route response, because that is the
    # surface the panel reads. Every other assertion about `unusable_details`
    # either calls `resolve_citations` directly or hand-builds the entry, so
    # deleting the two lines in `_validate_tools` that turn one into the other
    # left the whole suite green. CLAUDE.md: the assertion has to go red through
    # the surface the client actually reaches.
    row = next(r for r in body["coverage"] if r["technique_code"] == code)
    assert row["unconfirmed_citations"] == [
        {
            "tool": None,
            "cited": "Splunk Enterprise",
            "reason": "unusable_field",
            "field": "detection_tools",
            "cleared_at": None,
        }
    ], row["unconfirmed_citations"]

    # AND the marker it DISPLACED. Before #109 this row carried a `no_citation`
    # entry -- the merge block writes one only when `merged` is empty, and the
    # unusable entry now fills it. The row is still withheld, by
    # `has_uncleared_evidence` over the new entry rather than by the mechanism
    # `pending.py` names. That is a real behaviour change and it is pinned so it
    # reads as a decision rather than as something nobody noticed.
    assert not any(e["reason"] == "no_citation" for e in row["unconfirmed_citations"])
    assert row["pending_review"] is True


@pytest.mark.unit
def test_the_same_tool_spelled_two_ways_across_lists_is_not_made_ambiguous(app_client) -> None:
    """A regression the audit caught before it shipped.

    A client can have two Tech Debt lists, one extracted from an all-caps table,
    so the allow-list holds both `Splunk` and `SPLUNK`. Deduping on the exact
    string kept both, `_by_norm["splunk"]` then held two names, and the resolver
    called the citation AMBIGUOUS and rejected it — while `main`'s
    `frozenset(t.lower() ...)` collapsed the pair and kept it. The client would
    have lost evidence they used to get, and the panel would have said the tool
    "is not on the list" when it is on it twice.
    """
    import uuid as _uuid

    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Splunk"])

    # A second list for the same client, same tool, different casing.
    with TestSession() as db:
        svc = Service(
            kind=ServiceKind.TECH_DEBT,
            status=ServiceStatus.IN_PROGRESS,
            title="Second inventory",
            client_id=_uuid.UUID(cid),
            opened_by=_uuid.UUID(me["id"]),
        )
        db.add(svc)
        db.flush()
        cl = CapabilityList(service_id=svc.id, version=1, status=CapabilityListStatus.APPROVED)
        db.add(cl)
        db.flush()
        db.add(CapabilityItem(capability_list_id=cl.id, name="SPLUNK"))
        db.commit()

    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"}
    ).json()["id"]
    code = c.post(f"/attack/services/{svc_id}/assessments", headers=h).json()["coverage"][0][
        "technique_code"
    ]
    import json as _json

    provider.register_static(
        "mitre_map",
        LLMResponse(
            _json.dumps(
                {
                    "techniques": [
                        {
                            "technique_code": code,
                            "status": "covered",
                            "detection_tools": ["Splunk"],
                            "rationale": "r",
                        }
                    ]
                }
            )
        ),
    )
    body = c.post(f"/attack/services/{svc_id}/run-ai", headers=h).json()
    row = next(t for t in body["coverage"] if t["technique_code"] == code)
    assert row["detection_tools"] != [], "a citation main would have kept was rejected"
    assert body["citations_rejected"] == 0


@pytest.mark.unit
def test_every_batched_mitre_map_call_carries_the_requests_correlation_id(app_client) -> None:
    """The batch workers ran without the request's context, so `llm_calls`
    rows lost the correlation id every other row in the request carries.

    Measured on the dev stack 2026-09-23: 0 of 52 live `mitre_map` rows had
    one, against 4 of 4 `extract.capabilities` and 1 of 1 `zt_score` -- the
    unbatched jobs. Without it a coverage edit cannot be joined to the LLM
    calls that produced it, which is the provenance join `audit_entries` and
    `llm_calls` both carry the column for.
    """
    from sqlalchemy import select

    from app.models.llm_call import LLMCall

    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "Acme ATT&CK"}
    ).json()["id"]
    c.post(f"/attack/services/{svc_id}/assessments", headers=h)
    provider.register_static("mitre_map", LLMResponse('{"techniques": []}'))

    r = c.post(
        f"/attack/services/{svc_id}/run-ai",
        headers={**h, "X-Request-ID": "corr-mitre-batches"},
    )
    assert r.status_code == 200, r.text
    assert r.headers["X-Request-ID"] == "corr-mitre-batches"

    with TestSession() as db:
        ids = (
            db.execute(select(LLMCall.correlation_id).where(LLMCall.purpose == "mitre_map"))
            .scalars()
            .all()
        )
    # More than one row, or this proves nothing about the WORKERS: a single
    # batch could in principle run on the request thread.
    assert len(ids) > 1, ids
    assert set(ids) == {"corr-mitre-batches"}, ids


def _one_row_run(c, TestSession, provider, status: str) -> tuple[dict, str, str]:
    """A service with one approved tool, an assessment, and a static AI answer
    giving the first technique `status`. Returns headers, service id, row id."""
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Tool A"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "ATT&CK"}
    ).json()["id"]
    row = c.post(f"/attack/services/{svc_id}/assessments", headers=h).json()["coverage"][0]
    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": [{"technique_code": "' + row["technique_code"] + '", '
            '"status": "' + status + '", "detection_tools": [], "prevention_tools": [], '
            '"response_tools": [], "rationale": "r"}]}'
        ),
    )
    return h, svc_id, row["id"]


@pytest.mark.unit
def test_run_ai_drops_a_reason_the_new_status_does_not_take(app_client) -> None:
    """#554: the PATCH drops a reason that no longer fits its status, and the AI
    write-back must too, or a consultant's `missing_control_category` survives
    under the AI's N/A -- the exact pairing the vocabulary forbids."""
    c, TestSession, provider = app_client
    h, svc_id, row_id = _one_row_run(c, TestSession, provider, "not_applicable")
    r = c.patch(
        f"/attack/coverage/{row_id}",
        headers=h,
        json={"status": "partial", "reason_code": "missing_control_category"},
    )
    assert r.status_code == 200, r.text

    r = c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    row = next(t for t in r.json()["coverage"] if t["id"] == row_id)
    assert (row["status"], row["reason_code"]) == ("not_applicable", None)

    # DISCLOSED, not only dropped: in the run's own diff and in the audit row.
    code = row["technique_code"]
    changed = {
        ch["field"]: (ch["old"], ch["new"])
        for ch in r.json()["changed"]
        if ch["technique_code"] == code
    }
    assert changed["reason_code"] == ("missing_control_category", None), changed

    from sqlalchemy import select

    from app.models.audit_entry import AuditEntry

    with TestSession() as db:
        details = (
            db.execute(select(AuditEntry.details).where(AuditEntry.action == "attack.run_ai"))
            .scalars()
            .one()
        )
    assert details["reason_codes_dropped"] == [
        {"technique_code": code, "reason_code": "missing_control_category"}
    ]


@pytest.mark.unit
@pytest.mark.parametrize("status", ["unable_to_determine", "outside_control_surface"])
def test_run_ai_does_not_write_a_status_no_surface_reports(app_client, status) -> None:
    """#554: the AI's allowed set is the four the prompt offers, not the whole
    enum, so a model answer outside it leaves the row as it was."""
    c, TestSession, provider = app_client
    h, svc_id, row_id, code = _one_row_run_with_reason(c, TestSession, provider, status, None)
    r = c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    row = next(t for t in r.json()["coverage"] if t["id"] == row_id)
    # Refused WHOLE (#590 round 2): no status, and none of the suggestion's
    # tools or rationale -- a rationale arguing for a status the row does not
    # have is what the old skip left behind.
    assert row["status"] is None
    assert not row["detection_tools"]
    assert row["rationale"] != _SUGGESTED_RATIONALE
    rejected = _run_audit(TestSession)["statuses_rejected"]
    assert rejected and all(e == {"technique_code": code, "status": status} for e in rejected)


_SUGGESTED_RATIONALE = "SUGGESTED-RATIONALE-that-must-not-land-on-a-refused-row"


def _one_row_run_with_reason(c, TestSession, provider, status: str, reason) -> tuple:
    """As `_one_row_run`, with the model also offering `reason_code`."""
    import json

    h, svc_id, row_id = _one_row_run(c, TestSession, provider, status)
    code = next(
        t["technique_code"]
        for t in c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json()[
            "coverage"
        ]
        if t["id"] == row_id
    )
    provider.register_static(
        "mitre_map",
        LLMResponse(
            json.dumps(
                {
                    "techniques": [
                        {
                            "technique_code": code,
                            "status": status,
                            "reason_code": reason,
                            # Cited and argued, so a refusal that let the tools
                            # or the rationale through is visible on the row.
                            "detection_tools": ["Tool A"],
                            "prevention_tools": [],
                            "response_tools": [],
                            "rationale": _SUGGESTED_RATIONALE,
                        }
                    ]
                }
            )
        ),
    )
    return h, svc_id, row_id, code


def _run_audit(TestSession) -> dict:
    from sqlalchemy import select

    from app.models.audit_entry import AuditEntry

    with TestSession() as db:
        return (
            db.execute(select(AuditEntry.details).where(AuditEntry.action == "attack.run_ai"))
            .scalars()
            .one()
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "reason"),
    [("partial", "reach_limited"), ("not_applicable", "platform_absent")],
)
def test_run_ai_stores_a_reason_the_status_takes(app_client, status, reason) -> None:
    """#554 slice 2: the model's reason is stored when it belongs to the status."""
    c, TestSession, provider = app_client
    h, svc_id, row_id, _ = _one_row_run_with_reason(c, TestSession, provider, status, reason)
    r = c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    row = next(t for t in r.json()["coverage"] if t["id"] == row_id)
    assert (row["status"], row["reason_code"]) == (status, reason)
    assert _run_audit(TestSession)["reason_codes_rejected"] == []


_PRIOR_PARTIAL = {"status": "partial", "reason_code": "detection_weak"}
_PRIOR_GAP = {"status": "gap", "reason_code": None}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "reason", "recorded", "prior"),
    [
        # The pairing the vocabulary exists to forbid: a missing control is a
        # GAP, never an N/A reason. Applying the N/A would move the row out of
        # the gap list on the model's word.
        ("not_applicable", "missing_control_category", "missing_control_category", _PRIOR_PARTIAL),
        ("partial", "platform_absent", "platform_absent", _PRIOR_GAP),
        ("gap", "reach_limited", "reach_limited", _PRIOR_PARTIAL),
        ("partial", "not_a_code", "not_a_code", _PRIOR_GAP),
        # Model PROSE never reaches an audit row: a marker stands in for it.
        ("partial", "Nothing defends this. See notes!", "<not a code>", _PRIOR_GAP),
    ],
)
def test_run_ai_refuses_a_mispaired_suggestion_whole_and_records_it(
    app_client, status, reason, recorded, prior
) -> None:
    """As the PATCH refuses the whole request (typed 422), the write-back refuses
    the whole suggestion: the row keeps the consultant's status AND reason, and
    the audit row names what was refused. Every case starts from a prior status
    DIFFERENT from the suggestion, or applying the status would change nothing
    and the case could not fail (review round 2)."""
    c, TestSession, provider = app_client
    h, svc_id, row_id, code = _one_row_run_with_reason(c, TestSession, provider, status, reason)
    assert prior["status"] != status
    before = c.patch(f"/attack/coverage/{row_id}", headers=h, json=prior)
    assert before.status_code == 200, before.text
    kept = {k: before.json()[k] for k in ("detection_tools", "rationale")}

    r = c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    row = next(t for t in r.json()["coverage"] if t["id"] == row_id)
    assert (row["status"], row["reason_code"]) == (prior["status"], prior["reason_code"])
    # WHOLE: the suggestion's tools and rationale did not land either.
    assert {k: row[k] for k in kept} == kept
    assert row["rationale"] != _SUGGESTED_RATIONALE
    # The static answer is replayed to EVERY batch, so the refusal is recorded
    # once per batch that saw it. What is pinned is that it IS recorded, whole,
    # and nothing else is.
    rejected = _run_audit(TestSession)["reason_codes_rejected"]
    assert rejected, "a refused suggestion must be recorded, not silently dropped"
    assert all(
        entry == {"technique_code": code, "status": status, "reason_code": recorded}
        for entry in rejected
    ), rejected
