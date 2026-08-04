"""Contract tests for the deliverable release-to-client flow (Sprint 5 T1, D-025).

Release is a NEW admin-only action: until a consultant explicitly releases a
finalized deliverable, the client sees nothing (Master Spec §12 release rule).
These tests lock the release route, the client read route, and the artifact
download allow/deny matrix.
"""

from __future__ import annotations

import os
import uuid as _uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.storage.local import LocalFilesystemStorage


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "shield-release.db"
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
    app.dependency_overrides[_storage_dep] = lambda: storage

    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain

    _seed = TestSession()
    _tenant = _Client(legal_name="Test Tenant")
    _seed.add(_tenant)
    _seed.flush()
    _seed.add(_ClientDomain(client_id=_tenant.id, domain="example.com"))
    _seed.commit()
    _cid = str(_tenant.id)
    _seed.close()

    c = TestClient(app, headers={"X-Client-Id": _cid})
    c._tenant_id = _cid  # type: ignore[attr-defined]
    with c:
        yield c


def _register(c: TestClient, email: str) -> dict:
    r = c.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple!",
            "display_name": email.split("@")[0],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _finalized_csf_deliverable(c: TestClient, bearer: str) -> dict:
    """Open CSF service, score tier 3, approve, finalize. Returns the deliverable."""
    sr = c.post(
        "/csf/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"kind": "nist_csf", "title": "Atlas - CSF"},
    )
    svc_id = sr.json()["id"]
    a = c.post(
        f"/csf/services/{svc_id}/assessments",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assess = a.json()
    for ans in assess["answers"]:
        c.patch(
            f"/csf/answers/{ans['id']}",
            headers={"Authorization": f"Bearer {bearer}"},
            json={"maturity_tier": 3},
        )
    c.post(
        f"/csf/assessments/{assess['id']}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    fin = c.post(
        f"/csf/services/{svc_id}/deliverables/finalize",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert fin.status_code == 201, fin.text
    return fin.json()


# --- Release route -----------------------------------------------------------


@pytest.mark.unit
def test_release_requires_finalized(app_client) -> None:
    """Releasing a deliverable that was never finalized -> typed 409."""
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]

    # Fabricate an unfinalized deliverable directly so the route sees a row
    # without finalized_at.
    from app.db.session import get_db
    from app.models.deliverable import Deliverable
    from app.models.service import Service, ServiceKind

    gen = c.app.dependency_overrides[get_db]()
    db = next(gen)
    svc = Service(
        kind=ServiceKind.NIST_CSF,
        title="raw",
        client_id=_uuid.UUID(c._tenant_id),
        opened_by=_uuid.UUID(admin["user"]["id"]),
    )
    db.add(svc)
    db.flush()
    deliv = Deliverable(service_id=svc.id, title="unfinalized", version=1)
    db.add(deliv)
    db.commit()
    deliv_id = str(deliv.id)
    db.close()

    r = c.post(
        f"/csf/deliverables/{deliv_id}/release",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "not_finalized"


@pytest.mark.unit
def test_release_sets_fields_and_audits(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    deliv = _finalized_csf_deliverable(c, bearer)
    assert deliv["released_at"] is None

    r = c.post(
        f"/csf/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["released_at"] is not None
    assert body["released_by"] == admin["user"]["id"]

    # An audit row *.deliverable.released was written.
    from app.db.session import get_db
    from app.models.audit_entry import AuditEntry

    gen = c.app.dependency_overrides[get_db]()
    db = next(gen)
    rows = (
        db.execute(select(AuditEntry).where(AuditEntry.action == "csf.deliverable.released"))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert str(rows[0].target_id) == deliv["id"]
    db.close()


@pytest.mark.unit
def test_release_is_idempotent(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    deliv = _finalized_csf_deliverable(c, bearer)

    r1 = c.post(
        f"/csf/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r1.status_code == 200, r1.text
    first_release = r1.json()["released_at"]

    r2 = c.post(
        f"/csf/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r2.status_code == 200, r2.text
    # No-op: same released_at, no second audit row.
    assert r2.json()["released_at"] == first_release

    from app.db.session import get_db
    from app.models.audit_entry import AuditEntry

    gen = c.app.dependency_overrides[get_db]()
    db = next(gen)
    rows = (
        db.execute(select(AuditEntry).where(AuditEntry.action == "csf.deliverable.released"))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    db.close()


@pytest.mark.unit
def test_release_requires_admin(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    deliv = _finalized_csf_deliverable(c, bearer_admin)
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    r = c.post(
        f"/csf/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 403, r.text


@pytest.mark.unit
def test_release_wrong_service_kind_404(app_client) -> None:
    """A CSF deliverable id cannot be released through the zt route."""
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    deliv = _finalized_csf_deliverable(c, bearer)
    r = c.post(
        f"/zt/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 404, r.text


# --- Client list route -------------------------------------------------------


@pytest.mark.unit
def test_client_list_only_released_own_tenant(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    cid = client["user"]["client_id"]

    deliv = _finalized_csf_deliverable(c, bearer_admin)

    # Before release: the client sees nothing.
    r = c.get(
        f"/clients/{cid}/deliverables",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []

    # Release, then the client sees exactly one row with the expected shape.
    c.post(
        f"/csf/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    )
    r = c.get(
        f"/clients/{cid}/deliverables",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["id"] == deliv["id"]
    assert row["released_at"] is not None
    assert row["version"] == deliv["version"]
    assert row["pdf_filename"].endswith(".pdf")
    assert row["service_kind"] == "nist_csf"


@pytest.mark.unit
def test_client_list_cross_tenant_404(app_client) -> None:
    """A client asking for another tenant's list gets 404 (never 403)."""
    c = app_client
    _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    r = c.get(
        f"/clients/{_uuid.uuid4()}/deliverables",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 404, r.text


# --- Artifact download allow/deny matrix -------------------------------------


@pytest.mark.unit
def test_client_can_download_released_deliverable_artifacts(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    deliv = _finalized_csf_deliverable(c, bearer_admin)

    # Unreleased: client denied on every format.
    for key in ("pdf_artifact_id", "xlsx_artifact_id", "docx_artifact_id"):
        d = c.get(
            f"/artifacts/{deliv[key]}/download",
            headers={"Authorization": f"Bearer {bearer_client}"},
        )
        assert d.status_code == 404, f"{key}: {d.status_code}"

    # Release, then the client can download every format.
    c.post(
        f"/csf/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    )
    for key in ("pdf_artifact_id", "xlsx_artifact_id", "docx_artifact_id"):
        d = c.get(
            f"/artifacts/{deliv[key]}/download",
            headers={"Authorization": f"Bearer {bearer_client}"},
        )
        assert d.status_code == 200, f"{key}: {d.status_code} {d.text}"


@pytest.mark.unit
def test_client_cannot_download_other_tenants_released_artifact(app_client) -> None:
    """Cross-tenant deny: a client of tenant B cannot download tenant A's
    RELEASED deliverable artifact — the tenant boundary 404s (never 403), even
    though the deliverable is released."""
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    deliv = _finalized_csf_deliverable(c, bearer_admin)
    c.post(
        f"/csf/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    )

    # Seed a SECOND tenant (own domain) and register a client user into it.
    from app.db.session import get_db
    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain

    gen = c.app.dependency_overrides[get_db]()
    db = next(gen)
    tenant_b = _Client(legal_name="Beta Tenant")
    db.add(tenant_b)
    db.flush()
    db.add(_ClientDomain(client_id=tenant_b.id, domain="beta.example"))
    db.commit()
    tenant_b_id = str(tenant_b.id)
    db.close()

    client_b = _register(c, "client@beta.example")
    assert client_b["user"]["client_id"] == tenant_b_id
    bearer_b = client_b["tokens"]["access_token"]

    d = c.get(
        f"/artifacts/{deliv['pdf_artifact_id']}/download",
        headers={"Authorization": f"Bearer {bearer_b}", "X-Client-Id": tenant_b_id},
    )
    assert d.status_code == 404, d.text


@pytest.mark.unit
def test_client_cannot_download_non_deliverable_artifact(app_client) -> None:
    """A non-deliverable artifact the client didn't upload stays 404 for them."""
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]

    up = c.post(
        "/artifacts",
        headers={"Authorization": f"Bearer {bearer_admin}"},
        files={"file": ("notes.txt", b"internal admin notes", "text/plain")},
    )
    assert up.status_code == 201, up.text
    art_id = up.json()["id"]

    d = c.get(
        f"/artifacts/{art_id}/download",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert d.status_code == 404, d.text
