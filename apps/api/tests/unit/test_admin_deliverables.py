"""Contract tests for GET /admin/deliverables (IA appendix, Phase D).

The client-facing route (`/clients/{id}/deliverables`) deliberately shows ONLY
released rows — that is the §12 release rule. An admin needs the opposite: every
deliverable a tenant has, including the ones no client can see yet, because the
question they are answering is "what have we produced and what is out?".

The status is derived from columns that already exist, so there is no migration
and no new state to keep in sync:

    superseded_by set  -> superseded   (not client-visible)
    released_at set    -> released     (CLIENT-VISIBLE)
    finalized_at set   -> generated    (not client-visible)

`client_visible` is asserted independently of `status` rather than inferred from
it: it is the field a consultant will actually trust when deciding whether the
client has already seen something, and a wrong answer there is the expensive
kind of wrong.
"""

from __future__ import annotations

import os
import uuid as _uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models._common import utcnow


@pytest.fixture()
def env(tmp_path):
    """App + session factory + two tenants, so isolation is testable."""
    db_path = tmp_path / "shield-admin-deliverables.db"
    url = f"sqlite:///{db_path}"
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

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain

    seed = TestSession()
    tenant_a = _Client(legal_name="Tenant A")
    tenant_b = _Client(legal_name="Tenant B")
    seed.add_all([tenant_a, tenant_b])
    seed.flush()
    # The admin self-registers against tenant A's domain; D-004 makes the first
    # registrant an admin regardless.
    seed.add(_ClientDomain(client_id=tenant_a.id, domain="example.com"))
    seed.commit()
    ids = (str(tenant_a.id), str(tenant_b.id))
    seed.close()

    with TestClient(app) as c:
        yield c, TestSession, ids[0], ids[1]


def _admin_bearer(client: TestClient) -> tuple[str, str]:
    r = client.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "Admin",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["user"]["role"] == "admin"
    # services.opened_by is NOT NULL, so seeding needs a real user id.
    return r.json()["tokens"]["access_token"], r.json()["user"]["id"]


def _client_bearer(client: TestClient) -> str:
    r = client.post(
        "/auth/register",
        json={
            "email": "user@example.com",
            "password": "correct horse battery staple!",
            "display_name": "User",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["user"]["role"] == "client"
    return r.json()["tokens"]["access_token"]


def _service(db: Session, client_id: str, title: str, opened_by: str):
    from app.models.service import Service, ServiceKind, ServiceStatus

    svc = Service(
        kind=ServiceKind.NIST_CSF,
        status=ServiceStatus.IN_PROGRESS,
        title=title,
        client_id=_uuid.UUID(client_id),
        opened_by=_uuid.UUID(opened_by),
    )
    db.add(svc)
    db.flush()
    return svc


def _deliverable(db: Session, service_id, *, version: int, **kw):
    from app.models.deliverable import Deliverable

    deliv = Deliverable(
        service_id=service_id,
        title=f"Report v{version}",
        version=version,
        finalized_at=kw.pop("finalized_at", utcnow()),
        **kw,
    )
    db.add(deliv)
    db.flush()
    return deliv


def _get(client: TestClient, bearer: str, tenant: str):
    return client.get(
        "/admin/deliverables",
        headers={"Authorization": f"Bearer {bearer}", "X-Client-Id": tenant},
    )


@pytest.mark.unit
def test_lists_unreleased_deliverables(env) -> None:
    """The whole point: rows the client route hides must appear here."""
    app_client, TestSession, tenant_a, _ = env
    bearer, admin_id = _admin_bearer(app_client)

    db = TestSession()
    svc = _service(db, tenant_a, "CSF Assessment", admin_id)
    _deliverable(db, svc.id, version=1)  # finalized, never released
    db.commit()
    db.close()

    r = _get(app_client, bearer, tenant_a)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "generated"
    assert items[0]["client_visible"] is False
    assert items[0]["service_title"] == "CSF Assessment"


@pytest.mark.unit
def test_status_derivation_across_all_three_states(env) -> None:
    app_client, TestSession, tenant_a, _ = env
    bearer, admin_id = _admin_bearer(app_client)

    db = TestSession()
    svc = _service(db, tenant_a, "CSF Assessment", admin_id)
    v1 = _deliverable(db, svc.id, version=1)
    v2 = _deliverable(db, svc.id, version=2, released_at=utcnow())
    # v1 was superseded by v2. Superseded wins over released: a superseded row
    # is history, whatever it once was.
    v1.superseded_by = v2.id
    v1.released_at = utcnow() - timedelta(days=1)
    _deliverable(db, svc.id, version=3)
    db.commit()
    db.close()

    r = _get(app_client, bearer, tenant_a)
    assert r.status_code == 200, r.text
    by_version = {i["version"]: i for i in r.json()["items"]}

    assert by_version[1]["status"] == "superseded"
    assert by_version[1]["client_visible"] is False

    assert by_version[2]["status"] == "released"
    assert by_version[2]["client_visible"] is True

    assert by_version[3]["status"] == "generated"
    assert by_version[3]["client_visible"] is False


@pytest.mark.unit
def test_orders_newest_version_first(env) -> None:
    app_client, TestSession, tenant_a, _ = env
    bearer, admin_id = _admin_bearer(app_client)

    db = TestSession()
    svc = _service(db, tenant_a, "CSF Assessment", admin_id)
    for v in (1, 2, 3):
        _deliverable(db, svc.id, version=v)
    db.commit()
    db.close()

    r = _get(app_client, bearer, tenant_a)
    assert [i["version"] for i in r.json()["items"]] == [3, 2, 1]


@pytest.mark.unit
def test_never_leaks_another_tenants_deliverables(env) -> None:
    app_client, TestSession, tenant_a, tenant_b = env
    bearer, admin_id = _admin_bearer(app_client)

    db = TestSession()
    svc_a = _service(db, tenant_a, "A's assessment", admin_id)
    _deliverable(db, svc_a.id, version=1)
    svc_b = _service(db, tenant_b, "B's assessment", admin_id)
    _deliverable(db, svc_b.id, version=1)
    db.commit()
    db.close()

    titles_a = [i["service_title"] for i in _get(app_client, bearer, tenant_a).json()["items"]]
    assert titles_a == ["A's assessment"]

    titles_b = [i["service_title"] for i in _get(app_client, bearer, tenant_b).json()["items"]]
    assert titles_b == ["B's assessment"]


@pytest.mark.unit
def test_client_role_is_refused(env) -> None:
    """This is an admin surface: it shows unreleased work by design."""
    app_client, _TestSession, tenant_a, _ = env
    _admin_bearer(app_client)  # first registrant takes the admin role
    bearer = _client_bearer(app_client)

    r = _get(app_client, bearer, tenant_a)
    assert r.status_code == 403, r.text


@pytest.mark.unit
def test_empty_tenant_returns_an_empty_list_not_an_error(env) -> None:
    app_client, _TestSession, tenant_a, _ = env
    bearer, admin_id = _admin_bearer(app_client)
    r = _get(app_client, bearer, tenant_a)
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []
