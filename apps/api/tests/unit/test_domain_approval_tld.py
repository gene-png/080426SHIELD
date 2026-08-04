"""Reject reserved/special-use TLDs at domain-approval time (Sprint 2 T9, D-018).

The email validator (pydantic ``EmailStr`` at registration) 422s special-use /
reserved names -- ``.test``, ``.invalid``, ``.localhost`` -- but ``.example`` is
fine. Before this guard an admin could approve such a domain, stranding it as
approved-but-unregistrable (the seeded ``beacon.test`` problem). The add-domain
route now rejects those with a typed 422 ``{reason: "domain_reserved_tld"}``
(the D-016 dict-detail pattern), reusing email-validator's own reserved-name
check rather than a hand-rolled TLD list.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def app_ctx(tmp_path):
    """Yield (TestClient, session_factory) sharing one SQLite file so a test can
    plant a pre-existing row directly and prove reads are not gated by the new
    add-time check."""
    db_path = tmp_path / "shield-tld.db"
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
    with TestClient(app) as c:
        yield c, TestSession


def _admin_bearer(c: TestClient) -> str:
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "admin",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["tokens"]["access_token"]


def _make_client(c: TestClient, bearer: str, name: str = "Acme Corp") -> str:
    r = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": name},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.unit
@pytest.mark.parametrize("domain", ["beacon.test", "acme.invalid", "corp.localhost"])
def test_reserved_tld_rejected_with_typed_reason(app_ctx, domain: str) -> None:
    c, _ = app_ctx
    bearer = _admin_bearer(c)
    cid = _make_client(c, bearer)
    r = c.post(
        f"/admin/clients/{cid}/domains",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"domain": domain},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["reason"] == "domain_reserved_tld"
    # Friendly, non-empty human copy for the Management UI (never a raw dump).
    assert r.json()["error"]["message"]


@pytest.mark.unit
def test_example_tld_still_approved(app_ctx) -> None:
    """.example is NOT a reserved name to the validator -- users can register on
    it -- so approval must succeed (this is the beacon.example migration target)."""
    c, _ = app_ctx
    bearer = _admin_bearer(c)
    cid = _make_client(c, bearer)
    r = c.post(
        f"/admin/clients/{cid}/domains",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"domain": "beacon.example"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["domain"] == "beacon.example"


@pytest.mark.unit
def test_normal_domain_still_approved(app_ctx) -> None:
    c, _ = app_ctx
    bearer = _admin_bearer(c)
    cid = _make_client(c, bearer)
    r = c.post(
        f"/admin/clients/{cid}/domains",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"domain": "acme.com"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["domain"] == "acme.com"


@pytest.mark.unit
def test_existing_reserved_row_unaffected(app_ctx) -> None:
    """The guard is add-time only: a domain approved before the guard existed
    still lists and removes normally (no retroactive breakage)."""
    import uuid

    from app.models.client_domain import ClientDomain

    c, TestSession = app_ctx
    bearer = _admin_bearer(c)
    cid = _make_client(c, bearer)
    h = {"Authorization": f"Bearer {bearer}"}

    # Plant a legacy beacon.test row directly, bypassing the add-domain route
    # (created_by is nullable/SET NULL, so no user reference is needed).
    db = TestSession()
    try:
        db.add(ClientDomain(client_id=uuid.UUID(cid), domain="beacon.test", created_by=None))
        db.commit()
    finally:
        db.close()

    lst = c.get(f"/admin/clients/{cid}/domains", headers=h)
    assert lst.status_code == 200, lst.text
    rows = {d["domain"]: d["id"] for d in lst.json()["domains"]}
    assert "beacon.test" in rows

    rm = c.delete(f"/admin/clients/{cid}/domains/{rows['beacon.test']}", headers=h)
    assert rm.status_code == 204
