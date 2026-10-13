"""#1120: a revision's AI disclosure counts the runs that drafted what it copied.

Copied values were drafted by AI runs on the SOURCE record, so the stamp of a
revision counts completed runs on the record and on every ancestor through
`revision_of` (Q8: counted, no new wording). A chain deeper than 32 or a cycle
cannot be walked; the stamp then reads not-recorded (`unknown`), failing
closed. Through the real routes for the stamp; the broken chains are built
directly, since no route can produce them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from tests._csf_world import make_world

pytestmark = pytest.mark.unit


@pytest.fixture()
def world(tmp_path):
    yield from make_world(tmp_path)


def _admin(c) -> tuple[dict, str]:
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}, r.json()["user"]["id"]


def _completed_run(sessions, *, service_id: str, subject_id: str, user_id: str) -> None:
    """A completed `csf_score` run on `subject_id`, as the run framework
    records one (a Run AI on that record is the reachable way to get it)."""
    from app.ai.llm import LLMCallMode
    from app.models.ai_run import AiRun, AiRunStatus
    from app.models.service import Service

    now = datetime.now(UTC)
    with sessions() as s:
        svc = s.get(Service, uuid.UUID(service_id))
        s.add(
            AiRun(
                client_id=svc.client_id,
                service_id=svc.id,
                purpose="csf_score",
                subject_id=uuid.UUID(subject_id),
                status=AiRunStatus.COMPLETED,
                mode=LLMCallMode.FIXTURE,
                boot_id="b",
                requested_by=uuid.UUID(user_id),
                started_at=now,
                deadline_at=now + timedelta(minutes=5),
                finished_at=now,
            )
        )
        s.commit()


def _v1_approved(c, h):
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()
    v1 = c.post(f"/csf/services/{svc['id']}/assessments", headers=h).json()
    assert c.post(f"/csf/assessments/{v1['id']}/approve", headers=h).status_code == 200
    return svc["id"], v1["id"]


def _revise(c, h, svc_id: str, aid: str) -> dict:
    r = c.post(
        f"/csf/services/{svc_id}/assessments/{aid}/revisions",
        headers=h,
        json={"reason": "r"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_a_revision_counts_the_runs_on_its_source(world) -> None:
    c, sessions = world
    h, user_id = _admin(c)
    svc_id, v1 = _v1_approved(c, h)
    _completed_run(sessions, service_id=svc_id, subject_id=v1, user_id=user_id)
    v2 = _revise(c, h, svc_id, v1)
    assert v2["ai_source"]["fixture_runs"] == 1, v2["ai_source"]
    assert v2["ai_source"]["state"] != "unknown", v2["ai_source"]


def test_a_second_revision_counts_every_ancestor(world) -> None:
    c, sessions = world
    h, user_id = _admin(c)
    svc_id, v1 = _v1_approved(c, h)
    _completed_run(sessions, service_id=svc_id, subject_id=v1, user_id=user_id)
    v2 = _revise(c, h, svc_id, v1)
    _completed_run(sessions, service_id=svc_id, subject_id=v2["id"], user_id=user_id)
    assert c.post(f"/csf/assessments/{v2['id']}/approve", headers=h).status_code == 200
    v3 = _revise(c, h, svc_id, v2["id"])
    assert v3["ai_source"]["fixture_runs"] == 2, v3["ai_source"]


def test_a_cycle_in_the_chain_reads_unknown(world) -> None:
    c, sessions = world
    h, user_id = _admin(c)
    svc_id, v1 = _v1_approved(c, h)
    v2 = _revise(c, h, svc_id, v1)
    with sessions() as s:  # not reachable through a route: the fail-closed branch
        s.execute(
            text("UPDATE csf_assessments SET revision_of = :v2 WHERE id = :v1"),
            {"v2": uuid.UUID(v2["id"]).hex, "v1": uuid.UUID(v1).hex},
        )
        s.commit()
    latest = c.get(f"/csf/services/{svc_id}/assessments/latest", headers=h).json()
    assert latest["id"] == v2["id"]
    assert latest["ai_source"]["state"] == "unknown", latest["ai_source"]


def test_a_chain_deeper_than_32_reads_unknown(world) -> None:
    from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus

    c, sessions = world
    h, _ = _admin(c)
    svc_id, v1 = _v1_approved(c, h)
    from app.audit.spine import audit

    with sessions() as s:  # 33 released ancestors, built directly
        prev = s.get(CsfAssessment, uuid.UUID(v1))
        prev.status = CsfAssessmentStatus.RELEASED
        for version in range(2, 35):
            row = CsfAssessment(
                service_id=prev.service_id,
                client_id=prev.client_id,
                version=version,
                status=CsfAssessmentStatus.RELEASED,
                revision_of=prev.id,
            )
            s.add(row)
            s.flush()
            # Each with the audit row the revision route writes beside it, so
            # the only unreachable thing built here is the depth.
            audit(
                s,
                action="csf.assessment.revision_started",
                target_type="csf_assessment",
                target_id=row.id,
                details={"from_version": version - 1, "reason": "r", "from_rules": {}},
            )
            prev = row
        s.commit()
        top = s.execute(select(CsfAssessment.id).where(CsfAssessment.version == 34)).scalar_one()
    latest = c.get(f"/csf/services/{svc_id}/assessments/latest", headers=h).json()
    assert latest["id"] == str(top)
    assert latest["ai_source"]["state"] == "unknown", latest["ai_source"]


def test_a_cycle_is_named_as_a_cycle_not_as_depth(world) -> None:
    """The depth bound would also stop a cycle; this pins that a cycle is
    detected as one, at its first repeat."""
    from sqlalchemy.orm import Session

    from app.mode_stamp import RevisionChainError, revision_chain
    from app.models.csf_assessment import CsfAssessment

    c, sessions = world
    h, _ = _admin(c)
    svc_id, v1 = _v1_approved(c, h)
    v2 = _revise(c, h, svc_id, v1)
    with sessions() as s:
        s.execute(
            text("UPDATE csf_assessments SET revision_of = :v2 WHERE id = :v1"),
            {"v2": uuid.UUID(v2["id"]).hex, "v1": uuid.UUID(v1).hex},
        )
        s.commit()
    with sessions() as s:
        assert isinstance(s, Session)
        with pytest.raises(RevisionChainError, match="cyclic"):
            revision_chain(s, s.get(CsfAssessment, uuid.UUID(v2["id"])))
