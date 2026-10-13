"""#1120: Start a revision refuses while a locking run is RUNNING on the
service: `start_revision` calls `refuse_while_running` before any revision rule
(advisor ruling 6137840346; the route is in each `test_ai_runs_*` LOCK_DRIVERS).

Through the routes, for ZT: a run is RUNNING on draft v2 (its job held, as the
run lock's own tests hold one), and v2 is discarded. A revision of the approved
v1 is refused with the typed lock (`ai_run_in_progress`), because the run is
still RUNNING though its draft is discarded, and no version is opened. The held
run then completes and ends FAILED (`assessment_not_editable`, D-031). Only
then does the revision open v3, whose answer values equal v1's and hold none of
the run's suggestions.

Measured by red-on-revert: removing the `refuse_while_running` call turns this
test red; removing either of the job's discarded-subject checks alone leaves it
green, since each covers the other, and removing both turns it red.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from tests._ai_runs import defer_runs, get_run, start_run
from tests._csf_world import make_world

pytestmark = pytest.mark.unit


@pytest.fixture()
def world(tmp_path):
    yield from make_world(tmp_path)


def _answers(sessions, assessment_id: str) -> dict[str, tuple]:
    from app.models.zt_assessment import ZtAnswer

    with sessions() as s:
        rows = s.execute(
            select(ZtAnswer).where(ZtAnswer.assessment_id == uuid.UUID(assessment_id))
        ).scalars()
        return {
            r.capability_code: (
                r.maturity_stage,
                r.target_stage,
                r.notes,
                r.answer_source,
                r.answered_by,
                r.answered_at,
                r.updated_at,
            )
            for r in rows
        }


def _versions(sessions, svc_id: str) -> list[int]:
    from app.models.zt_assessment import ZtAssessment

    with sessions() as s:
        return sorted(
            s.execute(
                select(ZtAssessment.version).where(ZtAssessment.service_id == uuid.UUID(svc_id))
            ).scalars()
        )


def test_a_revision_waits_for_a_run_on_a_discarded_draft(world) -> None:
    from app.routes.zt import _llm_dep

    c, sessions = world
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    svc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "ZT"})
    svc_id = svc.json()["id"]
    v1 = c.post(f"/zt/services/{svc_id}/assessments", headers=h).json()
    assert c.post(f"/zt/assessments/{v1['id']}/approve", headers=h).status_code == 200
    v2 = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    assert v2.status_code in (200, 201), v2.text
    v2 = v2.json()
    assert (v2["version"], v2["status"]) == (2, "draft")

    caps = [{"code": a["capability_code"], "current": 2} for a in v2["answers"]]
    provider = FixtureProvider()
    provider.register_static("zt_score", LLMResponse(json.dumps({"capabilities": caps})))
    c.app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
    runner = defer_runs(c.app)

    # The run is in progress on v2 (RUNNING, its job held), as the run lock's
    # own tests hold one.
    started = start_run(c, f"/zt/services/{svc_id}/run-ai", h)
    assert get_run(c, started["run_id"], h)["status"] == "running"
    d = c.post(f"/zt/assessments/{v2['id']}/discard", headers=h)
    assert d.status_code == 200, d.text

    def revise():
        return c.post(
            f"/zt/services/{svc_id}/assessments/{v1['id']}/revisions",
            headers=h,
            json={"reason": "a correction"},
        )

    mid = revise()
    assert mid.status_code == 409, mid.text
    assert mid.json()["error"]["reason"] == "ai_run_in_progress", mid.text
    assert _versions(sessions, svc_id) == [1, 2]  # nothing was opened

    # The held run now completes, on a discarded draft.
    assert runner.run_all() == 1
    run = get_run(c, started["run_id"], h)
    assert (run["status"], run["error_reason"]) == ("failed", "assessment_not_editable"), run

    rev = revise()
    assert rev.status_code == 201, rev.text
    v3 = rev.json()
    assert (v3["version"], v3["status"]) == (3, "draft")
    copied = _answers(sessions, v3["id"])
    assert copied, "the revision copied no rows: the comparison below would be empty"
    source = _answers(sessions, v1["id"])
    assert {k: v[:6] for k, v in copied.items()} == {k: v[:6] for k, v in source.items()}
    # The run's suggestion would have changed every row, so v1's values in v3
    # are the run's values absent, not the run writing the same values.
    assert all(stage != 2 for stage, *_ in copied.values())
