"""Smoke for the Phase 2 stage 1 schema additions."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Client, ServiceRequest, ServiceType, User, UserRole
from app.models._common import utcnow


@pytest.fixture()
def migrated_sqlite(tmp_path) -> str:
    db_path = tmp_path / "shield-intake.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    return url


@pytest.mark.unit
def test_migration_adds_intake_completed_at(migrated_sqlite: str) -> None:
    engine = create_engine(migrated_sqlite)
    with engine.connect() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info('client')")}
    assert "intake_completed_at" in cols


@pytest.mark.unit
def test_migration_creates_service_requests_table(migrated_sqlite: str) -> None:
    engine = create_engine(migrated_sqlite)
    with engine.connect() as conn:
        names = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='service_requests'"
            )
        }
    assert "service_requests" in names


@pytest.mark.unit
def test_service_request_roundtrip(migrated_sqlite: str) -> None:
    engine = create_engine(migrated_sqlite)
    with Session(engine) as db:
        client = Client(legal_name="Atlas Defense")
        db.add(client)
        db.flush()
        user = User(
            email="poc@example.com",
            password_hash="x" * 64,
            role=UserRole.ADMIN,
            display_name="POC",
        )
        db.add(user)
        db.flush()
        sr = ServiceRequest(
            service_type=ServiceType.NIST_CSF,
            client_id=client.id,
            requested_by=user.id,
            notes="Initial intake — interested in NIST CSF.",
        )
        db.add(sr)
        db.commit()

        loaded = db.get(ServiceRequest, sr.id)
        assert loaded is not None
        assert loaded.service_type == ServiceType.NIST_CSF
        assert loaded.requested_by == user.id
        assert loaded.notes.startswith("Initial intake")
        assert loaded.declined_at is None
        assert loaded.fulfilled_service_id is None


@pytest.mark.unit
def test_consultation_service_type_supported(migrated_sqlite: str) -> None:
    """The 'I'm not sure' path on the intake wizard maps to CONSULTATION."""
    engine = create_engine(migrated_sqlite)
    with Session(engine) as db:
        client = Client(legal_name="Curious Co")
        db.add(client)
        db.flush()
        user = User(
            email="curious@example.com",
            password_hash="x" * 64,
            role=UserRole.CLIENT,
            display_name="Curious",
            client_id=client.id,
        )
        db.add(user)
        db.flush()
        sr = ServiceRequest(
            service_type=ServiceType.CONSULTATION,
            client_id=client.id,
            requested_by=user.id,
        )
        db.add(sr)
        db.commit()
        assert sr.service_type == ServiceType.CONSULTATION


@pytest.mark.unit
def test_client_intake_completed_at_writes(migrated_sqlite: str) -> None:
    engine = create_engine(migrated_sqlite)
    with Session(engine) as db:
        c = Client(legal_name="Atlas Defense", intake_completed_at=utcnow())
        db.add(c)
        db.commit()
        assert c.intake_completed_at is not None
