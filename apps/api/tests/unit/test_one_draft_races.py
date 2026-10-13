"""#1120 (migration 0073): the one-draft index is the guard, and each writer that
can lose a race to it answers in its own existing words, never a 500 or a
second draft.

* `create_assessment` (ATT&CK, CSF, ZT): a draft committed between the route's
  read of the latest record and its insert. The insert's flush hits
  `uq_<table>_one_draft`; the route rolls back, re-reads and returns THAT draft
  with 200, which is its existing idempotent contract.
* Tech Debt's extraction job: a draft committed during the LLM call, after the
  job's re-check. The insert's flush hits `uq_capability_lists_one_draft`; the
  run ends FAILED with the job's existing reason
  `capability_list_draft_exists`, and one draft remains.

Each race is made deterministic by a hook that commits the competing draft from
a separate session at the exact point in the gap.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.capability import CapabilityList, CapabilityListStatus
from tests._ai_runs import get_run, start_run
from tests._csf_world import make_world
from tests.unit.test_ai_runs_tech_debt import _deferred, world  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.fixture()
def csf_world(tmp_path):
    yield from make_world(tmp_path)


_KINDS = {
    "attack": ("/attack/services", {"title": "ATT&CK"}, "AttackAssessment"),
    "csf": ("/csf/services", {"kind": "nist_csf", "title": "CSF"}, "CsfAssessment"),
    "zt": ("/zt/services", {"kind": "zero_trust_cisa", "title": "ZT"}, "ZtAssessment"),
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


def _competing_draft(sessions, model_name: str, service_id: str) -> str:
    """A DRAFT for `service_id`, committed from a session of its own."""
    import app.models as models

    model = getattr(models, model_name)
    with sessions() as s:
        from app.models.service import Service

        svc = s.get(Service, uuid.UUID(service_id))
        from app.models.zt_assessment import ZtFramework

        extra = {"framework": ZtFramework.CISA_ZTMM_2_0} if model_name == "ZtAssessment" else {}
        row = model(service_id=svc.id, client_id=svc.client_id, version=99, **extra)
        s.add(row)
        s.commit()
        return str(row.id)


@pytest.mark.parametrize("kind", sorted(_KINDS))
def test_create_returns_the_draft_that_won_the_race(csf_world, monkeypatch, kind: str) -> None:
    c, sessions = csf_world
    h = _admin(c)
    path, body, model_name = _KINDS[kind]
    svc = c.post(path, headers=h, json=body)
    assert svc.status_code == 201, svc.text
    svc_id = svc.json()["id"]

    import importlib

    routes = importlib.import_module(f"app.routes.{kind}")
    original = routes._latest_assessment
    won: list[str] = []

    def racing_latest(db, service_id):
        found = original(db, service_id)
        if not won:
            won.append(_competing_draft(sessions, model_name, str(service_id)))
        return found

    monkeypatch.setattr(routes, "_latest_assessment", racing_latest)
    r = c.post(f"/{kind}/services/{svc_id}/assessments", headers=h)
    assert won, "the hook never ran"
    assert r.status_code == 200, r.text
    assert r.json()["id"] == won[0]
    assert r.json()["status"] == "draft"

    import app.models as models

    model = getattr(models, model_name)
    with sessions() as s:
        drafts = s.execute(
            select(model).where(
                model.service_id == uuid.UUID(svc_id),
                model.status == model.status.type.enum_class.DRAFT,
            )
        ).all()
    assert len(drafts) == 1


def test_an_extraction_that_loses_the_race_fails_with_its_own_reason(
    world, monkeypatch  # noqa: F811
) -> None:
    """The competing draft is committed after the job's re-check and its
    `llm_calls` commit, immediately before it reads the next version: the
    point where the job holds no write lock and nothing else guards."""
    import app.routes.tech_debt as td

    runner = _deferred(world)
    original = td._max_list_version
    won: list[int] = []

    def racing_max(db, service_id):
        if not won:
            with world.sessions() as s:
                s.add(
                    CapabilityList(
                        service_id=uuid.UUID(world.svc_id),
                        version=99,
                        status=CapabilityListStatus.DRAFT,
                    )
                )
                s.commit()
            won.append(99)
        return original(db, service_id)

    monkeypatch.setattr(td, "_max_list_version", racing_max)
    started = start_run(world.c, world.url, world.h, artifact_id=world.upload())
    assert runner.run_all() == 1
    assert won, "the hook never ran"
    run = get_run(world.c, started["run_id"], world.h)
    assert run["status"] == "failed", run
    assert run["error_reason"] == "capability_list_draft_exists", run
    drafts = [cl for cl in world.lists() if cl.status == CapabilityListStatus.DRAFT]
    assert [d.version for d in drafts] == [99], "the run put a second draft beside the winner"
