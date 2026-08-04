"""Client release-notification email tests (Sprint 7 T2, D-030).

On deliverable release, when ``SHIELD_EMAIL_DELIVERY_ENABLED`` is on, every
active client-role user of the deliverable's tenant is notified by email
(service, title/version, a link to ``{web_base_url}/documents``). The
notification is best-effort: with delivery off the release proceeds exactly as
v3.3.0 (loud skip log), and an SMTP failure logs loudly WITHOUT rolling back the
release (the release is the source of truth — D-030).

These drive ``release_deliverable`` directly against a migrated SQLite DB so the
recipient-selection matrix (active client vs admin vs inactive vs cross-tenant)
is exercised without the route/auth layer.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.deliverable_release import release_deliverable
from app.email.sender import send_release_notification
from app.models._common import utcnow
from app.models.client import Client
from app.models.client_domain import ClientDomain
from app.models.deliverable import Deliverable
from app.models.service import Service, ServiceKind
from app.models.user import User, UserRole


@pytest.fixture()
def db_factory(tmp_path) -> Iterator[sessionmaker]:
    db_path = tmp_path / "shield-release-notify.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _tenant(db: Session, legal_name: str, domain: str) -> Client:
    tenant = Client(legal_name=legal_name)
    db.add(tenant)
    db.flush()
    db.add(ClientDomain(client_id=tenant.id, domain=domain))
    db.flush()
    return tenant


def _user(db: Session, email: str, role: UserRole, client_id, *, is_active: bool = True) -> User:
    user = User(
        email=email,
        password_hash="x" * 64,
        role=role,
        display_name=email.split("@")[0],
        client_id=client_id,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user


def _finalized_deliverable(db: Session, tenant_id, admin_id) -> Deliverable:
    svc = Service(
        kind=ServiceKind.NIST_CSF,
        title="Atlas - CSF",
        client_id=tenant_id,
        opened_by=admin_id,
    )
    db.add(svc)
    db.flush()
    deliv = Deliverable(
        service_id=svc.id,
        title="NIST CSF 2.0 Assessment",
        version=3,
        finalized_at=utcnow(),
    )
    db.add(deliv)
    db.commit()
    db.refresh(deliv)
    return deliv


def _delivery_on(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.deliverable_release.get_settings",
        lambda: Settings(shield_email_delivery_enabled=True, smtp_host="mailhog"),
    )


def _delivery_off(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.deliverable_release.get_settings",
        lambda: Settings(shield_email_delivery_enabled=False),
    )


@pytest.mark.unit
def test_release_notifies_active_client_users_of_tenant_only(db_factory, monkeypatch) -> None:
    """Delivery on -> exactly the tenant's ACTIVE client-role users are emailed;
    admins, inactive client users, and other tenants' client users are never
    included."""
    captured: list[dict] = []
    monkeypatch.setattr(
        "app.deliverable_release.send_release_notification",
        lambda **kw: captured.append(kw),
    )
    _delivery_on(monkeypatch)

    with db_factory() as db:
        tenant = _tenant(db, "Atlas Corporation", "atlas.example")
        other = _tenant(db, "Beta Tenant", "beta.example")
        admin = _user(db, "admin@kentro.example", UserRole.ADMIN, None)
        c1 = _user(db, "client1@atlas.example", UserRole.CLIENT, tenant.id)
        c2 = _user(db, "client2@atlas.example", UserRole.CLIENT, tenant.id)
        _user(db, "inactive@atlas.example", UserRole.CLIENT, tenant.id, is_active=False)
        _user(db, "client@beta.example", UserRole.CLIENT, other.id)
        db.commit()

        expected_recipients = {c1.email, c2.email}
        deliv = _finalized_deliverable(db, tenant.id, admin.id)

        release_deliverable(
            db,
            deliverable_id=deliv.id,
            tenant_client_id=tenant.id,
            user=admin,
            kinds=(ServiceKind.NIST_CSF,),
            action="csf.deliverable.released",
        )

        recipients = {kw["to"] for kw in captured}
        assert recipients == expected_recipients
        # Content fields the client needs to find the deliverable.
        kw = captured[0]
        assert kw["service_label"] == "NIST CSF 2.0"
        assert kw["title"] == "NIST CSF 2.0 Assessment"
        assert kw["version"] == 3


@pytest.mark.unit
def test_notification_body_carries_service_title_version_and_documents_link(monkeypatch) -> None:
    """The composed email names the service, title, version and links to
    /documents on the configured web base URL."""
    sent: list[dict] = []
    monkeypatch.setattr(
        "app.email.sender.send_email",
        lambda **kw: sent.append(kw),
    )
    monkeypatch.setattr(
        "app.email.sender.get_settings",
        lambda: Settings(
            shield_email_delivery_enabled=True,
            smtp_host="mailhog",
            web_base_url="https://shield.example",
        ),
    )

    send_release_notification(
        to="client@atlas.example",
        service_label="NIST CSF 2.0",
        title="NIST CSF 2.0 Assessment",
        version=3,
    )

    assert len(sent) == 1
    msg = sent[0]
    assert msg["to"] == "client@atlas.example"
    assert "NIST CSF 2.0" in msg["subject"] or "NIST CSF 2.0" in msg["body"]
    assert "NIST CSF 2.0 Assessment" in msg["body"]
    assert "v3" in msg["body"] or "version 3" in msg["body"].lower()
    assert "https://shield.example/documents" in msg["body"]


@pytest.mark.unit
def test_delivery_off_sends_nothing_but_still_releases(db_factory, monkeypatch) -> None:
    """Delivery off -> no notification attempted, release still applied exactly
    as v3.3.0 (released_at set)."""
    captured: list[dict] = []
    monkeypatch.setattr(
        "app.deliverable_release.send_release_notification",
        lambda **kw: captured.append(kw),
    )
    _delivery_off(monkeypatch)

    with db_factory() as db:
        tenant = _tenant(db, "Atlas Corporation", "atlas.example")
        admin = _user(db, "admin@kentro.example", UserRole.ADMIN, None)
        _user(db, "client1@atlas.example", UserRole.CLIENT, tenant.id)
        db.commit()

        deliv = _finalized_deliverable(db, tenant.id, admin.id)
        result = release_deliverable(
            db,
            deliverable_id=deliv.id,
            tenant_client_id=tenant.id,
            user=admin,
            kinds=(ServiceKind.NIST_CSF,),
            action="csf.deliverable.released",
        )

        assert captured == []
        assert result.released_at is not None


@pytest.mark.unit
def test_smtp_failure_does_not_roll_back_release(db_factory, monkeypatch) -> None:
    """An SMTP failure during notification logs loudly but does NOT roll back the
    release (the release is the source of truth — D-030)."""

    def _boom(**kw):
        raise RuntimeError("smtp down")

    monkeypatch.setattr("app.deliverable_release.send_release_notification", _boom)
    _delivery_on(monkeypatch)

    with db_factory() as db:
        tenant = _tenant(db, "Atlas Corporation", "atlas.example")
        admin = _user(db, "admin@kentro.example", UserRole.ADMIN, None)
        _user(db, "client1@atlas.example", UserRole.CLIENT, tenant.id)
        db.commit()

        deliv = _finalized_deliverable(db, tenant.id, admin.id)
        deliv_id = deliv.id

        # Release must NOT raise even though every notification send fails.
        result = release_deliverable(
            db,
            deliverable_id=deliv_id,
            tenant_client_id=tenant.id,
            user=admin,
            kinds=(ServiceKind.NIST_CSF,),
            action="csf.deliverable.released",
        )
        assert result.released_at is not None

    # Re-query on a fresh session: the release persisted despite the send failure.
    with db_factory() as db2:
        persisted = db2.execute(select(Deliverable).where(Deliverable.id == deliv_id)).scalar_one()
        assert persisted.released_at is not None
