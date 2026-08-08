"""GET /attack/services/{id}/ai-inputs — what feeds the mapping.

The ATT&CK workspace reported one number — `23 tools available` — and only AFTER
the run. An admin could not see which capabilities were in play, or which
document they came from. That is how a run with ZERO capabilities wrote 607
fabricated gaps across 633 techniques on 2026-08-07: a catastrophic-looking
posture that was purely an artifact of no inventory being loaded (N-033).

These tests pin the disclosure. Note what it is NOT: it never gates Run AI — the
typed 409 in `run_ai` remains the only guard — and it answers with zero rather
than refusing, because reporting "nothing will be sent" is the entire point.

The fixture and seed helper are imported from `test_attack_run_ai` so the two
files cannot drift on how a capability list is built.
"""

from __future__ import annotations

import pytest

from app.ai.llm import LLMResponse

from .test_attack_run_ai import _admin, _seed_tech_debt_tools, app_client  # noqa: F401


def _attack_service(c, headers) -> str:
    return c.post(
        "/attack/services",
        headers=headers,
        json={"kind": "attack_coverage", "title": "ATT&CK"},
    ).json()["id"]


@pytest.mark.unit
def test_lists_the_capabilities_and_their_provenance(app_client) -> None:  # noqa: F811
    c, TestSession, _provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(
        TestSession,
        cid,
        me["id"],
        ["CrowdStrike Falcon"],
        vendor="CrowdStrike",
        category="Endpoint Security",
        security_functions=["detect"],
    )
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = _attack_service(c, h)

    r = c.get(f"/attack/services/{svc_id}/ai-inputs", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["tools_sent"] == 1
    item = body["items"][0]
    assert item["name"] == "CrowdStrike Falcon"
    assert item["vendor"] == "CrowdStrike"
    assert item["security_functions"] == ["detect"]
    assert body["lists"][0]["version"] == 1
    # No artifact was attached to the row, so the gap is REPORTED, not hidden.
    assert body["items_without_source_document"] == 1
    assert body["documents"] == []


@pytest.mark.unit
def test_answers_before_an_assessment_exists(app_client) -> None:  # noqa: F811
    """The reason this is not part of /ai/preview.

    "What will this run against?" is asked BEFORE creating an assessment. The
    preview route 404s in that state; this must not.
    """
    c, TestSession, _provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Splunk"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = _attack_service(c, h)

    r = c.get(f"/attack/services/{svc_id}/ai-inputs", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["tools_sent"] == 1


@pytest.mark.unit
def test_reports_zero_rather_than_refusing(app_client) -> None:  # noqa: F811
    """Disclosure, not a guard. "Nothing will be sent" is the finding."""
    c, _TestSession, _provider = app_client
    bearer, cid = _admin(c)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = _attack_service(c, h)

    r = c.get(f"/attack/services/{svc_id}/ai-inputs", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["tools_sent"] == 0
    assert r.json()["items"] == []


@pytest.mark.unit
def test_flags_a_superseded_list_that_still_contributes(app_client) -> None:  # noqa: F811
    """Every non-discarded version feeds the mapping, which routinely surprises.

    A tool dropped in v2 is STILL offered to the model from v1. This change does
    not alter that behaviour; it makes it visible.
    """
    c, TestSession, _provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Retired Tool"], title="Debt A", version=1)
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Current Tool"], title="Debt B", version=2)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = _attack_service(c, h)

    body = c.get(f"/attack/services/{svc_id}/ai-inputs", headers=h).json()
    assert body["tools_sent"] == 2, "both versions still contribute — that is the point"
    assert len(body["lists"]) == 2


@pytest.mark.unit
def test_excludes_a_confirmed_non_security_row(app_client) -> None:  # noqa: F811
    """The security-scope rule, seen from the ATT&CK side."""
    c, TestSession, _provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Splunk"], title="Sec")
    _seed_tech_debt_tools(
        TestSession,
        cid,
        me["id"],
        ["Figma"],
        title="Design",
        security_related=False,
        confirmed=True,
    )
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = _attack_service(c, h)

    body = c.get(f"/attack/services/{svc_id}/ai-inputs", headers=h).json()
    assert [i["name"] for i in body["items"]] == ["Splunk"]


@pytest.mark.unit
def test_marks_an_unconfirmed_negative_as_awaiting_signoff(app_client) -> None:  # noqa: F811
    """Provisional negatives stay IN scope and are flagged, not hidden.

    That is the design of `security_scope`: an unreviewed "not security" costs a
    consultant one glance, while dropping it silently creates a blind spot nobody
    ever sees.
    """
    c, TestSession, _provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(
        TestSession, cid, me["id"], ["Maybe Security"], security_related=False, confirmed=False
    )
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = _attack_service(c, h)

    body = c.get(f"/attack/services/{svc_id}/ai-inputs", headers=h).json()
    assert body["tools_sent"] == 1
    assert body["items"][0]["awaiting_signoff"] is True
    assert body["awaiting_signoff_count"] == 1


@pytest.mark.unit
def test_count_matches_what_run_ai_reports(app_client) -> None:  # noqa: F811
    """Anti-drift: the panel and the run must never disagree about the count."""
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Splunk", "Okta"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = _attack_service(c, h)
    c.post(f"/attack/services/{svc_id}/assessments", headers=h)
    provider.register_static("mitre_map", LLMResponse('{"techniques": []}'))

    shown = c.get(f"/attack/services/{svc_id}/ai-inputs", headers=h).json()["tools_sent"]
    ran = c.post(f"/attack/services/{svc_id}/run-ai", headers=h).json()["tools_available"]
    assert shown == ran == 2


@pytest.mark.unit
def test_is_admin_only(app_client) -> None:  # noqa: F811
    c, TestSession, _provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Splunk"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = _attack_service(c, h)

    other = c.post(
        "/auth/register",
        json={
            "email": "client@acme.example",
            "password": "correct horse battery staple!",
            "display_name": "C",
        },
    )
    r = c.get(
        f"/attack/services/{svc_id}/ai-inputs",
        headers={
            "Authorization": f"Bearer {other.json()['tokens']['access_token']}",
            "X-Client-Id": cid,
        },
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# Only an APPROVED list feeds the mapping (2026-08-08).
#
# A DRAFT list is raw extraction output nobody has vouched for. On 2026-08-08 a
# draft produced by a malformed-upload TEST contributed four bare vendor stubs
# ("CrowdStrike", "Splunk", ...) to a real client's allow-list, and a live run
# attributed 765 citations across 361 techniques to them instead of the licensed
# products. Approval is the only gate that excludes an unreviewed file: the
# malformed list was the LATEST version, so a "newest version wins" rule would
# have kept it and dropped the approved one.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_draft_list_does_not_feed_the_mapping(app_client) -> None:  # noqa: F811
    c, TestSession, _provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(
        TestSession, cid, me["id"], ["Reviewed Tool"], title="Approved", status="APPROVED"
    )
    _seed_tech_debt_tools(
        TestSession, cid, me["id"], ["Unreviewed Stub"], title="Draft", status="DRAFT"
    )
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = _attack_service(c, h)

    body = c.get(f"/attack/services/{svc_id}/ai-inputs", headers=h).json()
    assert [i["name"] for i in body["items"]] == ["Reviewed Tool"]
    assert body["tools_sent"] == 1


@pytest.mark.unit
def test_a_released_list_still_feeds_the_mapping(app_client) -> None:  # noqa: F811
    """RELEASED is past approval, not short of it."""
    c, TestSession, _provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(
        TestSession, cid, me["id"], ["Released Tool"], title="Rel", status="RELEASED"
    )
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = _attack_service(c, h)

    assert c.get(f"/attack/services/{svc_id}/ai-inputs", headers=h).json()["tools_sent"] == 1


@pytest.mark.unit
def test_excluded_drafts_are_reported_not_silent(app_client) -> None:  # noqa: F811
    """Starting ATT&CK before Tech Debt is finalised is a normal order of work.

    Excluding drafts silently would make those capabilities simply missing, with
    no way to tell that from "the client does not own them" — the same
    indistinguishability that makes a fabricated gap dangerous. The consultant is
    told what is being held back and why.
    """
    c, TestSession, _provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(
        TestSession, cid, me["id"], ["Reviewed"], title="Approved", status="APPROVED"
    )
    _seed_tech_debt_tools(
        TestSession, cid, me["id"], ["Pending A", "Pending B"], title="Draft", status="DRAFT"
    )
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = _attack_service(c, h)

    body = c.get(f"/attack/services/{svc_id}/ai-inputs", headers=h).json()
    assert body["tools_sent"] == 1
    assert body["draft_excluded_count"] == 2
    assert body["draft_lists_count"] == 1
