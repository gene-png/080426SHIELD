"""Reopening a frozen ATT&CK assessment — the repair path that did not exist.

Approving an assessment freezes it: coverage rows reject edits with 409 "This
assessment is locked", Run AI refuses, and discard accepts DRAFT only. There was
no unapprove endpoint, so an admin who generated a deliverable and then spotted a
mistake had exactly one option — mint a NEW assessment version with 633 fresh
unscored rows, discarding every score and paying for another live AI run.

That dead end matters more once generating a document freezes the assessment
implicitly, because freezing then happens as a side effect of the REVIEW action
rather than as a deliberate click.

The safety line is `deliverable.released_at`, NOT the assessment status. Nothing
in the ATT&CK routes ever assigns `AttackAssessmentStatus.RELEASED` — releasing
sets `released_at` on the deliverable — so a guard keyed on assessment status
would never fire and would cheerfully reopen an assessment whose report is
already with the client. Once a document has gone out, the assessment behind it
must stay frozen forever: that is the point-in-time guarantee a client-facing
report rests on.
"""

from __future__ import annotations

import uuid as _uuid

import pytest

from app.ai.llm import LLMResponse
from app.models._common import utcnow
from app.models.attack_assessment import AttackAssessment, AttackAssessmentStatus
from app.models.deliverable import Deliverable

from .test_attack_run_ai import _admin, _seed_tech_debt_tools, app_client  # noqa: F401

# WRITTEN AHEAD OF THE ENDPOINT. `POST /attack/assessments/{id}/reopen` does not
# exist yet, so every test here currently fails with 404 — this is the contract,
# committed so it is not lost between sessions.
#
# `strict=True` is doing real work and must NOT be softened to `skip`. A skipped
# spec rots silently and reads as passing (CLAUDE.md: "a spec that self-skips is
# UNTESTED, not passing"). Strict xfail is self-cleaning instead: the moment the
# endpoint lands these XPASS, strict turns an unexpected pass into a FAILURE, and
# the suite forces whoever implemented it to delete this marker. The breadcrumb
# removes itself rather than waiting to be noticed.
#
# Implementation notes live in the plan file, Part 3. The one that matters: the
# already-released guard keys on `Deliverable.released_at`, NOT on assessment
# status — nothing ever assigns AttackAssessmentStatus.RELEASED, so a
# status-keyed guard would compile, pass review, and never fire.
pytestmark = pytest.mark.xfail(
    reason="POST /attack/assessments/{id}/reopen is not implemented yet (plan Part 3)",
    strict=True,
)


def _approved_assessment(c, TestSession, bearer: str, cid: str) -> tuple[str, str]:
    """A service with an APPROVED (frozen) assessment. Returns (service_id, assessment_id)."""
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Splunk"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"}
    ).json()["id"]
    a = c.post(f"/attack/services/{svc_id}/assessments", headers=h).json()
    approved = c.post(f"/attack/assessments/{a['id']}/approve", headers=h)
    assert approved.status_code == 200, approved.text
    return svc_id, a["id"]


@pytest.mark.unit
def test_reopen_returns_a_frozen_assessment_to_draft(app_client) -> None:  # noqa: F811
    c, TestSession, _provider = app_client
    bearer, cid = _admin(c)
    svc_id, a_id = _approved_assessment(c, TestSession, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}

    r = c.post(f"/attack/assessments/{a_id}/reopen", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "draft"
    # Any deliverable already generated no longer matches the assessment.
    assert r.json()["documents_stale"] is True


@pytest.mark.unit
def test_reopening_restores_the_ability_to_edit(app_client) -> None:  # noqa: F811
    """The whole point: a mistake costs one click, not a whole re-assessment."""
    c, TestSession, _provider = app_client
    bearer, cid = _admin(c)
    svc_id, a_id = _approved_assessment(c, TestSession, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    latest = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json()
    cov_id = latest["coverage"][0]["id"]

    # Frozen: the edit is refused.
    blocked = c.patch(f"/attack/coverage/{cov_id}", headers=h, json={"status": "covered"})
    assert blocked.status_code == 409, blocked.text

    assert c.post(f"/attack/assessments/{a_id}/reopen", headers=h).status_code == 200

    allowed = c.patch(f"/attack/coverage/{cov_id}", headers=h, json={"status": "covered"})
    assert allowed.status_code == 200, allowed.text


@pytest.mark.unit
def test_reopening_restores_the_ability_to_re_run_ai(app_client) -> None:  # noqa: F811
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    svc_id, a_id = _approved_assessment(c, TestSession, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    provider.register_static("mitre_map", LLMResponse('{"techniques": []}'))

    blocked = c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert blocked.status_code == 409, blocked.text

    assert c.post(f"/attack/assessments/{a_id}/reopen", headers=h).status_code == 200
    assert c.post(f"/attack/services/{svc_id}/run-ai", headers=h).status_code == 200


@pytest.mark.unit
def test_reopen_is_refused_once_a_deliverable_has_been_released(app_client) -> None:  # noqa: F811
    """The line that must not move.

    A released document is a point-in-time claim made to a client. Reopening the
    assessment behind it would let the underlying scores change while the
    delivered PDF says otherwise — the report would describe a state that no
    longer exists anywhere.

    Keyed on `released_at`, NOT on assessment status: nothing in these routes
    ever assigns AttackAssessmentStatus.RELEASED, so a status-based guard would
    silently never fire.
    """
    c, TestSession, _provider = app_client
    bearer, cid = _admin(c)
    svc_id, a_id = _approved_assessment(c, TestSession, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}

    with TestSession() as db:
        db.add(
            Deliverable(
                service_id=_uuid.UUID(svc_id),
                client_id=_uuid.UUID(cid),
                version=1,
                title="ATT&CK Coverage",
                finalized_at=utcnow(),
                released_at=utcnow(),
            )
        )
        db.commit()

    r = c.post(f"/attack/assessments/{a_id}/reopen", headers=h)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "already_released"

    # And it really is still frozen.
    with TestSession() as db:
        a = db.get(AttackAssessment, _uuid.UUID(a_id))
        assert a.status == AttackAssessmentStatus.APPROVED


@pytest.mark.unit
def test_an_unreleased_deliverable_does_not_block_reopen(app_client) -> None:  # noqa: F811
    """A generated-but-unreleased document is exactly the case reopen exists for."""
    c, TestSession, _provider = app_client
    bearer, cid = _admin(c)
    svc_id, a_id = _approved_assessment(c, TestSession, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}

    with TestSession() as db:
        db.add(
            Deliverable(
                service_id=_uuid.UUID(svc_id),
                client_id=_uuid.UUID(cid),
                version=1,
                title="ATT&CK Coverage",
                finalized_at=utcnow(),
                released_at=None,
            )
        )
        db.commit()

    assert c.post(f"/attack/assessments/{a_id}/reopen", headers=h).status_code == 200


@pytest.mark.unit
def test_reopening_a_draft_is_idempotent(app_client) -> None:  # noqa: F811
    """Mirrors discard, which is idempotent on an already-discarded assessment."""
    c, TestSession, _provider = app_client
    bearer, cid = _admin(c)
    svc_id, a_id = _approved_assessment(c, TestSession, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}

    assert c.post(f"/attack/assessments/{a_id}/reopen", headers=h).status_code == 200
    again = c.post(f"/attack/assessments/{a_id}/reopen", headers=h)
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "draft"


@pytest.mark.unit
def test_reopen_is_admin_only(app_client) -> None:  # noqa: F811
    c, TestSession, _provider = app_client
    bearer, cid = _admin(c)
    _svc_id, a_id = _approved_assessment(c, TestSession, bearer, cid)

    other = c.post(
        "/auth/register",
        json={
            "email": "client@acme.example",
            "password": "correct horse battery staple!",
            "display_name": "C",
        },
    )
    r = c.post(
        f"/attack/assessments/{a_id}/reopen",
        headers={
            "Authorization": f"Bearer {other.json()['tokens']['access_token']}",
            "X-Client-Id": cid,
        },
    )
    assert r.status_code == 403, r.text
