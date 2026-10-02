"""A capability list counts its edits, so an approval can go stale (#640).

The owner's rule (2026-09-25): classifications stay editable until release,
every edit is audited, and step 3 must run again after any edit. Every test
drives the routes; the set of edit routes is DERIVED from the router, so a new
edit route fails `test_every_mutating_list_route_...` until a driver here proves
it moves the revision.
"""

from __future__ import annotations

import io
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
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.capability import CapabilityItem, CapabilityList
from app.storage.local import LocalFilesystemStorage
from tests._ai_runs import tech_debt_extract


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker, FixtureProvider]]:
    db_path = tmp_path / "shield-rev.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    storage = LocalFilesystemStorage(tmp_path / "storage")
    provider = FixtureProvider()
    llm = LLMClient(provider)

    from app.db.session import get_db
    from app.main import create_app
    from app.routes.artifacts import _storage_dep
    from app.routes.tech_debt import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_storage_dep] = lambda: storage
    app.dependency_overrides[_llm_dep] = lambda: llm

    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain

    _seed = TestSession()
    _tenant = _Client(legal_name="Northwind Logistics")
    _seed.add(_tenant)
    _seed.flush()
    _seed.add(_ClientDomain(client_id=_tenant.id, domain="example.com"))
    _seed.commit()
    _cid = str(_tenant.id)
    _seed.close()

    with TestClient(app, headers={"X-Client-Id": _cid}) as c:
        yield c, TestSession, provider


def _register(c: TestClient, email: str) -> str:
    r = c.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple!",
            "display_name": email.split("@")[0],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["tokens"]["access_token"]


# ---------------------------------------------------------------------------
# The world: two capabilities from four uploaded rows, so every edit route has
# something to act on. Rows 1 and 3 were excluded; "Workday HCM" was classified
# not security-related, which is what the classification queue acts on.
# ---------------------------------------------------------------------------

_ITEMS = [
    {
        "name": "CrowdStrike Falcon",
        "vendor": "CrowdStrike",
        "category": "EDR",
        "annual_cost_usd": 120000,
        "confidence_pct": 95,
        "source_row_index": 0,
        "security_related": True,
        "security_functions": ["prevent", "detect", "respond"],
    },
    {
        "name": "Workday HCM",
        "vendor": "Workday",
        "category": "HCM",
        "annual_cost_usd": 81700,
        "confidence_pct": 90,
        "source_row_index": 2,
        "security_related": False,
        "security_functions": [],
    },
]
_CSV = (
    b"Tool,Vendor,Annual Cost\n"
    b"CrowdStrike Falcon,CrowdStrike,120000\n"
    b"Claroty xDome,Claroty,133000\n"
    b"Workday HCM,Workday,81700\n"
    b"Team offsite,-,4000\n"
)


@dataclass
class World:
    c: TestClient
    h: dict
    sessions: sessionmaker
    svc_id: str
    list_id: str
    security_id: str
    other_id: str


def _world(app_client) -> World:
    c, sessions, provider = app_client
    bearer = _register(c, "admin@example.com")
    h = {"Authorization": f"Bearer {bearer}"}
    provider.register("extract.capabilities", lambda _p: LLMResponse(json.dumps({"items": _ITEMS})))
    svc_id = c.post("/tech-debt/services", headers=h, json={"title": "Portfolio"}).json()["id"]
    art = c.post("/artifacts", headers=h, files={"file": ("inv.csv", io.BytesIO(_CSV), "text/csv")})
    assert art.status_code == 201, art.text
    body = tech_debt_extract(c, svc_id, h, art.json()["id"])
    assert [e["index"] for e in body["excluded_rows"]] == [1, 3], body["excluded_rows"]
    by_name = {i["name"]: i["id"] for i in body["items"]}
    return World(
        c=c,
        h=h,
        sessions=sessions,
        svc_id=svc_id,
        list_id=body["id"],
        security_id=by_name["CrowdStrike Falcon"],
        other_id=by_name["Workday HCM"],
    )


def _latest(w: World) -> dict:
    r = w.c.get(f"/tech-debt/services/{w.svc_id}/capability-lists/latest", headers=w.h)
    assert r.status_code == 200, r.text
    return r.json()


def _revision(w: World) -> int:
    with w.sessions() as s:
        return s.get(CapabilityList, uuid.UUID(w.list_id)).revision


def _decide_all(w: World) -> None:
    for item in _latest(w)["items"]:
        r = w.c.patch(
            f"/tech-debt/capability-items/{item['id']}", headers=w.h, json={"disposition": "keep"}
        )
        assert r.status_code == 200, r.text


def _approve(w: World):
    return w.c.post(f"/tech-debt/capability-lists/{w.list_id}/approve", headers=w.h)


def _finalize(w: World):
    return w.c.post(f"/tech-debt/services/{w.svc_id}/deliverables/finalize", headers=w.h)


# ---------------------------------------------------------------------------
# Every edit route, derived from the router
# ---------------------------------------------------------------------------

# One driver per edit route: path template -> (method, how to call it).
EDIT_DRIVERS: dict[tuple[str, str], Callable[[World], Any]] = {
    ("POST", "/tech-debt/capability-lists/{list_id}/excluded-rows/{row_index}/include"): (
        lambda w: w.c.post(
            f"/tech-debt/capability-lists/{w.list_id}/excluded-rows/1/include",
            headers=w.h,
            json={"name": "Claroty xDome"},
        )
    ),
    ("POST", "/tech-debt/capability-lists/{list_id}/excluded-rows/{row_index}/confirm"): (
        lambda w: w.c.post(
            f"/tech-debt/capability-lists/{w.list_id}/excluded-rows/3/confirm", headers=w.h
        )
    ),
    ("POST", "/tech-debt/capability-items/{item_id}/security-classification/confirm"): (
        lambda w: w.c.post(
            f"/tech-debt/capability-items/{w.other_id}/security-classification/confirm",
            headers=w.h,
        )
    ),
    ("POST", "/tech-debt/capability-items/{item_id}/security-classification/override"): (
        lambda w: w.c.post(
            f"/tech-debt/capability-items/{w.other_id}/security-classification/override",
            headers=w.h,
            json={"security_functions": ["detect"]},
        )
    ),
    ("POST", "/tech-debt/capability-items/{item_id}/components"): (
        lambda w: w.c.post(
            f"/tech-debt/capability-items/{w.security_id}/components",
            headers=w.h,
            json={"components": [{"name": "Falcon Insight"}]},
        )
    ),
    ("PATCH", "/tech-debt/capability-items/{item_id}"): (
        lambda w: w.c.patch(
            f"/tech-debt/capability-items/{w.security_id}", headers=w.h, json={"notes": "renewal"}
        )
    ),
    # #641's bulk twin of the single-row disposition PATCH.
    ("POST", "/tech-debt/capability-lists/{list_id}/items/disposition"): (
        lambda w: w.c.post(
            f"/tech-debt/capability-lists/{w.list_id}/items/disposition",
            headers=w.h,
            json={"item_ids": [w.security_id, w.other_id], "disposition": "cut"},
        )
    ),
}

# Mutating routes on an existing list that are NOT step-2 edits, each for a
# stated reason. Everything else under these prefixes must have a driver.
NOT_EDITS = {
    # The act being measured: it sets `approved_revision`, it does not edit rows.
    ("POST", "/tech-debt/capability-lists/{list_id}/approve"),
    # Ends the list; a discarded list is not approvable at all (#231).
    ("POST", "/tech-debt/capability-lists/{list_id}/discard"),
}


def _mutating_list_routes() -> set[tuple[str, str]]:
    # The Tech Debt router's own table: `create_app().routes` holds included
    # routers lazily and exposes no paths for them.
    from app.routes.tech_debt import router

    found: set[tuple[str, str]] = set()
    for route in router.routes:
        path = getattr(route, "path", "")
        if not path.startswith(("/tech-debt/capability-lists/", "/tech-debt/capability-items/")):
            continue
        for method in getattr(route, "methods", set()) - {"GET", "HEAD", "OPTIONS"}:
            found.add((method, path))
    return found


@pytest.mark.unit
def test_every_mutating_list_route_is_either_driven_or_named_as_not_an_edit() -> None:
    """A new edit route with no driver here is a route nothing proves bumps the
    revision, so it fails this test until it gets one."""
    found = _mutating_list_routes()
    assert found, "no routes found: the prefix filter is broken, not the routes clean"
    assert found == set(EDIT_DRIVERS) | NOT_EDITS, {
        "undriven": sorted(found - set(EDIT_DRIVERS) - NOT_EDITS),
        "stale": sorted((set(EDIT_DRIVERS) | NOT_EDITS) - found),
    }


@pytest.mark.unit
@pytest.mark.parametrize("route", sorted(EDIT_DRIVERS), ids=lambda r: f"{r[0]} {r[1]}")
def test_each_edit_after_approval_makes_the_approval_stale(app_client, route) -> None:
    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    assert _latest(w)["approval_current"] is True
    before = _revision(w)

    r = EDIT_DRIVERS[route](w)
    assert r.status_code in (200, 201), r.text

    assert _revision(w) == before + 1
    # Including a row or naming components adds UNDECIDED rows, which finalize
    # refuses first (#639). Deciding them is itself an edit; the approval stays
    # stale, which is what the refusal below must say.
    _decide_all(w)
    latest = _latest(w)
    assert latest["status"] == "approved"
    assert latest["approval_current"] is False

    fin = _finalize(w)
    assert fin.status_code == 409, fin.text
    error = fin.json()["error"]
    assert error["reason"] == "capability_list_edited_since_approval", error
    assert "step 3, Approve the capability list" in error["message"], error["message"]


@pytest.mark.unit
def test_locking_a_row_is_not_an_edit_of_the_review(app_client) -> None:
    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    r = w.c.patch(
        f"/tech-debt/capability-items/{w.security_id}", headers=w.h, json={"locked": True}
    )
    assert r.status_code == 200, r.text
    assert _latest(w)["approval_current"] is True


@pytest.mark.unit
def test_a_draft_is_never_current_and_approving_makes_it_so(app_client) -> None:
    w = _world(app_client)
    _decide_all(w)
    assert _latest(w)["approval_current"] is False
    body = _approve(w).json()
    assert body["approval_current"] is True
    with w.sessions() as s:
        row = s.get(CapabilityList, uuid.UUID(w.list_id))
        assert row.approved_revision == row.revision


@pytest.mark.unit
def test_approving_again_after_an_edit_lets_the_deliverable_through(app_client) -> None:
    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    EDIT_DRIVERS[("PATCH", "/tech-debt/capability-items/{item_id}")](w)
    assert _finalize(w).status_code == 409

    again = _approve(w)
    assert again.status_code == 200, again.text
    assert again.json()["approval_current"] is True
    assert _finalize(w).status_code == 201


@pytest.mark.unit
def test_release_refuses_a_list_edited_after_its_deliverable_was_built(app_client) -> None:
    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    fin = _finalize(w)
    assert fin.status_code == 201, fin.text
    EDIT_DRIVERS[("PATCH", "/tech-debt/capability-items/{item_id}")](w)

    r = w.c.post(f"/tech-debt/deliverables/{fin.json()['id']}/release", headers=w.h)
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["reason"] == "capability_list_edited_since_approval", error
    assert "before releasing" in error["message"], error["message"]
    assert _latest(w)["status"] == "approved"


_PREDATES = "deliverable_predates_approval"


def _release(w: World, deliverable_id: str):
    return w.c.post(f"/tech-debt/deliverables/{deliverable_id}/release", headers=w.h)


def _deliverable_released(w: World, deliverable_id: str) -> bool:
    from app.models.deliverable import Deliverable

    with w.sessions() as s:
        return s.get(Deliverable, uuid.UUID(deliverable_id)).released_at is not None


@pytest.mark.unit
def test_release_refuses_a_deliverable_built_before_the_list_was_approved_again(
    app_client,
) -> None:
    """Edit, approve again, then release the deliverable generated BEFORE the
    edit. The approval is current, so the list-level guard passes, but the
    document was rendered from rows that are no longer the approved ones."""
    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    old = _finalize(w)
    assert old.status_code == 201, old.text
    EDIT_DRIVERS[("PATCH", "/tech-debt/capability-items/{item_id}")](w)
    assert _approve(w).status_code == 200
    assert _latest(w)["approval_current"] is True, "setup: the list must be re-approved"

    r = _release(w, old.json()["id"])

    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["reason"] == _PREDATES, error
    assert "generate the deliverable again" in error["message"].lower(), error["message"]
    assert _latest(w)["status"] == "approved"
    assert not _deliverable_released(w, old.json()["id"])


@pytest.mark.unit
def test_a_deliverable_generated_after_the_new_approval_releases(app_client) -> None:
    """The remedy the refusal names works: generate again, release that one."""
    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    old = _finalize(w)
    assert old.status_code == 201, old.text
    EDIT_DRIVERS[("PATCH", "/tech-debt/capability-items/{item_id}")](w)
    assert _approve(w).status_code == 200
    assert _release(w, old.json()["id"]).status_code == 409, "setup: the old one is refused"

    new = _finalize(w)
    assert new.status_code == 201, new.text
    r = _release(w, new.json()["id"])

    assert r.status_code == 200, r.text
    assert _latest(w)["status"] == "released"
    assert _deliverable_released(w, new.json()["id"])


@pytest.mark.unit
def test_an_older_deliverable_is_refused_after_the_list_is_released(app_client) -> None:
    """Advisor review of #730 at 1d012e4, F1. Once a newer deliverable is
    released the list is RELEASED, and `_release_parent` returns before it
    applies the caller's guard. The deliverable built BEFORE the edit must
    still be refused, through the endpoint an admin can call directly."""
    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    old = _finalize(w)
    assert old.status_code == 201, old.text
    EDIT_DRIVERS[("PATCH", "/tech-debt/capability-items/{item_id}")](w)
    assert _approve(w).status_code == 200
    new = _finalize(w)
    assert new.status_code == 201, new.text
    assert _release(w, new.json()["id"]).status_code == 200, "setup: the new one releases"
    assert _latest(w)["status"] == "released", "setup: the list must be RELEASED"

    r = _release(w, old.json()["id"])

    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["reason"] == _PREDATES, error
    assert "generated before the capability list was last approved" in error["message"], error
    assert not _deliverable_released(w, old.json()["id"])


@pytest.mark.unit
def test_a_deliverable_with_no_parent_version_is_refused(app_client) -> None:
    """Advisor review of #730 at 1d012e4, F1. A deliverable finalized before
    migration 0041 recorded no `parent_version` (and, being older than 0056, no
    list revision). `_release_parent` returns before any guard for it, so the
    refusal has to come from the route. The legacy row is written by SQL
    because no current writer produces one; the setup builds that world, and
    the release endpoint is what is under test."""
    from sqlalchemy import update as sa_update

    from app.models.deliverable import Deliverable

    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    fin = _finalize(w)
    assert fin.status_code == 201, fin.text
    with w.sessions() as s:
        s.execute(
            sa_update(Deliverable)
            .where(Deliverable.id == uuid.UUID(fin.json()["id"]))
            .values(parent_version=None, capability_list_revision=None)
        )
        s.commit()

    r = _release(w, fin.json()["id"])

    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["reason"] == _PREDATES, error
    assert "nothing confirms it shows the approved rows" in error["message"], error
    assert not _deliverable_released(w, fin.json()["id"])


@pytest.mark.unit
def test_an_unedited_approval_releases_its_deliverable(app_client) -> None:
    """The control: approve, generate, release, with no edit anywhere."""
    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    fin = _finalize(w)
    assert fin.status_code == 201, fin.text

    r = _release(w, fin.json()["id"])

    assert r.status_code == 200, r.text
    assert _latest(w)["status"] == "released"


@pytest.mark.unit
def test_an_edit_landing_during_approval_refuses_it(app_client, monkeypatch) -> None:
    """The approve UPDATE matches only at the revision it read. An edit that
    commits between that read and the write -- here, while the membership is
    being built -- refuses the approval instead of stamping the edited rows."""
    import app.routes.tech_debt as td

    w = _world(app_client)
    _decide_all(w)
    real_build = td.build_approved_membership
    fired: list[str] = []

    def edit_while_building(db, capability_list_id):
        # What an edit route commits: a row change and the revision bump, in
        # one transaction on its own connection.
        if not fired:
            fired.append("edit")
            with w.sessions() as other:
                other.get(CapabilityItem, uuid.UUID(w.security_id)).notes = "edited"
                other.execute(
                    update(CapabilityList)
                    .where(CapabilityList.id == uuid.UUID(w.list_id))
                    .values(revision=CapabilityList.revision + 1)
                )
                other.commit()
        return real_build(db, capability_list_id)

    monkeypatch.setattr(td, "build_approved_membership", edit_while_building)
    r = _approve(w)

    assert fired == ["edit"], "the race was not exercised"
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "capability_list_changed_during_approval"
    latest = _latest(w)
    assert (latest["status"], latest["approval_current"]) == ("draft", False)


# ---------------------------------------------------------------------------
# Migration 0056's backfill, against lists the product built
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_backfill_reads_an_approved_list_as_current_and_a_draft_as_not(
    app_client,
) -> None:
    """Built through the API, then 0056 is rewound and replayed, so the backfill
    reads rows the approve route wrote, not rows written to suit it."""
    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    draft_svc = w.c.post("/tech-debt/services", headers=w.h, json={"title": "Draft"}).json()["id"]
    art = w.c.post(
        "/artifacts", headers=w.h, files={"file": ("d.csv", io.BytesIO(_CSV), "text/csv")}
    )
    draft = tech_debt_extract(w.c, draft_svc, w.h, art.json()["id"])["id"]

    url = os.environ["DATABASE_URL"]
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.downgrade(cfg, "0055")
    command.upgrade(cfg, "0056")

    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            rows = dict(
                conn.execute(text("SELECT id, approved_revision FROM capability_lists")).all()
            )
            revisions = {r for (r,) in conn.execute(text("SELECT revision FROM capability_lists"))}
    finally:
        engine.dispose()
    by_id = {str(uuid.UUID(str(k))): v for k, v in rows.items()}
    assert revisions == {0}
    assert by_id[w.list_id] == 0
    assert by_id[draft] is None


@pytest.mark.unit
def test_a_deliverable_from_before_0056_is_refused_at_release(app_client) -> None:
    """A deliverable finalized before migration 0056 records no revision, and
    before #640 an approved list could already be edited, so nothing says its
    rows are the approved ones. Missing data defaults to UNCONFIRMED: release
    refuses it and names the remedy. Built through the API, then 0056 is rewound
    and replayed, which is the writer that leaves the column NULL."""
    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    fin = _finalize(w)
    assert fin.status_code == 201, fin.text

    url = os.environ["DATABASE_URL"]
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.downgrade(cfg, "0055")
    command.upgrade(cfg, "0056")
    # Back to head before anything reads through the ORM: the models track
    # head, so a later migration's column would be missing at 0056.
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT id, capability_list_revision FROM deliverables"))
            recorded = {str(uuid.UUID(str(k))): v for k, v in rows.all()}
    finally:
        engine.dispose()
    assert list(recorded) == [fin.json()["id"]], recorded
    recorded = recorded[fin.json()["id"]]
    assert recorded is None, "setup: the replayed migration must leave the column NULL"
    assert _latest(w)["approval_current"] is True, "setup: the backfill reads the list as current"

    r = _release(w, fin.json()["id"])

    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == _PREDATES, r.text
    assert not _deliverable_released(w, fin.json()["id"])


_WHEN_UNKNOWN = "nothing confirms it shows the approved rows"
_WHEN_EDITED = "generated before the capability list was last approved"


def _replay_0056() -> None:
    """Rewind and replay 0056: the writer that leaves every existing
    deliverable's `capability_list_revision` NULL."""
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.downgrade(cfg, "0055")
    command.upgrade(cfg, "0056")
    command.upgrade(cfg, "head")


@pytest.mark.unit
def test_a_deliverable_from_before_0056_is_not_told_it_predates_the_approval(
    app_client,
) -> None:
    """Finalize needed an approved list, so a deliverable that recorded no
    revision was probably generated AFTER the approval. The refusal says only
    what is known: nothing confirms its rows are the approved ones."""
    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    fin = _finalize(w)
    assert fin.status_code == 201, fin.text
    _replay_0056()
    assert _latest(w)["approval_current"] is True, "setup: the backfill reads the list as current"

    r = _release(w, fin.json()["id"])

    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["reason"] == _PREDATES, error
    assert _WHEN_UNKNOWN in error["message"], error["message"]
    assert _WHEN_EDITED not in error["message"], error["message"]
    assert "Re-finalize in step 4" in error["message"], error["message"]


@pytest.mark.unit
def test_a_deliverable_built_before_a_re_approval_is_told_so(app_client) -> None:
    """The other half of the message branch: a deliverable that DID record a
    revision, older than the approval, is told it predates the approval."""
    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    old = _finalize(w)
    assert old.status_code == 201, old.text
    EDIT_DRIVERS[("PATCH", "/tech-debt/capability-items/{item_id}")](w)
    assert _approve(w).status_code == 200

    r = _release(w, old.json()["id"])

    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["reason"] == _PREDATES, error
    assert _WHEN_EDITED in error["message"], error["message"]
    assert _WHEN_UNKNOWN not in error["message"], error["message"]


@pytest.mark.unit
def test_the_seeded_released_list_reads_as_a_current_approval(tmp_path) -> None:
    """Advisor review of #730 at 7ef5585, R2-1. `seed_demo.py` writes a RELEASED
    capability list after every migration has run, so 0056's backfill never
    reaches it. Without an `approved_revision` equal to its `revision`, Re-finalize
    then Release on the seeded demo is refused as "generated before the list was
    last approved", which is false. The seed's own writer is under test here."""
    from scripts.seed_demo import _bootstrap_org, _seed_tech_debt

    url = f"sqlite:///{tmp_path / 'seed.db'}"
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    with sessionmaker(bind=engine, future=True)() as s:
        admin, _client_user, org = _bootstrap_org(s)
        svc = _seed_tech_debt(s, LocalFilesystemStorage(tmp_path / "storage"), admin, org)
        s.commit()
        cap_list = s.execute(
            select(CapabilityList).where(CapabilityList.service_id == svc.id)
        ).scalar_one()

        assert cap_list.status.value == "released"
        assert cap_list.approved_revision is not None, "the seed must record its approval"
        assert cap_list.approval_current is True


# ---------------------------------------------------------------------------
# Round 3 of the independent review of #730 at 2a35fa1b
# ---------------------------------------------------------------------------


def _released_before_w4_and_0056(w: World) -> str:
    """A deliverable the client already has, whose list was left APPROVED and
    which recorded no list revision. Releases before W4 never flipped the
    parent, which is what the idempotent re-release repairs; no current writer
    leaves a released deliverable beside an APPROVED list, so that one column
    is written by SQL. 0056 is then replayed, the writer that leaves the
    deliverable's revision NULL and backfills the list's approval."""
    from app.models.capability import CapabilityListStatus

    _decide_all(w)
    assert _approve(w).status_code == 200
    fin = _finalize(w)
    assert fin.status_code == 201, fin.text
    assert _release(w, fin.json()["id"]).status_code == 200, "setup: the first release"
    with w.sessions() as s:
        s.execute(
            update(CapabilityList)
            .where(CapabilityList.id == uuid.UUID(w.list_id))
            .values(status=CapabilityListStatus.APPROVED)
        )
        s.commit()
    _replay_0056()
    latest = _latest(w)
    assert (latest["status"], latest["approval_current"]) == ("approved", True), latest
    assert _deliverable_released(w, fin.json()["id"]), "setup: the client has the report"
    return fin.json()["id"]


@pytest.mark.unit
def test_re_releasing_a_report_released_before_0056_repairs_its_list(app_client) -> None:
    """Finding 1. The plan: a deliverable finalized but not released before 0056
    is re-finalized once; RELEASED ones are unaffected. The repair re-release of
    one must still flip its list, or the list stays editable and the client
    dashboard keeps reading it live."""
    w = _world(app_client)
    deliverable_id = _released_before_w4_and_0056(w)

    r = _release(w, deliverable_id)

    assert r.status_code == 200, r.text
    assert _latest(w)["status"] == "released"


@pytest.mark.unit
def test_the_repair_re_release_still_refuses_a_list_edited_since_approval(app_client) -> None:
    """Finding 1's other half: the repair is not unguarded. Release freezes the
    list, so it must not freeze rows edited after the approval, whichever
    deliverable is being released."""
    w = _world(app_client)
    deliverable_id = _released_before_w4_and_0056(w)
    EDIT_DRIVERS[("PATCH", "/tech-debt/capability-items/{item_id}")](w)

    r = _release(w, deliverable_id)

    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "capability_list_edited_since_approval", r.text
    assert _latest(w)["status"] == "approved"


@pytest.mark.unit
def test_a_release_after_edit_approve_edit_names_approving_again(app_client) -> None:
    """Finding 2(a). Finalize, edit, approve, edit, release. The deliverable also
    predates the approval, but Re-finalize would be refused while the approval
    is stale, so the refusal must name step 3, the remedy that works now."""
    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    old = _finalize(w)
    assert old.status_code == 201, old.text
    EDIT_DRIVERS[("PATCH", "/tech-debt/capability-items/{item_id}")](w)
    assert _approve(w).status_code == 200
    EDIT_DRIVERS[("PATCH", "/tech-debt/capability-items/{item_id}")](w)
    assert _latest(w)["approval_current"] is False, "setup: the approval must be stale"

    r = _release(w, old.json()["id"])

    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["reason"] == "capability_list_edited_since_approval", error
    assert "Approve it again in step 3" in error["message"], error["message"]
    assert _finalize(w).status_code == 409, "the remedy Re-finalize would not work here"


@pytest.mark.unit
def test_a_legacy_list_with_an_undecided_row_names_the_row_not_re_finalize(app_client) -> None:
    """Finding 2(b). Before 0056 a row of an APPROVED list could be sent back to
    undecided without moving any revision, and the backfill then reads that
    approval as current. Built through the API (the bulk route) and then 0056 is
    replayed, which is the writer that produces it. Re-finalize would be refused
    over the undecided row, so the refusal must name the row."""
    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    fin = _finalize(w)
    assert fin.status_code == 201, fin.text
    r = w.c.post(
        f"/tech-debt/capability-lists/{w.list_id}/items/disposition",
        headers=w.h,
        json={"item_ids": [w.security_id], "disposition": None},
    )
    assert r.status_code == 200, r.text
    _replay_0056()
    assert _latest(w)["approval_current"] is True, "setup: the backfill reads it as current"

    r = _release(w, fin.json()["id"])

    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["reason"] == "capability_list_undecided_rows", error
    assert "1 row is still undecided" in error["message"], error["message"]


@pytest.mark.unit
@pytest.mark.parametrize("route", sorted(EDIT_DRIVERS), ids=lambda r: f"{r[0]} {r[1]}")
def test_an_edit_landing_after_the_release_flip_is_refused(app_client, monkeypatch, route) -> None:
    """Finding 3. Every edit route reads the list as open, then writes. A release
    flip that commits between the two must refuse the edit; otherwise a RELEASED
    list carries `revision > approved_revision` and every later release of it is
    refused with a remedy that loops. The competing flip is written on its own
    connection, as `_release_parent` writes it, just before the edit's write."""
    import app.routes.tech_debt as td
    from app.models.capability import CapabilityListStatus

    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    approved_at = _revision(w)
    real_record_edit = td._record_edit
    fired: list[str] = []

    def release_first(db, list_id):
        if not fired:
            fired.append("release")
            with w.sessions() as other:
                other.execute(
                    update(CapabilityList)
                    .where(CapabilityList.id == uuid.UUID(w.list_id))
                    .values(status=CapabilityListStatus.RELEASED)
                )
                other.commit()
        return real_record_edit(db, list_id)

    monkeypatch.setattr(td, "_record_edit", release_first)
    r = EDIT_DRIVERS[route](w)

    assert fired == ["release"], "the race was not exercised"
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "capability_list_released", r.text
    latest = _latest(w)
    assert (latest["status"], latest["approval_current"]) == ("released", True), latest
    assert _revision(w) == approved_at
