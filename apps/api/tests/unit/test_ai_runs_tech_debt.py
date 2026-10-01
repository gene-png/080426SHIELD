"""Tech Debt extraction runs in the background (#645), through its endpoints.

The run framework's own guards (CAS completion, the reaper, the index, the
savepoint, correlation) are pinned in `test_ai_runs_attack.py`; what is
Tech-Debt-specific is pinned here: which answers stay synchronous, the run
writing a NEW list version, and a second POST naming a different document.
"""

from __future__ import annotations

import io
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.ai_run import AiRun
from app.models.capability import CapabilityList
from app.storage.local import LocalFilesystemStorage
from tests._ai_runs import DeferringRunner, defer_runs, get_run, start_run, tech_debt_extract

_ITEMS = [
    {
        "name": "CrowdStrike Falcon",
        "vendor": "CrowdStrike",
        "category": "EDR",
        "confidence_pct": 95,
        "source_row_index": 0,
        "security_related": True,
        "security_functions": ["detect"],
    }
]
_CSV = b"Tool,Vendor\nCrowdStrike Falcon,CrowdStrike\n"


@dataclass
class World:
    c: TestClient
    app: Any
    sessions: sessionmaker
    provider: FixtureProvider
    h: dict
    svc_id: str

    @property
    def url(self) -> str:
        return f"/tech-debt/services/{self.svc_id}/capability-lists/extract"

    def upload(self, name: str = "inv.csv", data: bytes = _CSV, mime: str = "text/csv") -> str:
        r = self.c.post(
            "/artifacts", headers=self.h, files={"file": (name, io.BytesIO(data), mime)}
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def lists(self) -> list[CapabilityList]:
        with self.sessions() as s:
            return list(s.execute(select(CapabilityList)).scalars())


@pytest.fixture()
def world(tmp_path) -> Iterator[World]:
    url = f"sqlite:///{tmp_path / 'shield-tdruns.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    storage = LocalFilesystemStorage(tmp_path / "storage")
    provider = FixtureProvider()
    provider.register("extract.capabilities", lambda _p: LLMResponse(json.dumps({"items": _ITEMS})))

    from app.db.session import get_db
    from app.main import create_app
    from app.models.client import Client
    from app.models.client_domain import ClientDomain
    from app.routes.artifacts import _storage_dep
    from app.routes.tech_debt import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_storage_dep] = lambda: storage
    app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)

    with sessions() as seed:
        tenant = Client(legal_name="Northwind Logistics")
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
                "display_name": "admin",
            },
        ).json()["tokens"]["access_token"]
        h = {"Authorization": f"Bearer {bearer}"}
        svc = c.post("/tech-debt/services", headers=h, json={"title": "Northwind Tech Debt"})
        assert svc.status_code == 201, svc.text
        yield World(c, app, sessions, provider, h, svc.json()["id"])


def _deferred(world: World) -> DeferringRunner:
    return defer_runs(world.app)


@pytest.mark.unit
def test_an_extraction_without_an_acknowledged_mode_is_a_typed_422(world) -> None:
    runner = _deferred(world)
    r = world.c.post(world.url, headers=world.h, json={"artifact_id": world.upload()})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["reason"] == "serves_required"
    assert runner.pending == [] and world.lists() == []


@pytest.mark.unit
def test_an_extraction_runs_in_the_background_and_writes_a_new_list(world) -> None:
    runner = _deferred(world)
    started = start_run(world.c, world.url, world.h, artifact_id=world.upload())
    assert get_run(world.c, started["run_id"], world.h)["status"] == "running"
    assert world.lists() == [], "nothing is written until the run completes"
    assert runner.run_all() == 1
    run = get_run(world.c, started["run_id"], world.h)
    assert run["status"] == "completed", run
    assert run["applied_count"] == 1
    assert run["result"]["item_count"] == 1
    assert run["result"]["source_rows_total"] == 1
    (cap_list,) = world.lists()
    assert str(cap_list.id) == run["result"]["capability_list_id"]


@pytest.mark.unit
def test_the_production_runner_finishes_an_extraction_end_to_end(world) -> None:
    body = tech_debt_extract(world.c, world.svc_id, world.h, world.upload())
    assert body["version"] == 1 and len(body["items"]) == 1


@pytest.mark.unit
def test_a_second_post_for_the_same_document_joins_and_another_document_is_refused(
    world,
) -> None:
    runner = _deferred(world)
    doc = world.upload("a.csv")
    first = start_run(world.c, world.url, world.h, artifact_id=doc)
    again = start_run(world.c, world.url, world.h, artifact_id=doc)
    assert again["run_id"] == first["run_id"] and again["joined"] is True

    other = world.upload("b.csv")
    r = world.c.post(world.url, headers=world.h, json={"artifact_id": other, "serves": "offline"})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "ai_run_in_progress_other_input"
    with world.sessions() as s:
        assert len(s.execute(select(AiRun)).scalars().all()) == 1
    assert len(runner.pending) == 1


@pytest.mark.unit
def test_a_document_that_is_not_an_inventory_is_refused_before_any_run(world) -> None:
    runner = _deferred(world)
    doc = world.upload("inv.pdf", b"%PDF-1.7 stub", "application/pdf")
    r = world.c.post(world.url, headers=world.h, json={"artifact_id": doc, "serves": "offline"})
    assert r.status_code == 415, r.text
    with world.sessions() as s:
        assert s.execute(select(AiRun)).first() is None
    assert runner.pending == []


@pytest.mark.unit
def test_an_open_draft_is_still_returned_synchronously(world) -> None:
    doc = world.upload()
    first = tech_debt_extract(world.c, world.svc_id, world.h, doc)
    r = world.c.post(world.url, headers=world.h, json={"artifact_id": doc, "serves": "offline"})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == first["id"]
    with world.sessions() as s:
        assert len(s.execute(select(AiRun)).scalars().all()) == 1


@pytest.mark.unit
def test_a_provider_failure_ends_the_extraction_failed_and_writes_no_list(world) -> None:
    runner = _deferred(world)

    def boom(_payload: dict) -> LLMResponse:
        raise RuntimeError("upstream exploded")

    world.provider.register("extract.capabilities", boom)
    started = start_run(world.c, world.url, world.h, artifact_id=world.upload())
    assert runner.run_all() == 1
    run = get_run(world.c, started["run_id"], world.h)
    assert (run["status"], run["error_reason"]) == ("failed", "ai_call_failed"), run
    assert world.lists() == []


# ---------------------------------------------------------------------------
# No edit route is locked by an extraction, and why
# ---------------------------------------------------------------------------

# An extraction writes a NEW list version and never an existing list's rows,
# and none is ever running while a DRAFT is open (the open-draft guard answers
# instead of starting one). So there are no rows for a lock to protect, and the
# approved list's own edits (#640) stay open. Listed so a new route is a
# decision, not a default: the test below fails until it is classified.
NOT_LOCKED_BY_EXTRACTION = {
    ("POST", "/tech-debt/services"),
    ("POST", "/tech-debt/services/{service_id}/capability-lists/extract"),
    ("POST", "/tech-debt/capability-lists/{list_id}/excluded-rows/{row_index}/include"),
    ("POST", "/tech-debt/capability-lists/{list_id}/excluded-rows/{row_index}/confirm"),
    ("POST", "/tech-debt/capability-items/{item_id}/security-classification/confirm"),
    ("POST", "/tech-debt/capability-items/{item_id}/security-classification/override"),
    ("POST", "/tech-debt/capability-items/{item_id}/components"),
    ("PATCH", "/tech-debt/capability-items/{item_id}"),
    ("POST", "/tech-debt/capability-lists/{list_id}/items/disposition"),
    ("POST", "/tech-debt/capability-lists/{list_id}/approve"),
    ("POST", "/tech-debt/capability-lists/{list_id}/discard"),
    ("POST", "/tech-debt/services/{service_id}/deliverables/finalize"),
    ("POST", "/tech-debt/deliverables/{deliverable_id}/release"),
}


@pytest.mark.unit
def test_every_mutating_tech_debt_route_is_classified_against_the_run() -> None:
    from app.routes.tech_debt import router

    found = {
        (method, route.path)
        for route in router.routes
        for method in getattr(route, "methods", set()) - {"GET", "HEAD", "OPTIONS"}
    }
    assert found, "no routes found: the filter is broken, not the routes clean"
    assert found == NOT_LOCKED_BY_EXTRACTION, {
        "unclassified": sorted(found - NOT_LOCKED_BY_EXTRACTION),
        "stale": sorted(NOT_LOCKED_BY_EXTRACTION - found),
    }


@pytest.mark.unit
def test_an_approved_lists_edit_is_not_refused_while_an_extraction_runs(world) -> None:
    first = tech_debt_extract(world.c, world.svc_id, world.h, world.upload("a.csv"))
    item = first["items"][0]["id"]
    r = world.c.patch(
        f"/tech-debt/capability-items/{item}", headers=world.h, json={"disposition": "keep"}
    )
    assert r.status_code == 200, r.text
    assert (
        world.c.post(f"/tech-debt/capability-lists/{first['id']}/approve", headers=world.h)
    ).status_code == 200
    runner = _deferred(world)
    start_run(world.c, world.url, world.h, artifact_id=world.upload("b.csv"))
    r = world.c.patch(
        f"/tech-debt/capability-items/{item}", headers=world.h, json={"notes": "renewal"}
    )
    assert r.status_code == 200, r.text
    assert runner.run_all() == 1
    versions = sorted(cl.version for cl in world.lists())
    assert versions == [1, 2]
