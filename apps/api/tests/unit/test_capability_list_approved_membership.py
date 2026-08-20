"""W3: approving a Tech Debt capability list must fix what is in it.

`_editable_list_or_404` blocks RELEASED and DISCARDED only, so the whole window
between approval and release is mutable through five doors:

  * `patch_capability_item` — any field, INCLUDING `name`
  * add-components
  * `include_excluded_row`
  * the security-classification confirm queue (a *sanctioned* post-approval
    change of allow-list membership)
  * `_editable_list_or_404` itself, which lets the first three through

`attack.py::_client_tool_names` builds a HARD ALLOW-LIST out of those names. Its
own module docstring states the stakes: "Drop a real security tool from it and
the model cannot name it, so the technique it covers reads as uncovered. That is
a fabricated gap." So "confirmed against the approved list" was checked against
whatever the list had since become — which is the premise W2's narrow-confirmed
would otherwise rest on.

The snapshot is deliberately NOT a lock. Editing an approved list is a real
workflow (the confirm queue exists on purpose); what was missing is that the
edit silently rewrote history. Re-approval refreshes the snapshot, so the escape
hatch is explicit and audited rather than implicit and silent.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.storage.local import LocalFilesystemStorage


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    url = f"sqlite:///{tmp_path / 'shield-w3.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app
    from app.routes.artifacts import _storage_dep

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_storage_dep] = lambda: LocalFilesystemStorage(tmp_path / "storage")

    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain

    seed = TestSession()
    tenant = _Client(legal_name="Test Tenant")
    seed.add(tenant)
    seed.flush()
    seed.add(_ClientDomain(client_id=tenant.id, domain="example.com"))
    seed.commit()
    cid = str(tenant.id)
    seed.close()

    with TestClient(app, headers={"X-Client-Id": cid}) as c:
        c.client_id = cid  # type: ignore[attr-defined]
        yield c


def _admin(c: TestClient) -> dict:
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "admin",
        },
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}


def _list_with_items(c: TestClient, h: dict, names: list[str]) -> tuple[str, list[str]]:
    """A Tech Debt service + capability list carrying `names`, all in security scope."""
    from app.models.capability import CapabilityItem, CapabilityList
    from app.models.service import Service, ServiceKind

    svc_id = c.post(
        "/tech-debt/services", headers=h, json={"kind": "tech_debt", "title": "TD"}
    ).json()["id"]

    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=eng, future=True)() as s:
        svc = s.get(Service, uuid.UUID(svc_id))
        assert svc.kind == ServiceKind.TECH_DEBT
        cap_list = CapabilityList(service_id=svc.id, version=1)
        s.add(cap_list)
        s.flush()
        item_ids = []
        for n in names:
            it = CapabilityItem(capability_list_id=cap_list.id, name=n, security_related=True)
            s.add(it)
            s.flush()
            item_ids.append(str(it.id))
        s.commit()
        return str(cap_list.id), item_ids


def _membership(list_id: str) -> list | None:
    from app.models.capability import CapabilityList

    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=eng, future=True)() as s:
        return s.get(CapabilityList, uuid.UUID(list_id)).approved_membership


def _allow_list(c: TestClient) -> list[str]:
    from app.db.session import get_db
    from app.routes.attack import _client_tool_names

    gen = c.app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        return _client_tool_names(db, uuid.UUID(c.client_id))  # type: ignore[attr-defined]
    finally:
        gen.close()


# --- the snapshot -----------------------------------------------------------


@pytest.mark.unit
def test_approval_records_what_was_in_the_list(app_client) -> None:
    c = app_client
    h = _admin(c)
    list_id, item_ids = _list_with_items(c, h, ["Splunk", "CrowdStrike"])
    assert _membership(list_id) is None, "nothing is claimed before approval"

    r = c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=h)
    assert r.status_code == 200, r.text

    snap = _membership(list_id)
    assert sorted(e["name"] for e in snap) == ["CrowdStrike", "Splunk"]
    assert sorted(e["item_id"] for e in snap) == sorted(item_ids), (
        "item ids are recorded too — a name alone cannot be traced back to the row "
        "it came from once the name has changed"
    )


@pytest.mark.unit
def test_renaming_an_item_after_approval_does_not_rewrite_the_allow_list(app_client) -> None:
    """The sharpest door: `patch_capability_item` can change `name`.

    The allow-list is `frozenset(t.lower() for t in tools)` built from names, so
    a rename silently substitutes one tool for another in what the model may
    cite — and every citation already "confirmed" against the old name is now
    checked against a list that does not contain it.
    """
    c = app_client
    h = _admin(c)
    list_id, item_ids = _list_with_items(c, h, ["Splunk", "CrowdStrike"])
    c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=h)

    r = c.patch(f"/tech-debt/capability-items/{item_ids[0]}", headers=h, json={"name": "Renamed"})
    assert r.status_code == 200, r.text

    assert "Splunk" in _allow_list(c), "the approved name vanished from the allow-list"
    assert "Renamed" not in _allow_list(c), "an unapproved name entered the allow-list"


@pytest.mark.unit
def test_confirming_a_tool_non_security_after_approval_keeps_it_citable(app_client) -> None:
    """The confirm queue is a SANCTIONED post-approval membership change.

    `security_scope_filter` drops a row once a consultant agrees it is
    non-security. Doing that after an ATT&CK run left its already-confirmed
    citations checked against a list that no longer contained the tool. The
    snapshot is what makes those citations still mean something.
    """
    from app.models.capability import CapabilityItem

    c = app_client
    h = _admin(c)
    list_id, item_ids = _list_with_items(c, h, ["Splunk", "CrowdStrike"])
    c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=h)

    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=eng, future=True)() as s:
        it = s.get(CapabilityItem, uuid.UUID(item_ids[1]))
        it.security_related = False
        it.security_class_confirmed = True
        s.commit()

    assert "CrowdStrike" in _allow_list(c)


@pytest.mark.unit
def test_adding_an_item_after_approval_does_not_add_it_to_the_allow_list(app_client) -> None:
    from app.models.capability import CapabilityItem, CapabilityList

    c = app_client
    h = _admin(c)
    list_id, _ = _list_with_items(c, h, ["Splunk"])
    c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=h)

    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=eng, future=True)() as s:
        cap_list = s.get(CapabilityList, uuid.UUID(list_id))
        s.add(
            CapabilityItem(capability_list_id=cap_list.id, name="SneakedIn", security_related=True)
        )
        s.commit()

    assert _allow_list(c) == ["Splunk"]


@pytest.mark.unit
def test_re_approving_refreshes_the_snapshot(app_client) -> None:
    """Deliberately not a lock. Editing an approved list is a real workflow;
    what was missing is that the edit silently rewrote history."""
    c = app_client
    h = _admin(c)
    list_id, item_ids = _list_with_items(c, h, ["Splunk"])
    c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=h)
    c.patch(f"/tech-debt/capability-items/{item_ids[0]}", headers=h, json={"name": "Splunk ES"})
    assert _allow_list(c) == ["Splunk"]

    c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=h)
    assert _allow_list(c) == ["Splunk ES"]


# --- what must not change ---------------------------------------------------


@pytest.mark.unit
def test_a_draft_list_still_reads_live(app_client) -> None:
    """Mapping ATT&CK before approving the tech-debt list is a normal order of
    work — `_client_tool_names` says so, and a DRAFT has no approved membership
    to honour."""
    c = app_client
    h = _admin(c)
    list_id, item_ids = _list_with_items(c, h, ["Splunk"])
    c.patch(f"/tech-debt/capability-items/{item_ids[0]}", headers=h, json={"name": "Splunk ES"})
    assert _allow_list(c) == ["Splunk ES"]


@pytest.mark.unit
def test_a_list_approved_before_the_migration_still_reads_live(app_client) -> None:
    """C0: an older row parses unchanged. NULL means "nobody recorded this",
    which is not the same as "nothing was approved" — inventing a membership for
    it would assert something no consultant ever did."""
    from app.models.capability import CapabilityList, CapabilityListStatus

    c = app_client
    h = _admin(c)
    list_id, _ = _list_with_items(c, h, ["Splunk"])

    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=eng, future=True)() as s:
        cap_list = s.get(CapabilityList, uuid.UUID(list_id))
        cap_list.status = CapabilityListStatus.APPROVED
        cap_list.approved_membership = None
        s.commit()

    assert _allow_list(c) == ["Splunk"]


@pytest.mark.unit
def test_a_discarded_list_is_still_excluded_even_with_a_snapshot(app_client) -> None:
    """A consultant throwing a draft away must stop its tools being cited."""
    from app.models.capability import CapabilityList, CapabilityListStatus

    c = app_client
    h = _admin(c)
    list_id, _ = _list_with_items(c, h, ["Splunk"])
    c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=h)

    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=eng, future=True)() as s:
        s.get(CapabilityList, uuid.UUID(list_id)).status = CapabilityListStatus.DISCARDED
        s.commit()

    assert _allow_list(c) == []


@pytest.mark.unit
def test_the_snapshot_excludes_rows_already_out_of_security_scope(app_client) -> None:
    """The snapshot records the ATT&CK subset, not the whole portfolio — Tech
    Debt covers payroll and CRM since 0038."""
    from app.models.capability import CapabilityItem, CapabilityList

    c = app_client
    h = _admin(c)
    list_id, _ = _list_with_items(c, h, ["Splunk"])

    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=eng, future=True)() as s:
        cap_list = s.get(CapabilityList, uuid.UUID(list_id))
        s.add(
            CapabilityItem(
                capability_list_id=cap_list.id,
                name="Payroll",
                security_related=False,
                security_class_confirmed=True,
            )
        )
        s.commit()

    c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=h)
    assert [e["name"] for e in _membership(list_id)] == ["Splunk"]
    assert _allow_list(c) == ["Splunk"]
