"""End-to-end /intake route tests against an ephemeral SQLite + FastAPI TestClient."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.audit_entry import AuditEntry
from app.models.client import Client


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    db_path = tmp_path / "shield-intake-rt.db"
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
        yield c, TestSession


def _register_and_bearer(client: TestClient) -> str:
    # The first registrant becomes the platform admin (client_id IS NULL).
    # Under Work Order B1 a client can only self-register against a pre-approved
    # org domain, so the admin first creates the org + approves "example.com",
    # then the client-role user registers and auto-joins it.
    admin = client.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "Admin",
        },
    )
    assert admin.status_code == 201, admin.text
    admin_bearer = admin.json()["tokens"]["access_token"]
    created = client.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {admin_bearer}"},
        json={"legal_name": "(pending intake)"},
    )
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    dom = client.post(
        f"/admin/clients/{cid}/domains",
        headers={"Authorization": f"Bearer {admin_bearer}"},
        json={"domain": "example.com"},
    )
    assert dom.status_code == 201, dom.text
    r = client.post(
        "/auth/register",
        json={
            "email": "poc@example.com",
            "password": "correct horse battery staple!",
            "display_name": "POC",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["tokens"]["access_token"]


@pytest.mark.unit
def test_get_intake_creates_singleton_client(app_client) -> None:
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = client.get("/intake", headers={"Authorization": f"Bearer {bearer}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["client"]["legal_name"] == "(pending intake)"
    assert body["service_requests"] == []
    assert body["intake_completed_at"] is None


@pytest.mark.unit
def test_patch_intake_updates_client_and_profile(app_client) -> None:
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = client.patch(
        "/intake",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {
                "legal_name": "Atlas Defense Solutions",
                "industry": "Defense",
                "size_band": "501-1000",
            },
            "title": "CISO",
            "phone": "+1-555-0123",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["client"]["legal_name"] == "Atlas Defense Solutions"
    assert body["client"]["industry"] == "Defense"
    assert body["client"]["size_band"] == "501-1000"


@pytest.mark.unit
def test_submit_intake_writes_service_requests_and_audit(app_client) -> None:
    client, TestSession = app_client
    bearer = _register_and_bearer(client)

    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {
                "legal_name": "Atlas Defense Solutions",
                "industry": "Defense",
                "address_line1": "123 Pentagon Way",
                "city": "Arlington",
                "state": "VA",
                "country": "US",
            },
            "service_requests": [
                {
                    "service_type": "nist_csf",
                    "notes": "Annual assessment refresh.",
                    "csf_target_tier": 3,
                    "csf_profile": "MOD",
                },
                {"service_type": "zero_trust_cisa", "zt_target_stage": 3},
            ],
            "title": "CISO",
            "phone": "+1-555-0123",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intake_completed_at"] is not None
    assert len(body["service_requests"]) == 2
    types = sorted(req["service_type"] for req in body["service_requests"])
    assert types == ["nist_csf", "zero_trust_cisa"]

    # Audit row written.
    with TestSession() as db:
        rows = (
            db.execute(select(AuditEntry).where(AuditEntry.action == "client.intake_submitted"))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].details["services"] == ["nist_csf", "zero_trust_cisa"]

        c_row = db.execute(select(Client)).scalar_one()
        assert c_row.intake_completed_at is not None
        assert c_row.legal_name == "Atlas Defense Solutions"


@pytest.mark.unit
def test_submit_rejects_empty_service_requests(app_client) -> None:
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {"legal_name": "Atlas Defense Solutions"},
            "service_requests": [],
        },
    )
    assert r.status_code == 422


@pytest.mark.unit
def test_submit_rejects_pending_placeholder_legal_name(app_client) -> None:
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {"legal_name": "(pending intake)"},
            "service_requests": [{"service_type": "consultation"}],
        },
    )
    assert r.status_code == 422


@pytest.mark.unit
def test_submit_dedupes_duplicate_service_requests(app_client) -> None:
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {"legal_name": "Atlas Defense Solutions"},
            "service_requests": [
                {"service_type": "nist_csf", "csf_target_tier": 3, "csf_profile": "MOD"},
                {"service_type": "nist_csf", "csf_target_tier": 3, "csf_profile": "MOD"},
                {"service_type": "consultation"},
            ],
        },
    )
    assert r.status_code == 200
    assert len(r.json()["service_requests"]) == 2


@pytest.mark.unit
def test_submit_requires_csf_and_zt_targets(app_client) -> None:
    client, _ = app_client
    bearer = _register_and_bearer(client)

    # NIST CSF without a target tier + profile is rejected.
    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {"legal_name": "Atlas Defense Solutions"},
            "service_requests": [{"service_type": "nist_csf"}],
        },
    )
    assert r.status_code == 422

    # Zero Trust without a target stage is rejected.
    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {"legal_name": "Atlas Defense Solutions"},
            "service_requests": [{"service_type": "zero_trust_dod"}],
        },
    )
    assert r.status_code == 422

    # With targets supplied, the same services are accepted and persisted.
    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {"legal_name": "Atlas Defense Solutions"},
            "service_requests": [
                {"service_type": "nist_csf", "csf_target_tier": 4, "csf_profile": "HIGH"},
                {"service_type": "zero_trust_dod", "zt_target_stage": 2},
            ],
        },
    )
    assert r.status_code == 200, r.text
    by_type = {s["service_type"]: s for s in r.json()["service_requests"]}
    assert by_type["nist_csf"]["csf_target_tier"] == 4
    assert by_type["nist_csf"]["csf_profile"] == "HIGH"
    assert by_type["zero_trust_dod"]["zt_target_stage"] == 2


@pytest.mark.unit
def test_submit_refuses_a_zt_target_the_framework_does_not_have(app_client) -> None:
    """DoD ZTRA ends at Stage 3. Intake must refuse 4 rather than store it.

    The front half of #125. `ServiceRequestInput.zt_target_stage` is bound
    `ge=2, le=4` for BOTH frameworks -- a pydantic field constraint cannot see
    `service_type` -- and `_validate_targets` checked PRESENCE only. So a DoD
    engagement stored a 4, `analyze_gaps` clamped it to 3, and the finalize
    audit row reported `target_stage: 3, target_stage_source: "client"`: a stage
    the framework does not have, attributed to a client who could not have
    meant it.

    `resolve_target_stage` now reports such a stored value as
    `client_out_of_range` instead of as the client's choice, which is the
    honest answer to a value already on disk. This is the other end: refusing
    it at the door means there is nothing to be honest about later.

    The positive controls are the point. A guard that refused every target
    would satisfy the 422 assertion alone, so this also pins that DoD 2 and 3
    still submit, and that CISA 4 -- a stage CISA really has -- is untouched.
    """
    client, _ = app_client
    bearer = _register_and_bearer(client)

    def submit(service_type: str, stage: int):
        return client.post(
            "/intake/submit",
            headers={"Authorization": f"Bearer {bearer}"},
            json={
                "client": {"legal_name": "Atlas Defense Solutions"},
                "service_requests": [{"service_type": service_type, "zt_target_stage": stage}],
            },
        )

    # DoD has no Stage 4. Refused, and the reason names the real range rather
    # than dumping a validation error (the D-016 typed-detail pattern).
    r = submit("zero_trust_dod", 4)
    assert r.status_code == 422, r.text
    # The app wraps a typed detail in its own envelope (`app/exceptions.py`),
    # so `reason`/`message` sit under "error", not under FastAPI's "detail".
    err = r.json()["error"]
    assert err["reason"] == "zt_target_stage_out_of_range", err
    assert "stages 1-3" in err["message"], err["message"]
    assert "zero_trust_dod" in err["message"], err["message"]

    # POSITIVE CONTROLS -- every stage each framework really has still submits.
    for stage in (2, 3):
        assert submit("zero_trust_dod", stage).status_code == 200, stage
    for stage in (2, 3, 4):
        assert submit("zero_trust_cisa", stage).status_code == 200, stage


@pytest.mark.unit
def test_intake_requires_authentication(app_client) -> None:
    client, _ = app_client
    r = client.get("/intake")
    assert r.status_code == 401
    r = client.patch("/intake", json={})
    assert r.status_code == 401
    r = client.post(
        "/intake/submit",
        json={
            "client": {"legal_name": "X"},
            "service_requests": [{"service_type": "consultation"}],
        },
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# The review step must be able to show what it is about to submit.
#
# UX finding 3 / E2E F-7: "Review & submit" rendered Organization, Services and
# Systems but NOT the contact details, because /intake never returned them. A
# client could not check the POC name, title, phone or timezone before
# committing the intake.
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_intake_state_returns_the_contact_for_review(app_client) -> None:
    client, _ = app_client
    bearer = _register_and_bearer(client)
    client.patch(
        "/intake",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "display_name": "Dana Reyes",
            "title": "Director of Information Security",
            "phone": "+1 319 555 0142",
            "timezone": "America/Chicago",
        },
    )

    r = client.get("/intake", headers={"Authorization": f"Bearer {bearer}"})
    assert r.status_code == 200, r.text
    contact = r.json()["contact"]
    assert contact["display_name"] == "Dana Reyes"
    assert contact["title"] == "Director of Information Security"
    assert contact["phone"] == "+1 319 555 0142"
    assert contact["timezone"] == "America/Chicago"
    # The email is the account's own and is shown read-only on the wizard.
    assert contact["email"]
