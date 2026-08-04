"""Tech Debt ingest tests: service creation + capability extraction.

The extraction call uses a FixtureProvider-backed LLMClient with canned
JSON responses, so the test is deterministic + offline.
"""

from __future__ import annotations

import io
import json
import os
import uuid as _uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.audit_entry import AuditEntry
from app.models.capability import CapabilityList
from app.models.llm_call import LLMCall
from app.models.service import Service
from app.storage.local import LocalFilesystemStorage


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker, FixtureProvider]]:
    db_path = tmp_path / "shield-td.db"
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
    provider = FixtureProvider()
    client = LLMClient(provider)

    from app.db.session import get_db
    from app.main import create_app
    from app.routes.artifacts import _storage_dep
    from app.routes.tech_debt import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_storage_dep] = lambda: storage
    app.dependency_overrides[_llm_dep] = lambda: client

    # Multi-tenant (post-0013): admin/reviewer callers must name an active
    # tenant via X-Client-Id. Seed one tenant and bake the header into the
    # test client so single-tenant-style tests resolve to it; client-role
    # callers are pinned to their own client and ignore this header.
    from app.models.client import Client as _Client

    _seed = TestSession()
    _tenant = _Client(legal_name="Test Tenant")
    _seed.add(_tenant)
    _seed.flush()
    from app.models.client_domain import ClientDomain as _ClientDomain

    _seed.add(_ClientDomain(client_id=_tenant.id, domain="example.com"))
    _seed.commit()
    _cid = str(_tenant.id)
    _seed.close()

    with TestClient(app, headers={"X-Client-Id": _cid}) as c:
        yield c, TestSession, provider


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


def _upload_csv(c: TestClient, bearer: str, name: str, csv_bytes: bytes) -> str:
    r = c.post(
        "/artifacts",
        headers={"Authorization": f"Bearer {bearer}"},
        files={"file": (name, io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.unit
def test_admin_can_open_service(app_client) -> None:
    c, _, _ = app_client
    admin = _register(c, "admin@example.com")
    r = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {admin['tokens']['access_token']}"},
        json={"kind": "tech_debt", "title": "Atlas — Tech Debt"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "tech_debt"
    assert body["status"] == "in_progress"
    assert body["title"] == "Atlas — Tech Debt"


@pytest.mark.unit
def test_client_role_cannot_open_service(app_client) -> None:
    c, _, _ = app_client
    _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    c.headers["X-Client-Id"] = client["user"]["client_id"]
    r = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
        json={"kind": "tech_debt", "title": "x"},
    )
    assert r.status_code == 403


@pytest.mark.unit
def test_extract_runs_redacted_call_and_writes_capability_list(app_client) -> None:
    c, TestSession, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]

    captured: dict = {}

    def fake(payload: dict) -> LLMResponse:
        captured["payload"] = payload
        return LLMResponse(
            content=json.dumps(
                {
                    "items": [
                        {
                            "name": "Wiz",
                            "vendor": "Wiz, Inc.",
                            "category": "CNAPP",
                            "function": "Cloud posture",
                            "annual_cost_usd": 350000,
                            "license_count": 200,
                            "notes": "Strong cloud-native coverage.",
                            "confidence_pct": 92,
                            "source_row_index": 0,
                        },
                        {
                            "name": "Splunk Enterprise",
                            "vendor": "Splunk",
                            "category": "SIEM",
                            "function": "Log analytics",
                            "annual_cost_usd": 480000,
                            "license_count": None,
                            "notes": None,
                            "confidence_pct": 88,
                            "source_row_index": 1,
                        },
                    ]
                }
            )
        )

    provider.register("extract.capabilities", fake)

    # Open the service.
    sr = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"kind": "tech_debt", "title": "Atlas — Tech Debt"},
    )
    svc_id = sr.json()["id"]

    # Upload a small inventory CSV with PII so we can prove redaction.
    csv = (
        b"Tool,Vendor,Owner,Owner Email,Annual Cost\n"
        b"Wiz,Wiz Inc,Alice Pemberton,alice@atlas-defense.gov,$350000\n"
        b"Splunk Enterprise,Splunk,Bob,bob@atlas-defense.gov,$480000\n"
    )
    artifact_id = _upload_csv(c, bearer, "inventory.csv", csv)

    # Extract.
    r = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_id},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 1
    assert len(body["items"]) == 2
    names = sorted(i["name"] for i in body["items"])
    assert names == ["Splunk Enterprise", "Wiz"]
    item = next(i for i in body["items"] if i["name"] == "Wiz")
    assert item["annual_cost_usd"] == 350000.0
    assert item["confidence_pct"] == 92
    assert item["category"] == "CNAPP"

    # Provider received the REDACTED rows. The owner emails should be
    # placeholder strings; the raw emails must not appear anywhere.
    payload_json = json.dumps(captured["payload"])
    assert "alice@atlas-defense.gov" not in payload_json
    assert "bob@atlas-defense.gov" not in payload_json
    assert "[EMAIL]" in payload_json

    # An llm_calls row exists for this extraction.
    with TestSession() as db:
        call = db.execute(select(LLMCall)).scalar_one()
        assert call.purpose == "extract.capabilities"
        assert call.status == "completed"
        assert call.redacted_counts["email"] == 2
        cap_list = db.execute(select(CapabilityList)).scalar_one()
        assert cap_list.service_id == _uuid.UUID(svc_id)
        # T5: the extract call site (which does NOT go through run_job) still
        # attributes the egress row to the owning tenant.
        svc = db.execute(select(Service).where(Service.id == _uuid.UUID(svc_id))).scalar_one()
        assert call.client_id == svc.client_id
        assert cap_list.version == 1


@pytest.mark.unit
def test_extract_rejects_unknown_service(app_client) -> None:
    c, _, _ = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    artifact_id = _upload_csv(c, bearer, "x.csv", b"A,B\n1,2\n")
    r = c.post(
        f"/tech-debt/services/{_uuid.uuid4()}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_id},
    )
    assert r.status_code == 404


@pytest.mark.unit
def test_extract_rejects_unsupported_artifact_mime(app_client) -> None:
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    provider.register("extract.capabilities", lambda _p: LLMResponse('{"items": []}'))

    sr = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"title": "x"},
    )
    svc_id = sr.json()["id"]

    # Upload a PDF (allowed for intake artifacts but not for tech-debt
    # ingest in v1).
    r = c.post(
        "/artifacts",
        headers={"Authorization": f"Bearer {bearer}"},
        files={"file": ("inv.pdf", io.BytesIO(b"%PDF-1.7 stub"), "application/pdf")},
    )
    artifact_id = r.json()["id"]
    r = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_id},
    )
    assert r.status_code == 415


@pytest.mark.unit
def test_extract_versions_across_approved_boundary(app_client) -> None:
    """Versioning is cut across the APPROVED/RELEASED boundary, NOT on every
    POST.

    Deliberate re-contract (Sprint 8 T1): this test used to prove that two
    consecutive POSTs mint v1 -> v2. That contract is superseded by the
    draft-exists guard, which makes a second POST while a draft is open
    idempotent (see test_extract_reuses_open_draft_no_reextract). A new version
    is only minted once the prior draft has moved on, matching the CSF / ATT&CK /
    Zero Trust siblings. This rewrite proves the next-version-after-approval
    contract instead.
    """
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    provider.register(
        "extract.capabilities",
        lambda _p: LLMResponse('{"items": [{"name": "Wiz"}]}'),
    )

    sr = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"title": "x"},
    )
    svc_id = sr.json()["id"]
    artifact_id = _upload_csv(c, bearer, "x.csv", b"A\n1\n")

    r1 = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_id},
    )
    assert r1.status_code == 201, r1.text
    assert r1.json()["version"] == 1

    # Move the v1 draft on by approving it: the guard no longer applies.
    ar = c.post(
        f"/tech-debt/capability-lists/{r1.json()['id']}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert ar.status_code == 200, ar.text

    # A fresh extraction now mints v2 with a 201.
    r2 = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_id},
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["version"] == 2


@pytest.mark.unit
def test_extract_reuses_open_draft_no_reextract(app_client) -> None:
    """A second POST while a draft is open returns it idempotently (200) with
    NO re-extraction: the LLM is invoked once, one llm_calls row, one
    capability_list.extracted audit row."""
    c, TestSession, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]

    calls = {"n": 0}

    def fake(_p) -> LLMResponse:
        calls["n"] += 1
        return LLMResponse('{"items": [{"name": "Wiz"}]}')

    provider.register("extract.capabilities", fake)

    sr = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"title": "x"},
    )
    svc_id = sr.json()["id"]
    artifact_id = _upload_csv(c, bearer, "x.csv", b"A\n1\n")

    r1 = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_id},
    )
    assert r1.status_code == 201, r1.text
    first = r1.json()
    assert first["version"] == 1

    # Second POST while the draft is still open -> idempotent 200, same list.
    r2 = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_id},
    )
    assert r2.status_code == 200, r2.text
    second = r2.json()
    assert second["id"] == first["id"]
    assert second["version"] == first["version"] == 1
    assert [i["id"] for i in second["items"]] == [i["id"] for i in first["items"]]

    # No re-extraction: provider hit once, one llm_calls row, one extracted
    # audit row.
    assert calls["n"] == 1
    with TestSession() as db:
        assert db.execute(select(func.count()).select_from(LLMCall)).scalar_one() == 1
        extracted = db.execute(
            select(func.count())
            .select_from(AuditEntry)
            .where(AuditEntry.action == "capability_list.extracted")
        ).scalar_one()
        assert extracted == 1


@pytest.mark.unit
def test_extract_with_different_artifact_still_reuses_open_draft(app_client) -> None:
    """A POST with a DIFFERENT artifact_id while a draft is open still returns
    the existing draft untouched (documented contract; an explicit
    replace/re-extract affordance is out of scope)."""
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    provider.register(
        "extract.capabilities",
        lambda _p: LLMResponse('{"items": [{"name": "Wiz"}]}'),
    )

    sr = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"title": "x"},
    )
    svc_id = sr.json()["id"]
    artifact_a = _upload_csv(c, bearer, "a.csv", b"A\n1\n")
    artifact_b = _upload_csv(c, bearer, "b.csv", b"B\n2\n")

    r1 = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_a},
    )
    assert r1.status_code == 201, r1.text
    first = r1.json()

    # Different artifact, draft still open -> same draft returned, 200.
    r2 = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_b},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["id"] == first["id"]
    assert r2.json()["version"] == 1


@pytest.mark.unit
def test_latest_capability_list_admin_only(app_client) -> None:
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    c.headers["X-Client-Id"] = client["user"]["client_id"]
    a_bearer = admin["tokens"]["access_token"]
    c_bearer = client["tokens"]["access_token"]
    provider.register(
        "extract.capabilities",
        lambda _p: LLMResponse('{"items": []}'),
    )

    sr = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {a_bearer}"},
        json={"title": "x"},
    )
    svc_id = sr.json()["id"]
    artifact_id = _upload_csv(c, a_bearer, "x.csv", b"A\n1\n")
    c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {a_bearer}"},
        json={"artifact_id": artifact_id},
    )

    r = c.get(
        f"/tech-debt/services/{svc_id}/capability-lists/latest",
        headers={"Authorization": f"Bearer {a_bearer}"},
    )
    assert r.status_code == 200
    r = c.get(
        f"/tech-debt/services/{svc_id}/capability-lists/latest",
        headers={"Authorization": f"Bearer {c_bearer}"},
    )
    assert r.status_code == 403


@pytest.mark.unit
def test_extract_503_when_llm_returns_bad_json(app_client) -> None:
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    provider.register(
        "extract.capabilities",
        lambda _p: LLMResponse("totally not json"),
    )

    sr = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"title": "x"},
    )
    svc_id = sr.json()["id"]
    artifact_id = _upload_csv(c, bearer, "x.csv", b"A\n1\n")
    r = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_id},
    )
    assert r.status_code == 502


def _create_list_with_item(
    c: TestClient, bearer: str, provider: FixtureProvider
) -> tuple[str, str]:
    """Helper for stage-5 tests: open service + extract a single-item list.
    Returns (service_id, item_id)."""
    provider.register(
        "extract.capabilities",
        lambda _p: LLMResponse(
            json.dumps(
                {
                    "items": [
                        {
                            "name": "Wiz",
                            "vendor": "Wiz, Inc.",
                            "category": "CNAPP",
                            "function": "Posture",
                            "annual_cost_usd": 350000,
                            "license_count": 200,
                            "confidence_pct": 75,
                        }
                    ]
                }
            )
        ),
    )
    sr = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"title": "x"},
    )
    svc_id = sr.json()["id"]
    artifact_id = _upload_csv(c, bearer, "x.csv", b"A\n1\n")
    er = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_id},
    )
    return svc_id, er.json()["items"][0]["id"]


@pytest.mark.unit
def test_patch_capability_item_clears_confidence_and_persists_edits(app_client) -> None:
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    _, item_id = _create_list_with_item(c, bearer, provider)
    r = c.patch(
        f"/tech-debt/capability-items/{item_id}",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"vendor": "Wiz Corp.", "annual_cost_usd": 360000},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["vendor"] == "Wiz Corp."
    assert body["annual_cost_usd"] == 360000.0
    # Confidence cleared on human edit.
    assert body["confidence_pct"] is None
    # Untouched fields preserved.
    assert body["name"] == "Wiz"


@pytest.mark.unit
def test_patch_capability_item_rejects_empty_body(app_client) -> None:
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    _, item_id = _create_list_with_item(c, bearer, provider)
    r = c.patch(
        f"/tech-debt/capability-items/{item_id}",
        headers={"Authorization": f"Bearer {bearer}"},
        json={},
    )
    assert r.status_code == 422


@pytest.mark.unit
def test_patch_capability_item_404_for_unknown(app_client) -> None:
    c, _, _ = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    r = c.patch(
        f"/tech-debt/capability-items/{_uuid.uuid4()}",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"name": "x"},
    )
    assert r.status_code == 404


@pytest.mark.unit
def test_patch_capability_item_rejects_client_role(app_client) -> None:
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    c.headers["X-Client-Id"] = client["user"]["client_id"]
    _, item_id = _create_list_with_item(c, admin["tokens"]["access_token"], provider)
    r = c.patch(
        f"/tech-debt/capability-items/{item_id}",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
        json={"name": "x"},
    )
    assert r.status_code == 403


@pytest.mark.unit
def test_approve_capability_list_writes_status_and_actor(app_client) -> None:
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id, _item_id = _create_list_with_item(c, bearer, provider)
    latest = c.get(
        f"/tech-debt/services/{svc_id}/capability-lists/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    list_id = latest.json()["id"]

    r = c.post(
        f"/tech-debt/capability-lists/{list_id}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved"
    assert body["approved_at"] is not None
    assert body["approved_by"] == admin["user"]["id"]


@pytest.mark.unit
def test_approve_capability_list_404_for_unknown(app_client) -> None:
    c, _, _ = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    r = c.post(
        f"/tech-debt/capability-lists/{_uuid.uuid4()}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 404


def _seed_three_item_list(
    c: TestClient, bearer: str, provider: FixtureProvider
) -> tuple[str, list[str]]:
    """Seed a 3-item list with realistic costs for consolidation-plan tests."""
    provider.register(
        "extract.capabilities",
        lambda _p: LLMResponse(
            json.dumps(
                {
                    "items": [
                        {"name": "Wiz", "category": "CNAPP", "annual_cost_usd": 350000},
                        {"name": "Lacework", "category": "CNAPP", "annual_cost_usd": 120000},
                        {"name": "Splunk", "category": "SIEM", "annual_cost_usd": 480000},
                    ]
                }
            )
        ),
    )
    sr = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"title": "x"},
    )
    svc_id = sr.json()["id"]
    artifact_id = _upload_csv(c, bearer, "x.csv", b"A\n1\n")
    er = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_id},
    )
    return svc_id, [i["id"] for i in er.json()["items"]]


@pytest.mark.unit
def test_consolidation_plan_summary_counts_dispositions(app_client) -> None:
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)

    # Mark dispositions: keep / consolidate / cut respectively.
    for item_id, disp in zip(item_ids, ["keep", "consolidate", "cut"], strict=True):
        r = c.patch(
            f"/tech-debt/capability-items/{item_id}",
            headers={"Authorization": f"Bearer {bearer}"},
            json={"disposition": disp},
        )
        assert r.status_code == 200, r.text

    r = c.get(
        f"/tech-debt/services/{svc_id}/consolidation-plan",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["keep_count"] == 1
    assert body["consolidate_count"] == 1
    assert body["cut_count"] == 1
    assert body["undecided_count"] == 0
    # Splunk was the "cut" item ($480k savings).
    assert body["estimated_annual_savings"] == 480000.0
    assert body["savings_cost_known"] is True


@pytest.mark.unit
def test_consolidation_plan_marks_savings_unknown_when_cut_has_no_cost(app_client) -> None:
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)

    # Cut the first item then clear its cost.
    c.patch(
        f"/tech-debt/capability-items/{item_ids[0]}",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"disposition": "cut", "annual_cost_usd": None},
    )
    r = c.get(
        f"/tech-debt/services/{svc_id}/consolidation-plan",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["cut_count"] == 1
    assert body["estimated_annual_savings"] == 0.0
    assert body["savings_cost_known"] is False


@pytest.mark.unit
def test_consolidation_plan_summary_404_for_unknown_service(app_client) -> None:
    c, _, _ = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    r = c.get(
        f"/tech-debt/services/{_uuid.uuid4()}/consolidation-plan",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 404


@pytest.mark.unit
def test_consolidation_plan_summary_rejects_client_role(app_client) -> None:
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    c.headers["X-Client-Id"] = client["user"]["client_id"]
    svc_id, _ = _seed_three_item_list(c, admin["tokens"]["access_token"], provider)
    r = c.get(
        f"/tech-debt/services/{svc_id}/consolidation-plan",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    )
    assert r.status_code == 403


def _approve_list(c: TestClient, bearer: str, svc_id: str) -> str:
    latest = c.get(
        f"/tech-debt/services/{svc_id}/capability-lists/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    list_id = latest.json()["id"]
    c.post(
        f"/tech-debt/capability-lists/{list_id}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    return list_id


@pytest.mark.unit
def test_finalize_deliverable_renders_pdf_and_xlsx(app_client) -> None:
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    for item_id, disp in zip(item_ids, ["keep", "consolidate", "cut"], strict=True):
        c.patch(
            f"/tech-debt/capability-items/{item_id}",
            headers={"Authorization": f"Bearer {bearer}"},
            json={"disposition": disp},
        )
    _approve_list(c, bearer, svc_id)
    r = c.post(
        f"/tech-debt/services/{svc_id}/deliverables/finalize",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 1
    assert body["finalized_at"] is not None
    assert body["pdf_artifact_id"] is not None
    assert body["xlsx_artifact_id"] is not None
    assert body["pdf_filename"].endswith(".pdf")
    assert "Tech_Debt_Review" in body["pdf_filename"]
    assert body["xlsx_filename"].endswith(".xlsx")
    assert "estimated annual savings" in body["summary"]


@pytest.mark.unit
def test_finalize_requires_approved_list(app_client) -> None:
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id, _ = _seed_three_item_list(c, bearer, provider)
    r = c.post(
        f"/tech-debt/services/{svc_id}/deliverables/finalize",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 409


@pytest.mark.unit
def test_latest_returns_newest_finalized_version(app_client) -> None:
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id, _ = _seed_three_item_list(c, bearer, provider)
    _approve_list(c, bearer, svc_id)
    c.post(
        f"/tech-debt/services/{svc_id}/deliverables/finalize",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    r2 = c.post(
        f"/tech-debt/services/{svc_id}/deliverables/finalize",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    v2 = r2.json()["id"]
    # Latest endpoint returns the newest version (admin-only; Work Order A1).
    latest = c.get(
        f"/tech-debt/services/{svc_id}/deliverables/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert latest.json()["id"] == v2
    assert latest.json()["version"] == 2


@pytest.mark.unit
def test_client_cannot_reach_latest_deliverable(app_client) -> None:
    """Work Order A1: the latest-deliverable endpoint is admin-only."""
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id, _ = _seed_three_item_list(c, bearer, provider)
    _approve_list(c, bearer, svc_id)
    c.post(
        f"/tech-debt/services/{svc_id}/deliverables/finalize",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    client = _register(c, "client@example.com")
    c.headers["X-Client-Id"] = client["user"]["client_id"]
    bearer_client = client["tokens"]["access_token"]
    latest = c.get(
        f"/tech-debt/services/{svc_id}/deliverables/latest",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert latest.status_code == 403


@pytest.mark.unit
def test_latest_deliverable_404_when_none(app_client) -> None:
    c, _, _ = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    sr = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"title": "x"},
    )
    r = c.get(
        f"/tech-debt/services/{sr.json()['id']}/deliverables/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 404
