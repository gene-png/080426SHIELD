"""#1262 guard: the workspace's `?client_id=` cannot widen a client's access.

The web proxy now forwards an upload's `?client_id=` as `X-Client-Id` (so an
admin workspace's upload is filed under its own tenant, not the shared
cookie). The parameter must not widen access: a CLIENT-role user who sends
another tenant's id is still pinned to its own client by `current_client`,
and `POST /artifacts` files under its own client. Through the real route,
with two tenants.

A guard, not a fix: it holds on main, and pins that it keeps holding.
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
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.unit


@pytest.fixture()
def env(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    db_path = tmp_path / "shield-artifacts-scope.db"
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
    tenant_a = Client(legal_name=None)
    tenant_b = Client(legal_name=None)
    seed.add_all([tenant_a, tenant_b])
    seed.flush()
    seed.add(ClientDomain(client_id=tenant_a.id, domain="example.com"))
    seed.add(ClientDomain(client_id=tenant_b.id, domain="other.example"))
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


def test_a_client_uploading_with_another_tenants_id_files_under_its_own(env) -> None:
    """#1262's twin guard: the upload's `?client_id=` cannot file a client's
    document under another tenant either."""
    app_client, TestSession = env
    _register(app_client, "admin@example.com")  # first registrant: platform admin
    a = _register(app_client, "alice@example.com")
    _register(app_client, "bob@other.example")

    from app.models.artifact import Artifact
    from app.models.user import User

    with TestSession() as db:
        tenant = {
            u.email: u.client_id
            for u in db.execute(select(User)).scalars()
            if u.email in {"alice@example.com", "bob@other.example"}
        }
    r = app_client.post(
        "/artifacts",
        headers={
            "Authorization": f"Bearer {a['tokens']['access_token']}",
            "X-Client-Id": str(tenant["bob@other.example"]),
        },
        files={"file": ("a.csv", b"host,os\na,linux\n", "text/csv")},
    )
    assert r.status_code == 201, r.text
    with TestSession() as db:
        row = db.get(Artifact, uuid.UUID(r.json()["id"]))
        assert row is not None
        assert row.client_id == tenant["alice@example.com"]
