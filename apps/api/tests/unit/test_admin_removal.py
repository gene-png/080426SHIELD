"""Admin removal of clients and users (issue 3).

The admin console previously had NO way to remove anything but an approved
email domain and a service: no client removal, no user list, no user removal.
This pins the replacement contract, which follows the existing
``archive_service`` precedent rather than hard-deleting:

  * ``DELETE /admin/clients/{cid}``   archives the tenant (data retained)
  * ``GET    /admin/clients/{cid}/users``  lists that tenant's users
  * ``PATCH  /admin/users/{uid}``     deactivates / reactivates a user

Archiving hides the tenant from the platform client list and the intake queue
org index without destroying assessments, deliverables, or the audit trail.
Deactivating flips ``User.is_active``, which routes/auth.py already enforces at
sign-in, so a deactivated user is locked out immediately.
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

PASSWORD = "correct horse battery staple!"


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "shield-removal.db"
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
        yield c


def _register(c: TestClient, email: str) -> dict:
    r = c.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": email.split("@")[0]},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _admin_bearer(c: TestClient) -> str:
    return _register(c, "admin@kentro.example")["tokens"]["access_token"]


def _auth(bearer: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {bearer}"}


def _make_client(c: TestClient, bearer: str, name: str) -> str:
    r = c.post("/admin/clients", headers=_auth(bearer), json={"legal_name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _list_client_ids(c: TestClient, bearer: str, **params) -> list[str]:
    r = c.get("/admin/clients", headers=_auth(bearer), params=params)
    assert r.status_code == 200, r.text
    return [row["id"] for row in r.json()["clients"]]


# --- client archive ---------------------------------------------------------


def test_archive_client_hides_it_from_the_list_but_retains_the_row(app_client):
    bearer = _admin_bearer(app_client)
    keep = _make_client(app_client, bearer, "Keep Corp")
    drop = _make_client(app_client, bearer, "Drop Corp")

    r = app_client.delete(f"/admin/clients/{drop}", headers=_auth(bearer))
    assert r.status_code == 204, r.text

    ids = _list_client_ids(app_client, bearer)
    assert keep in ids
    assert drop not in ids, "archived client must drop out of the default list"

    # Retained, not destroyed: it is still fetchable and still listable when
    # the caller explicitly asks for archived rows.
    assert app_client.get(f"/admin/clients/{drop}", headers=_auth(bearer)).status_code == 200
    assert drop in _list_client_ids(app_client, bearer, include_archived=True)


def test_archiving_an_unknown_client_is_a_typed_404(app_client):
    bearer = _admin_bearer(app_client)
    missing = "00000000-0000-4000-8000-000000000000"
    r = app_client.delete(f"/admin/clients/{missing}", headers=_auth(bearer))
    assert r.status_code == 404


def test_archive_client_writes_an_audit_row(app_client):
    bearer = _admin_bearer(app_client)
    cid = _make_client(app_client, bearer, "Audited Corp")
    app_client.delete(f"/admin/clients/{cid}", headers=_auth(bearer))

    r = app_client.get("/admin/audit-entries", headers=_auth(bearer))
    assert r.status_code == 200, r.text
    actions = [e["action"] for e in r.json()["entries"]]
    assert "client.archived" in actions


def test_client_role_user_cannot_archive_a_client(app_client):
    admin = _admin_bearer(app_client)
    cid = _make_client(app_client, admin, "Protected Corp")
    # A self-registered user with no admin role.
    outsider = _register(app_client, "someone@atlas.example")["tokens"]["access_token"]

    r = app_client.delete(f"/admin/clients/{cid}", headers=_auth(outsider))
    assert r.status_code in (401, 403)
    assert cid in _list_client_ids(app_client, admin)


# --- user list + deactivate -------------------------------------------------


def test_list_users_for_a_client(app_client):
    bearer = _admin_bearer(app_client)
    cid = _make_client(app_client, bearer, "Staffed Corp")

    r = app_client.get(f"/admin/clients/{cid}/users", headers=_auth(bearer))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "users" in body
    assert isinstance(body["users"], list)
    # Shape check on the row contract the Management UI renders.
    for row in body["users"]:
        assert {"id", "email", "is_active"} <= set(row)


def test_deactivate_user_blocks_sign_in_and_reactivate_restores_it(app_client):
    bearer = _admin_bearer(app_client)
    victim = _register(app_client, "victim@atlas.example")
    uid = victim["user"]["id"]

    # Baseline: the account signs in fine.
    ok = app_client.post(
        "/auth/login", json={"email": "victim@atlas.example", "password": PASSWORD}
    )
    assert ok.status_code == 200, ok.text

    r = app_client.patch(f"/admin/users/{uid}", headers=_auth(bearer), json={"is_active": False})
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False

    blocked = app_client.post(
        "/auth/login", json={"email": "victim@atlas.example", "password": PASSWORD}
    )
    assert blocked.status_code == 403, "deactivated user must not sign in"
    assert blocked.json()["error"]["reason"] == "account_deactivated"

    # Reversible — this is deactivation, not deletion.
    back = app_client.patch(f"/admin/users/{uid}", headers=_auth(bearer), json={"is_active": True})
    assert back.status_code == 200, back.text
    again = app_client.post(
        "/auth/login", json={"email": "victim@atlas.example", "password": PASSWORD}
    )
    assert again.status_code == 200, again.text


def test_admin_cannot_deactivate_their_own_account(app_client):
    reg = _register(app_client, "admin@kentro.example")
    bearer = reg["tokens"]["access_token"]
    my_id = reg["user"]["id"]

    r = app_client.patch(f"/admin/users/{my_id}", headers=_auth(bearer), json={"is_active": False})
    assert r.status_code == 400, "locking yourself out must be refused loudly"
    # Typed, friendly error via the D-016 envelope — never a raw validation dump.
    err = r.json()["error"]
    assert err["reason"] == "cannot_deactivate_self"
    assert "another admin" in err["message"]


def test_deactivate_user_writes_an_audit_row(app_client):
    bearer = _admin_bearer(app_client)
    uid = _register(app_client, "logged@atlas.example")["user"]["id"]
    app_client.patch(f"/admin/users/{uid}", headers=_auth(bearer), json={"is_active": False})

    r = app_client.get("/admin/audit-entries", headers=_auth(bearer))
    actions = [e["action"] for e in r.json()["entries"]]
    assert "user.deactivated" in actions
