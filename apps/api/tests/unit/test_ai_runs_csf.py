"""CSF Run-AI in the background (#645), through CSF's endpoints.

The run framework's own guards are pinned in `test_ai_runs_attack.py`. Pinned
here: CSF's edit lock over a router-derived route set, a row edited after the
run started kept and itemized, the run's disclosures stored on the run, and a
discard racing the run winning.
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
from app.models.csf_profile import CsfDimensionScore
from app.storage.local import LocalFilesystemStorage
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
    rows: list[dict]

    @property
    def run_url(self) -> str:
        return f"/csf/services/{self.svc_id}/run-ai"

    def suggest(self, n: int) -> None:
        scores = [
            {
                "tier": "high",
                "subcategory_code": r["subcategory_code"],
                "governance": 2,
                "what_we_found": "Drafted.",
            }
            for r in self.rows[:n]
        ]
        self.provider.register_static("csf_score", LLMResponse(json.dumps({"scores": scores})))

    def row(self, score_id: str) -> CsfDimensionScore:
        with self.sessions() as s:
            return s.get(CsfDimensionScore, uuid.UUID(score_id))


@pytest.fixture()
def world(tmp_path) -> Iterator[World]:
    url = f"sqlite:///{tmp_path / 'shield-csfruns.db'}"
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
    from app.models.client import Client
    from app.models.client_domain import ClientDomain
    from app.routes.artifacts import _storage_dep
    from app.routes.csf import _llm_dep

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
    # The export driver really exports once the run has ended, so it needs a
    # store CI has: a local directory, not the compose stack's MinIO.
    storage = LocalFilesystemStorage(tmp_path / "storage")
    app.dependency_overrides[_storage_dep] = lambda: storage
    with sessions() as seed:
        tenant = Client(legal_name="Test Tenant")
        seed.add(tenant)
        seed.flush()
        seed.add(ClientDomain(client_id=tenant.id, domain="example.com"))
        seed.commit()
        cid = str(tenant.id)
    with TestClient(app, headers={"X-Client-Id": cid}) as c:
        bearer = c.post(
            "/auth/register",
            json={
                "email": "admin@example.com",
                "password": "correct horse battery staple!",
                "display_name": "A",
            },
        ).json()["tokens"]["access_token"]
        h = {"Authorization": f"Bearer {bearer}"}
        svc_id = c.post(
            "/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}
        ).json()["id"]
        a = c.post(f"/csf/services/{svc_id}/assessments", headers=h)
        assert a.status_code in (200, 201), a.text
        seeded = c.post(
            f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]}
        )
        assert seeded.status_code in (200, 201), seeded.text
        rows = c.get(f"/csf/services/{svc_id}/profile/high", headers=h).json()["rows"]
        assert len(rows) >= 3
        yield World(c, app, sessions, provider, h, svc_id, a.json()["id"], rows)


def _deferred(world: World) -> DeferringRunner:
    return defer_runs(world.app)


@pytest.mark.unit
def test_a_csf_run_stores_its_accounting_on_the_run(world) -> None:
    runner = _deferred(world)
    world.suggest(2)
    started = start_run(world.c, world.run_url, world.h)
    assert runner.run_all() == 1
    run = get_run(world.c, started["run_id"], world.h)
    assert run["status"] == "completed", run
    result = run["result"]
    assert result["suggestions_received"] == 4
    assert result["suggestions_applied"] == 4
    assert result["dropped"] == []
    assert run["applied_count"] == 4
    from app.schemas.csf import CsfRunAiResponse

    # Derived from the schema, never hand-listed: `CsfRunAiResponse` was the
    # synchronous route's `response_model` and is now the run result's model,
    # so every key it declares must be on the stored result. A field dropped
    # from the result fails here instead of silently shrinking what the
    # migrated assertions can see.
    assert set(result) == set(CsfRunAiResponse.model_fields), set(result) ^ set(
        CsfRunAiResponse.model_fields
    )
    assert len(result["rows"]) == len(world.rows)
    assert world.row(world.rows[0]["id"]).governance == 2


@pytest.mark.unit
def test_a_row_edited_after_the_run_started_is_kept_and_itemized(world) -> None:
    from app.models._common import utcnow

    runner = _deferred(world)
    world.suggest(2)
    started = start_run(world.c, world.run_url, world.h)
    edited = world.rows[0]
    with world.sessions() as s:
        s.execute(
            update(CsfDimensionScore)
            .where(CsfDimensionScore.id == uuid.UUID(edited["id"]))
            .values(governance=1, updated_at=utcnow())
        )
        s.commit()
    assert runner.run_all() == 1
    run = get_run(world.c, started["run_id"], world.h)
    assert run["status"] == "completed", run
    result = run["result"]
    skipped = [d for d in result["dropped"] if d["reason"] == "edited"]
    assert [d["key"] for d in skipped] == [f"high|{edited['subcategory_code']}"]
    assert result["suggestions_applied"] == 2 and result["suggestions_applied"] > 0
    assert result["suggestions_received"] == result["suggestions_applied"] + sum(
        d["values"] for d in result["dropped"]
    )
    assert world.row(edited["id"]).governance == 1
    assert world.row(world.rows[1]["id"]).governance == 2


@pytest.mark.unit
def test_a_discard_during_a_csf_run_wins(world) -> None:
    runner = _deferred(world)
    world.suggest(2)
    started = start_run(world.c, world.run_url, world.h)
    r = world.c.post(f"/csf/assessments/{world.assessment_id}/discard", headers=world.h)
    assert r.status_code == 200, r.text
    assert runner.run_all() == 1
    run = get_run(world.c, started["run_id"], world.h)
    assert (run["status"], run["error_reason"]) == ("failed", "assessment_not_editable"), run
    assert world.row(world.rows[0]["id"]).governance == 0


# ---------------------------------------------------------------------------
# The edit lock, over a route set derived from the router
# ---------------------------------------------------------------------------

LOCK_DRIVERS: dict[tuple[str, str], Callable[[World], Any]] = {
    ("POST", "/csf/services/{service_id}/assessments"): (
        lambda w: w.c.post(f"/csf/services/{w.svc_id}/assessments", headers=w.h)
    ),
    ("PATCH", "/csf/dimension-scores/{score_id}"): (
        lambda w: w.c.patch(
            f"/csf/dimension-scores/{w.rows[0]['id']}", headers=w.h, json={"governance": 1}
        )
    ),
    ("POST", "/csf/services/{service_id}/profiles/seed"): (
        lambda w: w.c.post(
            f"/csf/services/{w.svc_id}/profiles/seed", headers=w.h, json={"tiers": ["low"]}
        )
    ),
    ("POST", "/csf/assessments/{assessment_id}/approve"): (
        lambda w: w.c.post(f"/csf/assessments/{w.assessment_id}/approve", headers=w.h)
    ),
    ("POST", "/csf/services/{service_id}/playbook/export"): (
        lambda w: w.c.post(f"/csf/services/{w.svc_id}/playbook/export", headers=w.h)
    ),
    ("POST", "/csf/services/{service_id}/deliverables/finalize"): (
        lambda w: w.c.post(f"/csf/services/{w.svc_id}/deliverables/finalize", headers=w.h)
    ),
}

# Mutating CSF routes a run deliberately leaves open, each for a reason. A run
# writes the dimension-score rows of one assessment; these write none of them.
NOT_LOCKED = {
    # Creates a new service; no run can be in progress on it.
    ("POST", "/csf/services"),
    # Joins or refuses the run in progress itself.
    ("POST", "/csf/services/{service_id}/run-ai"),
    # D-031: a discard racing a run wins; the job then ends FAILED.
    ("POST", "/csf/assessments/{assessment_id}/discard"),
    # Ships a deliverable already rendered from an APPROVED assessment; a run
    # is refused on an approved or released one.
    ("POST", "/csf/deliverables/{deliverable_id}/release"),
    # Interview answers: the run READ them when it started and never writes
    # them. An answer edited mid-run reaches the next run, not this one.
    ("PATCH", "/csf/answers/{answer_id}"),
    # The client's own self-assessment, the same input from the client's side.
    ("PATCH", "/csf/self-assessment/answers/{answer_id}"),
    ("POST", "/csf/services/{service_id}/self-assessment/submit"),
    # Consultant gap actions: their own table, which a run never writes.
    ("PUT", "/csf/services/{service_id}/gap-actions/{subcategory_code}"),
}


@pytest.mark.unit
def test_every_mutating_csf_route_is_either_locked_or_named_as_open() -> None:
    from app.routes.csf import router

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
def test_each_locked_csf_route_is_refused_while_a_run_is_in_progress(world, route) -> None:
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
    assert '"csf_run_ai_suggestions_accounted.voided"' in out, out[-2000:]
    assert '"csf_run_ai_suggestions_accounted"' not in out
