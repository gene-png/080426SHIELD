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
from sqlalchemy import create_engine, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.capability import CapabilityItem, CapabilityList
from app.storage.local import LocalFilesystemStorage


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
    r = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers=h,
        json={"artifact_id": art.json()["id"]},
    )
    assert r.status_code == 201, r.text
    body = r.json()
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
# Migration 0055's backfill, against lists the product built
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_backfill_reads_an_approved_list_as_current_and_a_draft_as_not(
    app_client,
) -> None:
    """Built through the API, then 0055 is rewound and replayed, so the backfill
    reads rows the approve route wrote, not rows written to suit it."""
    w = _world(app_client)
    _decide_all(w)
    assert _approve(w).status_code == 200
    draft_svc = w.c.post("/tech-debt/services", headers=w.h, json={"title": "Draft"}).json()["id"]
    art = w.c.post(
        "/artifacts", headers=w.h, files={"file": ("d.csv", io.BytesIO(_CSV), "text/csv")}
    )
    draft = w.c.post(
        f"/tech-debt/services/{draft_svc}/capability-lists/extract",
        headers=w.h,
        json={"artifact_id": art.json()["id"]},
    ).json()["id"]

    url = os.environ["DATABASE_URL"]
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.downgrade(cfg, "0054")
    command.upgrade(cfg, "0055")

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
