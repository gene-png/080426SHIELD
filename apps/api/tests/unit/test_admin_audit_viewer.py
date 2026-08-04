"""Admin audit-viewer read routes (Sprint 5 T7).

`audit_entries` and `llm_calls` are append-only stores with 42 write sites and
(until T7) zero read surface. These routes are the read side: cursor-paginated,
filterable, admin-only, and strictly read-only (no mutation affordance).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def ctx(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    db_path = tmp_path / "shield-audit-viewer.db"
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

    # Work Order B1: seed a pending client + example.com domain so the second
    # registrant (the client-role user) auto-joins a tenant.
    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain

    _seed = TestSession()
    _tenant = _Client(legal_name="(pending intake)")
    _seed.add(_tenant)
    _seed.flush()
    _seed.add(_ClientDomain(client_id=_tenant.id, domain="example.com"))
    _seed.commit()
    _seed.close()

    with TestClient(app) as c:
        yield c, TestSession


def _register(
    client: TestClient, email: str, password: str = "correct horse battery staple!"
) -> dict:
    r = client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": email.split("@")[0]},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _admin(ctx) -> tuple[TestClient, str, str]:
    """Register the admin (first registrant, D-004) and return (client, bearer, user_id)."""
    c, _ = ctx
    body = _register(c, "admin@example.com")
    assert body["user"]["role"] == "admin"
    return c, body["tokens"]["access_token"], body["user"]["id"]


def _auth(bearer: str) -> dict:
    return {"Authorization": f"Bearer {bearer}"}


# --------------------------------------------------------------------------- #
# audit-entries
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_audit_entries_admin_only_client_gets_403(ctx) -> None:
    c, admin_bearer, _ = _admin(ctx)
    client_bearer = _register(c, "client@example.com")["tokens"]["access_token"]

    r = c.get("/admin/audit-entries", headers=_auth(client_bearer))
    assert r.status_code == 403, r.text

    r2 = c.get("/admin/llm-calls", headers=_auth(client_bearer))
    assert r2.status_code == 403, r2.text

    # Admin can read.
    assert c.get("/admin/audit-entries", headers=_auth(admin_bearer)).status_code == 200
    assert c.get("/admin/llm-calls", headers=_auth(admin_bearer)).status_code == 200


@pytest.mark.unit
def test_audit_entries_newest_first_and_cursor_pagination(ctx) -> None:
    c, admin_bearer, _ = _admin(ctx)
    # Each client.created write appends one audit row; make several.
    names = [f"Org {i}" for i in range(5)]
    for n in names:
        r = c.post("/admin/clients", headers=_auth(admin_bearer), json={"legal_name": n})
        assert r.status_code == 201, r.text

    # Page 1 (limit 2), newest first.
    r = c.get("/admin/audit-entries?limit=2", headers=_auth(admin_bearer))
    assert r.status_code == 200, r.text
    p1 = r.json()
    assert len(p1["entries"]) == 2
    assert p1["next_cursor"], "expected a cursor for more pages"
    # Newest first: at descending.
    ats = [e["at"] for e in p1["entries"]]
    assert ats == sorted(ats, reverse=True)
    assert all(e["action"] == "client.created" for e in p1["entries"])

    # Walk all pages via the cursor; collect ids, assert no dupes and full coverage.
    seen: list[str] = [e["id"] for e in p1["entries"]]
    cursor = p1["next_cursor"]
    guard = 0
    while cursor:
        guard += 1
        assert guard < 20
        rr = c.get(f"/admin/audit-entries?limit=2&cursor={cursor}", headers=_auth(admin_bearer))
        assert rr.status_code == 200, rr.text
        page = rr.json()
        seen.extend(e["id"] for e in page["entries"])
        cursor = page["next_cursor"]
    # 5 client.created + the audit rows from registration/seed - at least our 5.
    assert len(seen) == len(set(seen)), "cursor pages must not overlap"
    created_ids = {e["id"] for e in p1["entries"]}
    assert created_ids.issubset(set(seen))


@pytest.mark.unit
def test_audit_entries_filter_action_prefix_and_target_type(ctx) -> None:
    c, admin_bearer, _ = _admin(ctx)
    cr = c.post("/admin/clients", headers=_auth(admin_bearer), json={"legal_name": "Filterable"})
    assert cr.status_code == 201
    cid = cr.json()["id"]
    # A different action + target_type: approve a domain (client.domain.added).
    dr = c.post(
        f"/admin/clients/{cid}/domains",
        headers=_auth(admin_bearer),
        json={"domain": "filterable.example"},
    )
    assert dr.status_code == 201, dr.text

    # action prefix "client.domain" matches only the domain write.
    r = c.get("/admin/audit-entries?action=client.domain", headers=_auth(admin_bearer))
    assert r.status_code == 200, r.text
    actions = {e["action"] for e in r.json()["entries"]}
    assert actions == {"client.domain.added"}

    # target_type filter.
    r2 = c.get("/admin/audit-entries?target_type=client", headers=_auth(admin_bearer))
    assert r2.status_code == 200
    assert all(e["target_type"] == "client" for e in r2.json()["entries"])
    assert len(r2.json()["entries"]) >= 2


@pytest.mark.unit
def test_audit_entries_filter_actor_correlation_and_date_range(ctx) -> None:
    c, admin_bearer, admin_id = _admin(ctx)
    r = c.post("/admin/clients", headers=_auth(admin_bearer), json={"legal_name": "Actorful"})
    assert r.status_code == 201

    # actor filter: admin performed the create.
    r = c.get(f"/admin/audit-entries?actor_user_id={admin_id}", headers=_auth(admin_bearer))
    assert r.status_code == 200, r.text
    entries = r.json()["entries"]
    assert entries and all(e["actor_user_id"] == admin_id for e in entries)

    # correlation_id filter: pick one from an existing row, expect the row back.
    corr = entries[0]["correlation_id"]
    assert corr
    r2 = c.get(f"/admin/audit-entries?correlation_id={corr}", headers=_auth(admin_bearer))
    assert r2.status_code == 200
    assert all(e["correlation_id"] == corr for e in r2.json()["entries"])

    # Date range: a far-future window returns nothing; an all-time window returns
    # rows. Pass via params= so httpx URL-encodes the "+00:00" offset (a raw "+"
    # in the query string decodes to a space and 422s the datetime parse).
    future = (datetime.now(UTC) + timedelta(days=3650)).isoformat()
    r3 = c.get("/admin/audit-entries", params={"at_from": future}, headers=_auth(admin_bearer))
    assert r3.status_code == 200, r3.text
    assert r3.json()["entries"] == []

    past = (datetime.now(UTC) - timedelta(days=3650)).isoformat()
    r4 = c.get("/admin/audit-entries", params={"at_from": past}, headers=_auth(admin_bearer))
    assert r4.status_code == 200
    assert len(r4.json()["entries"]) >= 1


# --------------------------------------------------------------------------- #
# llm-calls
# --------------------------------------------------------------------------- #


def _seed_llm_call(
    TestSession: sessionmaker,
    *,
    requested_by: uuid.UUID,
    purpose: str = "csf_score",
    provider: str = "fixture",
    status: str = "completed",
    correlation_id: str | None = None,
    client_id: uuid.UUID | None = None,
) -> uuid.UUID:
    from app.models.llm_call import LLMCall, LLMCallMode, LLMCallStatus

    db = TestSession()
    try:
        row = LLMCall(
            purpose=purpose,
            prompt_version="v1",
            provider=provider,
            model="fixture-model",
            mode=LLMCallMode.FIXTURE,
            status=LLMCallStatus(status),
            input_tokens=10,
            output_tokens=20,
            duration_ms=5,
            requested_by=requested_by,
            client_id=client_id,
            redacted_counts={"email": 1},
            error_message=None,
            correlation_id=correlation_id,
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


@pytest.mark.unit
def test_llm_calls_exposes_only_audit_safe_fields(ctx) -> None:
    c, admin_bearer, admin_id = _admin(ctx)
    _, TestSession = ctx
    _seed_llm_call(TestSession, requested_by=uuid.UUID(admin_id))

    r = c.get("/admin/llm-calls", headers=_auth(admin_bearer))
    assert r.status_code == 200, r.text
    calls = r.json()["calls"]
    assert len(calls) == 1
    row = calls[0]
    # Audit-safe fields present.
    for key in (
        "id",
        "purpose",
        "provider",
        "model",
        "mode",
        "status",
        "input_tokens",
        "output_tokens",
        "duration_ms",
        "redacted_counts",
        "error_message",
        "requested_by",
        "requested_at",
    ):
        assert key in row, f"missing safe field {key}"
    # No secret ever surfaces.
    assert "api_key" not in row
    assert "anthropic_api_key" not in row
    # Redacted counts are counts only, never payload content.
    assert row["redacted_counts"] == {"email": 1}


@pytest.mark.unit
def test_llm_calls_filters_and_cursor(ctx) -> None:
    c, admin_bearer, admin_id = _admin(ctx)
    _, TestSession = ctx
    admin_uuid = uuid.UUID(admin_id)
    _seed_llm_call(TestSession, requested_by=admin_uuid, purpose="csf_score", provider="fixture")
    _seed_llm_call(TestSession, requested_by=admin_uuid, purpose="zt_score", provider="fixture")
    _seed_llm_call(
        TestSession,
        requested_by=admin_uuid,
        purpose="mitre_map",
        provider="anthropic",
        status="failed",
    )

    # purpose filter.
    r = c.get("/admin/llm-calls?purpose=csf_score", headers=_auth(admin_bearer))
    assert r.status_code == 200, r.text
    assert {row["purpose"] for row in r.json()["calls"]} == {"csf_score"}

    # provider filter.
    r2 = c.get("/admin/llm-calls?provider=anthropic", headers=_auth(admin_bearer))
    assert {row["provider"] for row in r2.json()["calls"]} == {"anthropic"}

    # status filter.
    r3 = c.get("/admin/llm-calls?status=failed", headers=_auth(admin_bearer))
    assert {row["status"] for row in r3.json()["calls"]} == {"failed"}

    # cursor pagination over 3 rows, limit 2.
    p1 = c.get("/admin/llm-calls?limit=2", headers=_auth(admin_bearer)).json()
    assert len(p1["calls"]) == 2
    assert p1["next_cursor"]
    p2 = c.get(
        f"/admin/llm-calls?limit=2&cursor={p1['next_cursor']}", headers=_auth(admin_bearer)
    ).json()
    assert len(p2["calls"]) == 1
    ids = {row["id"] for row in p1["calls"]} | {row["id"] for row in p2["calls"]}
    assert len(ids) == 3


@pytest.mark.unit
def test_llm_calls_filter_client_id(ctx) -> None:
    """The client_id filter returns only that tenant's llm_calls rows."""
    c, admin_bearer, admin_id = _admin(ctx)
    _, TestSession = ctx
    admin_uuid = uuid.UUID(admin_id)
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    _seed_llm_call(TestSession, requested_by=admin_uuid, client_id=tenant_a)
    _seed_llm_call(TestSession, requested_by=admin_uuid, client_id=tenant_b)

    r = c.get(f"/admin/llm-calls?client_id={tenant_a}", headers=_auth(admin_bearer))
    assert r.status_code == 200, r.text
    calls = r.json()["calls"]
    assert len(calls) == 1
    assert calls[0]["client_id"] == str(tenant_a)


@pytest.mark.unit
def test_llm_calls_date_range(ctx) -> None:
    """A far-future at_from returns nothing; an all-time window returns the rows."""
    c, admin_bearer, admin_id = _admin(ctx)
    _, TestSession = ctx
    _seed_llm_call(TestSession, requested_by=uuid.UUID(admin_id))

    future = (datetime.now(UTC) + timedelta(days=3650)).isoformat()
    r = c.get("/admin/llm-calls", params={"at_from": future}, headers=_auth(admin_bearer))
    assert r.status_code == 200, r.text
    assert r.json()["calls"] == []

    past = (datetime.now(UTC) - timedelta(days=3650)).isoformat()
    r2 = c.get("/admin/llm-calls", params={"at_from": past}, headers=_auth(admin_bearer))
    assert r2.status_code == 200
    assert len(r2.json()["calls"]) >= 1


@pytest.mark.unit
def test_correlation_id_links_activity_and_ai_tabs(ctx) -> None:
    """A shared correlation_id joins an audit row to its llm_calls row."""
    c, admin_bearer, admin_id = _admin(ctx)
    _, TestSession = ctx
    corr = f"corr-{uuid.uuid4()}"
    _seed_llm_call(TestSession, requested_by=uuid.UUID(admin_id), correlation_id=corr)

    # Write an audit row carrying the same correlation id.
    from app.audit import audit

    db = TestSession()
    try:
        # correlation_id_var is request-scoped; write directly with a fixed value.
        from app.models.audit_entry import AuditEntry

        db.add(
            AuditEntry(
                action="ai.run",
                target_type="service",
                target_id=None,
                actor_user_id=uuid.UUID(admin_id),
                details={"note": "linked"},
                correlation_id=corr,
            )
        )
        db.commit()
    finally:
        db.close()
    _ = audit  # imported to assert the blessed surface exists

    ar = c.get(f"/admin/audit-entries?correlation_id={corr}", headers=_auth(admin_bearer)).json()
    lr = c.get(f"/admin/llm-calls?correlation_id={corr}", headers=_auth(admin_bearer)).json()
    assert len(ar["entries"]) == 1
    assert len(lr["calls"]) == 1
    assert ar["entries"][0]["correlation_id"] == lr["calls"][0]["correlation_id"] == corr
