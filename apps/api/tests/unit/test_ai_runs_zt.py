"""Zero Trust Run-AI in the background (#645), through ZT's endpoints.

The run framework's own guards are pinned in `test_ai_runs_attack.py`. Pinned
here: ZT's edit lock over a router-derived route set (the run writes the
ANSWERS, so the client's own self-assessment routes are locked too), an
answer edited after the run started kept and itemized, and the run's
disclosures stored on the run.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.zt_assessment import ZtAnswer
from tests._ai_runs import DeferringRunner, defer_runs, get_run, start_run


@dataclass
class World:
    c: TestClient
    app: Any
    sessions: sessionmaker
    provider: FixtureProvider
    h: dict
    svc_id: str
    assessment_id: str
    answers: list[dict]

    @property
    def run_url(self) -> str:
        return f"/zt/services/{self.svc_id}/run-ai"

    def suggest(self, n: int) -> None:
        caps = [{"code": a["capability_code"], "current": 2} for a in self.answers[:n]]
        self.provider.register_static("zt_score", LLMResponse(json.dumps({"capabilities": caps})))

    def answer(self, answer_id: str) -> ZtAnswer:
        with self.sessions() as s:
            return s.get(ZtAnswer, uuid.UUID(answer_id))


@pytest.fixture()
def world(tmp_path) -> Iterator[World]:
    url = f"sqlite:///{tmp_path / 'shield-ztruns.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app
    from app.routes.zt import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    provider = FixtureProvider()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
    with TestClient(app) as c:
        bearer = c.post(
            "/auth/register",
            json={
                "email": "admin@kentro.example",
                "password": "correct horse battery staple!",
                "display_name": "A",
            },
        ).json()["tokens"]["access_token"]
        cid = c.post(
            "/admin/clients",
            headers={"Authorization": f"Bearer {bearer}"},
            json={"legal_name": "Acme"},
        ).json()["id"]
        h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
        svc_id = c.post(
            "/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "Acme ZT"}
        ).json()["id"]
        a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
        assert a.status_code in (200, 201), a.text
        answers = a.json()["answers"]
        assert len(answers) >= 3
        yield World(c, app, sessions, provider, h, svc_id, a.json()["id"], answers)


def _deferred(world: World) -> DeferringRunner:
    return defer_runs(world.app)


@pytest.mark.unit
def test_a_zt_run_stores_its_accounting_on_the_run(world) -> None:
    runner = _deferred(world)
    world.suggest(2)
    started = start_run(world.c, world.run_url, world.h)
    assert runner.run_all() == 1
    run = get_run(world.c, started["run_id"], world.h)
    assert run["status"] == "completed", run
    result = run["result"]
    assert (result["suggestions_received"], result["suggestions_applied"]) == (2, 2)
    assert run["applied_count"] == 2
    from app.schemas.zt import ZtRunAiResponse

    # Derived from the schema, never hand-listed: `ZtRunAiResponse` was the
    # synchronous route's `response_model` and is now the run result's model,
    # so every key it declares must be on the stored result. A field dropped
    # from the result fails here instead of silently shrinking what the
    # migrated assertions can see.
    assert set(result) == set(ZtRunAiResponse.model_fields), set(result) ^ set(
        ZtRunAiResponse.model_fields
    )
    assert len(result["answers"]) == len(world.answers)
    assert world.answer(world.answers[0]["id"]).maturity_stage == 2


@pytest.mark.unit
def test_an_answer_edited_after_the_run_started_is_kept_and_itemized(world) -> None:
    from app.models._common import utcnow

    runner = _deferred(world)
    world.suggest(2)
    started = start_run(world.c, world.run_url, world.h)
    edited = world.answers[0]
    with world.sessions() as s:
        s.execute(
            update(ZtAnswer).where(ZtAnswer.id == uuid.UUID(edited["id"]))
            # A NOTE, not a stage: an answered row is `protected` from an
            # offline run before the edit check is reached, which would pin the
            # wrong guard.
            .values(notes="edited mid-run", updated_at=utcnow())
        )
        s.commit()
    assert runner.run_all() == 1
    run = get_run(world.c, started["run_id"], world.h)
    assert run["status"] == "completed", run
    result = run["result"]
    skipped = [d for d in result["dropped"] if d["reason"] == "edited"]
    assert [d["key"] for d in skipped] == [edited["capability_code"]]
    assert result["suggestions_applied"] == 1
    kept = world.answer(edited["id"])
    assert (kept.maturity_stage, kept.notes) == (None, "edited mid-run")
    assert world.answer(world.answers[1]["id"]).maturity_stage == 2


# ---------------------------------------------------------------------------
# The edit lock, over a route set derived from the router
# ---------------------------------------------------------------------------

LOCK_DRIVERS: dict[tuple[str, str], Callable[[World], Any]] = {
    ("POST", "/zt/services/{service_id}/assessments"): (
        lambda w: w.c.post(f"/zt/services/{w.svc_id}/assessments", headers=w.h)
    ),
    ("PATCH", "/zt/answers/{answer_id}"): (
        lambda w: w.c.patch(
            f"/zt/answers/{w.answers[0]['id']}", headers=w.h, json={"maturity_stage": 1}
        )
    ),
    # The client's own routes, driven with the admin's session: the lock is
    # checked before the role-specific refusals, and it is the lock under test.
    ("PATCH", "/zt/self-assessment/answers/{answer_id}"): (
        lambda w: w.c.patch(
            f"/zt/self-assessment/answers/{w.answers[0]['id']}",
            headers=w.h,
            json={"maturity_stage": 1},
        )
    ),
    ("POST", "/zt/services/{service_id}/self-assessment/submit"): (
        lambda w: w.c.post(f"/zt/services/{w.svc_id}/self-assessment/submit", headers=w.h, json={})
    ),
    ("POST", "/zt/assessments/{assessment_id}/approve"): (
        lambda w: w.c.post(f"/zt/assessments/{w.assessment_id}/approve", headers=w.h)
    ),
    ("POST", "/zt/services/{service_id}/deliverables/finalize"): (
        lambda w: w.c.post(f"/zt/services/{w.svc_id}/deliverables/finalize", headers=w.h)
    ),
}

# Mutating ZT routes a run deliberately leaves open, each for a reason.
NOT_LOCKED = {
    # Creates a new service; no run can be in progress on it.
    ("POST", "/zt/services"),
    # Joins or refuses the run in progress itself.
    ("POST", "/zt/services/{service_id}/run-ai"),
    # D-031: a discard racing a run wins; the job then ends FAILED.
    ("POST", "/zt/assessments/{assessment_id}/discard"),
    # Ships a deliverable already rendered from an APPROVED assessment; a run
    # is refused on an approved or released one.
    ("POST", "/zt/deliverables/{deliverable_id}/release"),
}


@pytest.mark.unit
def test_every_mutating_zt_route_is_either_locked_or_named_as_open() -> None:
    from app.routes.zt import router

    found = {
        (method, route.path)
        for route in router.routes
        for method in getattr(route, "methods", set()) - {"GET", "HEAD", "OPTIONS"}
    }
    assert found, "no routes found: the filter is broken, not the routes clean"
    assert found == set(LOCK_DRIVERS) | NOT_LOCKED, {
        "undriven": sorted(found - set(LOCK_DRIVERS) - NOT_LOCKED),
        "stale": sorted((set(LOCK_DRIVERS) | NOT_LOCKED) - found),
    }


@pytest.mark.unit
@pytest.mark.parametrize("route", sorted(LOCK_DRIVERS), ids=lambda r: f"{r[0]} {r[1]}")
def test_each_locked_zt_route_is_refused_while_a_run_is_in_progress(world, route) -> None:
    runner = _deferred(world)
    world.suggest(1)
    start_run(world.c, world.run_url, world.h)
    r = LOCK_DRIVERS[route](world)
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["reason"] == "ai_run_in_progress"
    assert "UTC" in err["message"]
    assert runner.run_all() == 1
    after = LOCK_DRIVERS[route](world)
    assert after.status_code != 409 or after.json()["error"].get("reason") != "ai_run_in_progress"


@pytest.mark.unit
def test_a_reaped_runs_accounting_is_logged_voided_not_applied(world, capsys) -> None:
    """Review A2: the accounting line is emitted only after the completion
    commit; a run whose compare-and-swap misses logs it as `.voided`."""
    from app.models.ai_run import AiRun, AiRunStatus

    runner = _deferred(world)
    world.suggest(2)
    started = start_run(world.c, world.run_url, world.h)
    with world.sessions() as s:
        s.execute(
            update(AiRun)
            .where(AiRun.id == uuid.UUID(started["run_id"]))
            .values(status=AiRunStatus.FAILED, error_reason="run_deadline_exceeded")
        )
        s.commit()
    capsys.readouterr()
    assert runner.run_all() == 1
    out = capsys.readouterr().out
    assert '"zt_run_ai_suggestions_accounted.voided"' in out, out[-2000:]
    assert '"zt_run_ai_suggestions_accounted"' not in out
