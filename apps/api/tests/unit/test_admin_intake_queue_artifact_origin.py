"""#1054 (IN-2): the admin intake queue says WHERE each artifact came from.

The org page's "Uploaded documents" list rendered every `Artifact` row of the
tenant, and a released deliverable's PDF/XLSX/DOCX files are `Artifact` rows
too (origin `consultant_approved`), so twelve generated reports sat in a list
headed as the client's uploads. The stored `origin` is the discriminator; the
route must carry it so the page can split the list without guessing from a
filename.

The client upload goes through the real upload route; the generated report is
written the way the deliverable exporters write it (an `Artifact` with
`origin=CONSULTANT_APPROVED`), because building a whole released deliverable
here would test the exporters, not this route.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def env(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    db_path = tmp_path / "shield-intake-origin.db"
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
    from app.models.client import Client
    from app.models.client_domain import ClientDomain
    from app.routes.artifacts import _storage_dep
    from app.storage.local import LocalFilesystemStorage

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_storage_dep] = lambda: LocalFilesystemStorage(tmp_path / "storage")

    seed = TestSession()
    tenant = Client(legal_name=None)
    seed.add(tenant)
    seed.flush()
    seed.add(ClientDomain(client_id=tenant.id, domain="example.com"))
    seed.commit()
    seed.close()

    with TestClient(app) as c:
        yield c, TestSession


def _register(client: TestClient, email: str) -> dict:
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple!",
            "display_name": email.split("@")[0],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.unit
def test_intake_queue_rows_carry_the_stored_origin(env) -> None:
    app_client, TestSession = env
    admin = _register(app_client, "admin@example.com")
    assert admin["user"]["role"] == "admin"
    admin_bearer = admin["tokens"]["access_token"]
    member = _register(app_client, "client@example.com")
    assert member["user"]["role"] == "client"
    client_bearer = member["tokens"]["access_token"]

    up = app_client.post(
        "/artifacts",
        headers={"Authorization": f"Bearer {client_bearer}"},
        files={"file": ("network-inventory.csv", b"host,os\na,linux\n", "text/csv")},
    )
    assert up.status_code == 201, up.text
    upload_id = up.json()["id"]

    from app.models.artifact import Artifact, ArtifactOrigin
    from app.models.user import User

    db = TestSession()
    admin_row = db.execute(select(User).where(User.email == "admin@example.com")).scalar_one()
    client_row = db.execute(select(User).where(User.email == "client@example.com")).scalar_one()
    data = b"%PDF-1.4 generated report"
    report = Artifact(
        client_id=client_row.client_id,
        title="NIST-CSF-Report-v1.pdf",
        file_storage_key="deliverable/x/y/NIST-CSF-Report-v1.pdf",
        mime_type="application/pdf",
        size_bytes=len(data),
        sha256=sha256(data).hexdigest(),
        origin=ArtifactOrigin.CONSULTANT_APPROVED,
        stage="deliverable",
        uploaded_by=admin_row.id,
    )
    db.add(report)
    db.commit()
    report_id = str(report.id)
    tenant_id = str(client_row.client_id)
    db.close()

    r = app_client.get(
        f"/admin/intake-queue?client_id={tenant_id}",
        headers={"Authorization": f"Bearer {admin_bearer}"},
    )
    assert r.status_code == 200, r.text
    by_id = {a["id"]: a for a in r.json()["artifacts"]}
    assert set(by_id) == {upload_id, report_id}
    assert by_id[upload_id]["origin"] == "client_upload"
    assert by_id[report_id]["origin"] == "consultant_approved"
