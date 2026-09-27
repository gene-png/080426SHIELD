"""Archiving a client ends every session its users hold (#652, D-103).

Gene's decision, 2026-09-26: archiving a client ends ALL of its users'
sessions, access and refresh alike, the same way a password reset does. Before
this, nothing on the request path read a client's `archived_at`, so a user of
an archived tenant kept a working access token until its TTL and a refresh
token that went on minting new ones.

The three session-ending sites (reset, deactivation, archive) now share one
helper, so the tests here go through each ENDPOINT rather than the helper: the
wiring is what a refactor changes.

Every token under test is minted a few seconds in the past (`app.security.jwt
._now`), so its whole-second `iat` is strictly before the cutoff the endpoint
stamps. A token minted in the cutoff's own second is accepted by the owner's
rule (#658), which is pinned in `test_auth_reauth.py`, not here.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_PASSWORD = "correct horse battery staple!"
_CUTOFF_REASON = "credentials_changed"


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "shield-session-ending.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url

    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    test_engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)

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


@pytest.fixture()
def minted_in_the_past(monkeypatch) -> None:
    """Every token minted from here on carries an `iat` five seconds ago."""
    past = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=5)
    monkeypatch.setattr("app.security.jwt._now", lambda: past)


def _register(client: TestClient, email: str) -> dict:
    r = client.post(
        "/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": email.split("@")[0]},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _auth(access: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access}"}


def _me(client: TestClient, access: str):
    return client.get("/auth/me", headers=_auth(access))


def _user_row(email: str):
    from app.models.user import User

    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=eng, future=True)() as s:
        return s.query(User).filter_by(email=email).one()


def _rotation_state(email: str) -> tuple:
    u = _user_row(email)
    return u.active_refresh_jti, u.previous_refresh_jti, u.refresh_rotated_at


def _archive(client: TestClient, admin_access: str, email: str) -> None:
    cid = _user_row(email).client_id
    assert cid is not None, f"setup: {email} has no client to archive"
    r = client.delete(f"/admin/clients/{cid}", headers=_auth(admin_access))
    assert r.status_code == 204, r.text


# --- client archive -----------------------------------------------------------


@pytest.mark.unit
def test_archiving_a_client_refuses_its_users_earlier_access_tokens(
    app_client: TestClient, minted_in_the_past
) -> None:
    admin = _register(app_client, "admin@kentro.example")["tokens"]["access_token"]
    first = _register(app_client, "first@atlas.example")["tokens"]["access_token"]
    second = _register(app_client, "second@atlas.example")["tokens"]["access_token"]
    assert _user_row("first@atlas.example").client_id == (
        _user_row("second@atlas.example").client_id
    ), "setup: both users must belong to the one client being archived"
    for token in (first, second):
        assert _me(app_client, token).status_code == 200, "setup: the token must work first"

    _archive(app_client, admin, "first@atlas.example")

    for token in (first, second):
        r = _me(app_client, token)
        assert r.status_code == 401, r.text
        assert r.json()["error"]["reason"] == _CUTOFF_REASON, r.text


@pytest.mark.unit
def test_archiving_a_client_ends_its_users_refresh_families(
    app_client: TestClient, minted_in_the_past
) -> None:
    admin = _register(app_client, "admin@kentro.example")["tokens"]["access_token"]
    refresh = _register(app_client, "first@atlas.example")["tokens"]["refresh_token"]
    rotated = app_client.post("/auth/refresh", json={"refresh_token": refresh})
    assert rotated.status_code == 200, rotated.text
    assert _rotation_state("first@atlas.example")[1] is not None, "setup: no previous jti"

    _archive(app_client, admin, "first@atlas.example")

    assert _rotation_state("first@atlas.example") == (None, None, None)
    for presented in (refresh, rotated.json()["refresh_token"]):
        r = app_client.post("/auth/refresh", json={"refresh_token": presented})
        assert r.status_code == 401, r.text


@pytest.mark.unit
def test_archiving_a_client_leaves_other_tenants_and_the_admin_signed_in(
    app_client: TestClient, minted_in_the_past
) -> None:
    admin = _register(app_client, "admin@kentro.example")["tokens"]["access_token"]
    _register(app_client, "first@atlas.example")
    other = _register(app_client, "bystander@other-tenant.example")["tokens"]["access_token"]
    assert _user_row("bystander@other-tenant.example").client_id != (
        _user_row("first@atlas.example").client_id
    ), "setup: the bystander must belong to a different client"

    _archive(app_client, admin, "first@atlas.example")

    assert _me(app_client, other).status_code == 200
    assert _me(app_client, admin).status_code == 200
    assert _user_row("bystander@other-tenant.example").credentials_changed_at is None
    assert _user_row("admin@kentro.example").credentials_changed_at is None


@pytest.mark.unit
def test_archiving_an_already_archived_client_does_not_move_the_cutoff(
    app_client: TestClient, minted_in_the_past
) -> None:
    """The second DELETE is the existing no-op. It must not stamp a later
    cutoff, which would sign out anyone who signed in since the archive."""
    admin = _register(app_client, "admin@kentro.example")["tokens"]["access_token"]
    _register(app_client, "first@atlas.example")
    _archive(app_client, admin, "first@atlas.example")
    first_cutoff = _user_row("first@atlas.example").credentials_changed_at
    assert first_cutoff is not None

    _archive(app_client, admin, "first@atlas.example")

    assert _user_row("first@atlas.example").credentials_changed_at == first_cutoff


# --- deactivation -------------------------------------------------------------


@pytest.mark.unit
def test_a_reactivated_user_cannot_reuse_an_access_token_from_before_deactivation(
    app_client: TestClient, minted_in_the_past
) -> None:
    """Deactivation already refused access tokens through `is_active`, but only
    while the account stayed inactive. Ending sessions the way a reset does
    means reactivation does not bring the old ones back."""
    admin = _register(app_client, "admin@kentro.example")["tokens"]["access_token"]
    victim = _register(app_client, "victim@atlas.example")
    old_access = victim["tokens"]["access_token"]
    uid = victim["user"]["id"]

    for active in (False, True):
        r = app_client.patch(
            f"/admin/users/{uid}", headers=_auth(admin), json={"is_active": active}
        )
        assert r.status_code == 200, r.text

    r = _me(app_client, old_access)
    assert r.status_code == 401, r.text
    assert r.json()["error"]["reason"] == _CUTOFF_REASON, r.text


@pytest.mark.unit
def test_a_deactivation_still_clears_every_rotation_field(
    app_client: TestClient, minted_in_the_past
) -> None:
    admin = _register(app_client, "admin@kentro.example")["tokens"]["access_token"]
    victim = _register(app_client, "victim@atlas.example")
    app_client.post("/auth/refresh", json={"refresh_token": victim["tokens"]["refresh_token"]})
    assert _rotation_state("victim@atlas.example")[1] is not None, "setup: no previous jti"

    r = app_client.patch(
        f"/admin/users/{victim['user']['id']}", headers=_auth(admin), json={"is_active": False}
    )
    assert r.status_code == 200, r.text
    assert _rotation_state("victim@atlas.example") == (None, None, None)


# --- review round 1 (#726) ------------------------------------------------------

#: Cause-neutral: the same refusal follows a password reset, a deactivation and
#: a client archive, so it may not name any one of them. "Your password was
#: changed" told an archived client's users their account had been tampered with.
_CUTOFF_MESSAGE = "This session has ended. Sign in again."


@pytest.mark.unit
def test_the_cutoff_refusal_names_no_cause_after_an_archive_or_a_deactivation(
    app_client: TestClient, minted_in_the_past
) -> None:
    admin = _register(app_client, "admin@kentro.example")["tokens"]["access_token"]
    archived = _register(app_client, "first@atlas.example")["tokens"]["access_token"]
    victim = _register(app_client, "victim@other-tenant.example")
    _archive(app_client, admin, "first@atlas.example")
    uid = victim["user"]["id"]
    for active in (False, True):
        r = app_client.patch(
            f"/admin/users/{uid}", headers=_auth(admin), json={"is_active": active}
        )
        assert r.status_code == 200, r.text

    for token in (archived, victim["tokens"]["access_token"]):
        r = _me(app_client, token)
        assert r.status_code == 401, r.text
        error = r.json()["error"]
        assert (error["reason"], error["message"]) == (_CUTOFF_REASON, _CUTOFF_MESSAGE)


@pytest.mark.unit
def test_archiving_a_client_ends_an_inactive_users_sessions_too(
    app_client: TestClient, minted_in_the_past
) -> None:
    """D-103 covers EVERY user of the client. An inactive user whose sessions
    were never ended (made inactive before #652, when deactivation did not set
    a cutoff) must be cleared by the archive and stay refused if reactivated.
    An `is_active` filter on the archive's user query would keep every other
    test here green."""
    from sqlalchemy import update

    from app.models.user import User

    admin = _register(app_client, "admin@kentro.example")["tokens"]["access_token"]
    _register(app_client, "first@atlas.example")
    dormant = _register(app_client, "dormant@atlas.example")
    old_access = dormant["tokens"]["access_token"]
    rotated = app_client.post(
        "/auth/refresh", json={"refresh_token": dormant["tokens"]["refresh_token"]}
    )
    assert rotated.status_code == 200, rotated.text
    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=eng, future=True)() as s:
        s.execute(update(User).where(User.email == "dormant@atlas.example").values(is_active=False))
        s.commit()
    assert _user_row("dormant@atlas.example").credentials_changed_at is None, "setup"

    _archive(app_client, admin, "first@atlas.example")

    assert _user_row("dormant@atlas.example").credentials_changed_at is not None
    assert _rotation_state("dormant@atlas.example") == (None, None, None)
    r = app_client.patch(
        f"/admin/users/{dormant['user']['id']}", headers=_auth(admin), json={"is_active": True}
    )
    assert r.status_code == 200, r.text
    r = _me(app_client, old_access)
    assert r.status_code == 401, r.text
    assert r.json()["error"]["reason"] == _CUTOFF_REASON


@pytest.mark.unit
def test_a_failed_archive_commit_records_no_ended_sessions(
    app_client: TestClient, minted_in_the_past, monkeypatch
) -> None:
    """A success record belongs below the commit that makes it true. The helper
    logged "sessions.ended" before its caller committed, so a rolled-back
    archive left a log saying sessions had ended."""
    from sqlalchemy.orm import Session as OrmSession

    import app.routes.admin as admin_routes
    import app.security.sessions as sessions

    admin = _register(app_client, "admin@kentro.example")["tokens"]["access_token"]
    _register(app_client, "first@atlas.example")
    cid = _user_row("first@atlas.example").client_id
    events: list[str] = []
    from types import SimpleNamespace

    # `raising=False`: the helper has no logger now. If one is added back and
    # logs before the caller's commit, it lands in `events` and this goes red.
    monkeypatch.setattr(
        sessions,
        "log",
        SimpleNamespace(info=lambda event, **kw: events.append(event)),
        raising=False,
    )
    monkeypatch.setattr(
        admin_routes.logger, "info", lambda msg, *a, **kw: events.append(msg.split()[0])
    )

    def refuse(self) -> None:
        raise RuntimeError("commit refused (test)")

    monkeypatch.setattr(OrmSession, "commit", refuse)
    with pytest.raises(RuntimeError, match="commit refused"):
        app_client.delete(f"/admin/clients/{cid}", headers=_auth(admin))

    assert "sessions.ended" not in events
    assert "admin.client_archived" not in events
