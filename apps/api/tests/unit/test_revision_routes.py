"""#1120 "Start a revision", through the real routes (ATT&CK, CSF, ZT).

`POST /{kind}/services/{service_id}/assessments/{assessment_id}/revisions`
mints the next version as a DRAFT, copies the prior version forward, and
leaves the prior version untouched. Every refusal is a typed 409 carrying the
copy the advisor approved verbatim (#736 6136101129), written out here, never
imported from the module that renders it.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.csf.catalog import SUBCATEGORIES
from tests._csf_world import make_world

pytestmark = pytest.mark.unit


@pytest.fixture()
def world(tmp_path):
    yield from make_world(tmp_path)


V6 = "Version 2 is open as a draft. Approve it, or discard it, before starting another revision."
V8 = "Version 2 is a draft, so it can be edited directly."
V10 = (
    "Version 1 was submitted by the client and is waiting for your review. "
    "Approve it before starting a revision."
)
V12 = "Version 2 is newer than version 1. Only the newest version can be revised."
X1 = "This version was discarded, so it cannot be revised."
X2 = "This service has been archived, so it cannot be revised."

_SERVICES = {
    "attack": {"title": "ATT&CK"},
    "csf": {"kind": "nist_csf", "title": "CSF"},
    "zt": {"kind": "zero_trust_cisa", "title": "ZT"},
}


def _admin(c) -> dict:
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}


def _service(c, h, kind: str) -> tuple[str, str]:
    svc = c.post(f"/{kind}/services", headers=h, json=_SERVICES[kind])
    assert svc.status_code == 201, svc.text
    a = c.post(f"/{kind}/services/{svc.json()['id']}/assessments", headers=h)
    assert a.status_code == 201, a.text
    return svc.json()["id"], a.json()["id"]


def _approve(c, h, kind: str, aid: str) -> None:
    r = c.post(f"/{kind}/assessments/{aid}/approve", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved", r.text


def _revise(c, h, kind: str, svc_id: str, aid: str, reason: str = "Fix a score"):
    return c.post(
        f"/{kind}/services/{svc_id}/assessments/{aid}/revisions",
        headers=h,
        json={"reason": reason},
    )


def _refused(r, reason: str, message: str) -> None:
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["reason"] == reason, err
    assert err["message"] == message, err


@pytest.mark.parametrize("kind", sorted(_SERVICES))
def test_a_revision_of_an_approved_record_is_the_next_draft(world, kind: str) -> None:
    c, sessions = world
    h = _admin(c)
    svc_id, v1 = _service(c, h, kind)
    _approve(c, h, kind, v1)

    r = _revise(c, h, kind, svc_id, v1)
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["version"] == 2 and v2["status"] == "draft", v2
    assert v2["id"] != v1

    table = {"attack": "attack_assessments", "csf": "csf_assessments", "zt": "zt_assessments"}[kind]
    with sessions() as s:
        rows = dict(
            s.execute(
                text(f"SELECT version, status FROM {table} WHERE service_id = :s"),  # noqa: S608
                {"s": uuid.UUID(svc_id).hex},
            ).all()
        )
        link = s.execute(
            text(f"SELECT revision_of FROM {table} WHERE id = :id"),  # noqa: S608
            {"id": uuid.UUID(v2["id"]).hex},
        ).scalar_one()
    assert rows == {1: "APPROVED", 2: "DRAFT"}, rows  # v1 untouched
    assert uuid.UUID(str(link)) == uuid.UUID(v1)


@pytest.mark.parametrize("kind", sorted(_SERVICES))
def test_a_second_revision_while_a_draft_is_open_is_v6(world, kind: str) -> None:
    c, _ = world
    h = _admin(c)
    svc_id, v1 = _service(c, h, kind)
    _approve(c, h, kind, v1)
    assert _revise(c, h, kind, svc_id, v1).status_code == 201  # positive first
    _refused(_revise(c, h, kind, svc_id, v1), "draft_open", V6)


def test_revising_the_draft_itself_is_v8(world) -> None:
    c, _ = world
    h = _admin(c)
    svc_id, v1 = _service(c, h, "csf")
    _approve(c, h, "csf", v1)
    v2 = _revise(c, h, "csf", svc_id, v1).json()["id"]
    _refused(_revise(c, h, "csf", svc_id, v2), "draft_open", V8)


def test_revising_an_older_version_is_v12(world) -> None:
    c, _ = world
    h = _admin(c)
    svc_id, v1 = _service(c, h, "csf")
    _approve(c, h, "csf", v1)
    v2 = _revise(c, h, "csf", svc_id, v1).json()["id"]
    _approve(c, h, "csf", v2)
    _refused(_revise(c, h, "csf", svc_id, v1), "not_latest", V12)


def test_revising_a_discarded_version_is_x1(world) -> None:
    c, _ = world
    h = _admin(c)
    svc_id, v1 = _service(c, h, "csf")
    _approve(c, h, "csf", v1)
    v2 = _revise(c, h, "csf", svc_id, v1).json()["id"]
    assert c.post(f"/csf/assessments/{v2}/discard", headers=h).status_code == 200
    _refused(_revise(c, h, "csf", svc_id, v2), "assessment_discarded", X1)


def test_a_submitted_self_assessment_is_v10(world) -> None:
    c, _ = world
    h = _admin(c)
    svc_id, v1 = _service(c, h, "csf")
    r = c.post(f"/csf/services/{svc_id}/self-assessment/submit", headers=h, json={})
    assert r.status_code == 200, r.text
    _refused(_revise(c, h, "csf", svc_id, v1), "submitted_awaiting_review", V10)


def test_an_archived_service_is_x2(world) -> None:
    c, _ = world
    h = _admin(c)
    svc_id, v1 = _service(c, h, "csf")
    _approve(c, h, "csf", v1)
    r = c.delete(f"/admin/services/{svc_id}", headers=h)
    assert r.status_code == 204, r.text
    _refused(_revise(c, h, "csf", svc_id, v1), "service_archived", X2)


def test_a_blank_reason_is_refused_and_writes_nothing(world) -> None:
    c, sessions = world
    h = _admin(c)
    svc_id, v1 = _service(c, h, "csf")
    _approve(c, h, "csf", v1)
    r = _revise(c, h, "csf", svc_id, v1, reason="   ")
    assert r.status_code == 422, r.text
    with sessions() as s:
        count = s.execute(text("SELECT COUNT(*) FROM csf_assessments")).scalar_one()
    assert count == 1


def test_an_assessment_of_another_service_is_404(world) -> None:
    c, _ = world
    h = _admin(c)
    svc_a, _v1a = _service(c, h, "csf")
    _svc_b, v1b = _service(c, h, "csf")
    _approve(c, h, "csf", v1b)
    assert _revise(c, h, "csf", svc_a, v1b).status_code == 404


def test_the_answers_are_copied_forward(world) -> None:
    c, sessions = world
    h = _admin(c)
    svc_id, v1 = _service(c, h, "csf")
    code = SUBCATEGORIES[0].code
    answers = c.get(f"/csf/services/{svc_id}/assessments/latest", headers=h).json()["answers"]
    ans = next(a for a in answers if a["subcategory_code"] == code)
    r = c.patch(f"/csf/answers/{ans['id']}", headers=h, json={"maturity_tier": 3})
    assert r.status_code == 200, r.text
    _approve(c, h, "csf", v1)

    v2 = _revise(c, h, "csf", svc_id, v1).json()
    copied = next(a for a in v2["answers"] if a["subcategory_code"] == code)
    assert copied["maturity_tier"] == 3
    assert copied["id"] != ans["id"]
    assert len(v2["answers"]) == len(answers)


def test_the_revision_is_audited_with_its_reason(world) -> None:
    from app.models.audit_entry import AuditEntry

    c, sessions = world
    h = _admin(c)
    svc_id, v1 = _service(c, h, "csf")
    _approve(c, h, "csf", v1)
    v2 = _revise(c, h, "csf", svc_id, v1, reason="Client found a typo").json()
    with sessions() as s:
        entry = s.execute(
            select(AuditEntry).where(AuditEntry.action == "csf.assessment.revision_started")
        ).scalar_one()
    assert entry.details["reason"] == "Client found a typo"
    assert entry.details["from_version"] == 1 and entry.details["to_version"] == 2
    assert str(entry.target_id) == v2["id"]


def test_a_revision_that_loses_the_race_is_v6_naming_the_winner(world, monkeypatch) -> None:
    """A draft opened after the pre-check: the one-draft index refuses the
    revision's insert, and the answer is V6 naming the draft that won."""
    import app.services.revisions as revisions
    from app.models.csf_assessment import CsfAssessment

    c, sessions = world
    h = _admin(c)
    svc_id, v1 = _service(c, h, "csf")
    _approve(c, h, "csf", v1)
    original = revisions._newest_newer
    won: list[int] = []

    def racing(db, model, target):
        found = original(db, model, target)
        if not won:
            with sessions() as s:
                s.add(
                    CsfAssessment(
                        service_id=target.service_id, client_id=target.client_id, version=2
                    )
                )
                s.commit()
            won.append(2)
        return found

    monkeypatch.setattr(revisions, "_newest_newer", racing)
    r = _revise(c, h, "csf", svc_id, v1)
    assert won, "the hook never ran"
    _refused(r, "draft_open", V6)
    with sessions() as s:
        count = s.execute(text("SELECT COUNT(*) FROM csf_assessments")).scalar_one()
    assert count == 2  # v1 and the winner; the revision wrote nothing
