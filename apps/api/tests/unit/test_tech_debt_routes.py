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
    # #639: approval refuses undecided rows, so decide the one row first.
    _decide(c, bearer, [i["id"] for i in r1.json()["items"]])

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
    svc_id, item_id = _create_list_with_item(c, bearer, provider)
    _decide(c, bearer, [item_id])  # #639: approval refuses undecided rows
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


def _latest_list(c: TestClient, bearer: str, svc_id: str) -> dict:
    r = c.get(
        f"/tech-debt/services/{svc_id}/capability-lists/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _decide(c: TestClient, bearer: str, item_ids: list[str], disposition: str = "keep") -> None:
    for item_id in item_ids:
        r = c.patch(
            f"/tech-debt/capability-items/{item_id}",
            headers={"Authorization": f"Bearer {bearer}"},
            json={"disposition": disposition},
        )
        assert r.status_code == 200, r.text


@pytest.mark.unit
@pytest.mark.parametrize(("undecided", "noun"), [(1, "1 row is"), (2, "2 rows are")])
def test_approve_refuses_while_rows_are_undecided_naming_the_count(
    app_client, undecided: int, noun: str
) -> None:
    """#639: approving with step-2 rows still undecided (disposition None, the
    model's own "undecided") built a deliverable from an unfinished review.
    The refusal is typed (D-016), names the count, points back to step 2, and
    changes nothing."""
    c, _, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    _decide(c, bearer, item_ids[undecided:])
    list_id = _latest_list(c, bearer, svc_id)["id"]

    r = c.post(
        f"/tech-debt/capability-lists/{list_id}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )

    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["reason"] == "capability_list_undecided_rows", error
    assert noun in error["message"], error["message"]
    assert "Review and correct the extracted list" in error["message"], error["message"]
    after = _latest_list(c, bearer, svc_id)
    assert after["status"] == "draft" and after["approved_at"] is None, after


@pytest.mark.unit
def test_a_row_undecided_between_the_check_and_the_write_is_still_refused(
    app_client, monkeypatch
) -> None:
    """The guard is the UPDATE's WHERE, not the read before it. Every row is
    decided when the route counts, and a concurrent edit sets one back to
    undecided before the write -- forced deterministically: the route calls
    `build_approved_membership` between the two, and a one-shot hook there
    commits the edit through a separate session. Without the condition in the
    WHERE, the list is approved over an undecided row."""
    import app.routes.tech_debt as td
    from app.models.capability import CapabilityItem

    c, sessions, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    _decide(c, bearer, item_ids)
    list_id = _latest_list(c, bearer, svc_id)["id"]

    real = td.build_approved_membership
    fired: list[bool] = []

    def racing_edit(db, capability_list_id):
        if not fired:
            fired.append(True)
            other = sessions()
            try:
                item = other.get(CapabilityItem, _uuid.UUID(item_ids[0]))
                item.disposition = None
                other.commit()
            finally:
                other.close()
        return real(db, capability_list_id)

    monkeypatch.setattr(td, "build_approved_membership", racing_edit)
    r = c.post(
        f"/tech-debt/capability-lists/{list_id}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )

    assert fired, "the hook never ran -- the race was not exercised"
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "capability_list_undecided_rows"
    assert "1 row is" in r.json()["error"]["message"]
    assert _latest_list(c, bearer, svc_id)["status"] == "draft"


@pytest.mark.unit
def test_a_lost_approve_race_with_nothing_undecided_says_the_list_changed(
    app_client, monkeypatch
) -> None:
    """#657 round 1, F2. The UPDATE can miss while the list is still a draft
    with nothing undecided by the time the route recounts: a concurrent edit
    made a row undecided before the write and decided it again after. The
    route used to fall through to the RELEASED refusal and tell the consultant
    the list "has been released and is locked", which it had not.

    The edit before the write is real: a separate session commits it. The UNDO
    cannot be: SQLite holds the route's write lock from its UPDATE until commit,
    so a second writer gets "database is locked" (measured). Under Postgres READ
    COMMITTED the undo commits and the recount reads zero, so the recount is
    modelled as returning that zero -- the state this test is about, which
    SQLite cannot produce. The pre-check before it is the real count."""
    import app.routes.tech_debt as td
    from app.models.capability import CapabilityItem

    c, sessions, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    _decide(c, bearer, item_ids)
    list_id = _latest_list(c, bearer, svc_id)["id"]

    real_build, real_count = td.build_approved_membership, td.undecided_row_count
    events: list[str] = []

    def edit_before_write(db, capability_list_id):
        if "edit" not in events:
            events.append("edit")
            other = sessions()
            try:
                other.get(CapabilityItem, _uuid.UUID(item_ids[0])).disposition = None
                other.commit()
            finally:
                other.close()
        return real_build(db, capability_list_id)

    def undone_by_the_recount(db, list_id_):
        if "edit" in events and "undo" not in events:
            events.append("undo")
            return 0  # what a READ COMMITTED recount reads after the racer's undo
        return real_count(db, list_id_)

    monkeypatch.setattr(td, "build_approved_membership", edit_before_write)
    monkeypatch.setattr(td, "undecided_row_count", undone_by_the_recount)
    r = c.post(
        f"/tech-debt/capability-lists/{list_id}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )

    assert events == ["edit", "undo"], f"the race was not exercised as designed: {events}"
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["reason"] == "capability_list_changed_during_approval", error
    assert "released" not in error["message"].lower(), error["message"]
    assert "approve again" in error["message"].lower(), error["message"]
    assert _latest_list(c, bearer, svc_id)["status"] == "draft"


@pytest.mark.unit
def test_finalize_refuses_an_approved_list_a_row_was_made_undecided_on(app_client) -> None:
    """#657 round 1, F1. An APPROVED list stays editable until release, and
    the step-2 table can send a row back to undecided through the real PATCH.
    Finalize checked only the status, so the deliverable could still be built
    from an unfinished review. It re-checks, with the approve refusal's reason
    and a remedy that names what the consultant can do at step 4: approve is
    already done and its button disabled, so the message must not send them
    there."""
    c, _, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    _decide(c, bearer, item_ids)
    _approve_list(c, bearer, svc_id)
    r = c.patch(f"/tech-debt/capability-items/{item_ids[0]}", headers=h, json={"disposition": None})
    assert r.status_code == 200, r.text

    r = c.post(f"/tech-debt/services/{svc_id}/deliverables/finalize", headers=h)

    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["reason"] == "capability_list_undecided_rows", error
    assert "1 row is" in error["message"], error["message"]
    assert "Review and correct the extracted list" in error["message"], error["message"]
    assert "generate the deliverable again" in error["message"], error["message"]
    assert "approve again" not in error["message"], error["message"]


def _finalize(c: TestClient, h: dict, svc_id: str):
    return c.post(f"/tech-debt/services/{svc_id}/deliverables/finalize", headers=h)


@pytest.mark.unit
def test_release_refuses_while_a_row_is_undecided(app_client) -> None:
    """#657 round 2 (a). Release freezes the list, and a frozen list with an
    undecided row could never be repaired: every re-finalize would be refused
    with a remedy -- edit step 2 -- that a released list refuses. So release
    refuses first, naming step 2, which is still editable."""
    c, _, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    _decide(c, bearer, item_ids)
    _approve_list(c, bearer, svc_id)
    fin = _finalize(c, h, svc_id)
    assert fin.status_code == 201, fin.text
    r = c.patch(f"/tech-debt/capability-items/{item_ids[0]}", headers=h, json={"disposition": None})
    assert r.status_code == 200, r.text

    r = c.post(f"/tech-debt/deliverables/{fin.json()['id']}/release", headers=h)

    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["reason"] == "capability_list_undecided_rows", error
    assert "Review and correct the extracted list" in error["message"], error["message"]
    assert _latest_list(c, bearer, svc_id)["status"] == "approved", "the list was frozen anyway"
    # NO HALF-RELEASE (#657 round 4): the deliverable is not released either --
    # not on the admin's record, and not in the list the client can see.
    latest = c.get(f"/tech-debt/services/{svc_id}/deliverables/latest", headers=h)
    assert latest.status_code == 200, latest.text
    assert latest.json()["released_at"] is None, "the deliverable was released without its list"
    client = _register(c, "client@example.com")
    listed = c.get(
        f"/clients/{client['user']['client_id']}/deliverables",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == [], "the client can see a deliverable the release refused"


@pytest.mark.unit
def test_a_legacy_released_list_with_an_undecided_row_still_refinalizes(app_client) -> None:
    """#657 round 2 (b). Finalize accepts RELEASED so re-finalizing never locks a
    service. The undecided check is for APPROVED lists only.

    LEGACY STATE, BUILT BY DIRECT SQL: release now refuses undecided rows, so no
    route can produce a RELEASED list holding one. Lists released before #639
    can, and they must keep re-finalizing exactly as they do on main."""
    from app.models.capability import CapabilityItem

    c, sessions, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    _decide(c, bearer, item_ids)
    _approve_list(c, bearer, svc_id)
    fin = _finalize(c, h, svc_id)
    assert fin.status_code == 201, fin.text
    rel = c.post(f"/tech-debt/deliverables/{fin.json()['id']}/release", headers=h)
    assert rel.status_code == 200, rel.text
    assert _latest_list(c, bearer, svc_id)["status"] == "released"
    with sessions() as db:
        db.get(CapabilityItem, _uuid.UUID(item_ids[0])).disposition = None
        db.commit()

    again = _finalize(c, h, svc_id)

    assert again.status_code == 201, again.text


@pytest.mark.unit
def test_a_row_made_undecided_as_the_rows_load_is_refused_not_rendered(app_client) -> None:
    """#657 round 2, the check-to-render window. A count and the select that
    feeds the render were two statements; a PATCH committed between them sent
    an undecided row into a deliverable the count had passed. Forced through the
    route: a one-shot session hook commits the edit, from a separate session,
    immediately before the CapabilityItem rows are loaded -- after any separate
    count. The rows the render uses must be the rows the refusal judged."""
    from sqlalchemy import event

    from app.models.capability import CapabilityItem

    c, sessions, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    _decide(c, bearer, item_ids)
    _approve_list(c, bearer, svc_id)

    fired: list[bool] = []

    def before_rows_load(state) -> None:
        if fired or not state.is_select:
            return
        described = state.statement.column_descriptions
        if not (len(described) == 1 and described[0].get("entity") is CapabilityItem):
            return
        fired.append(True)
        other = sessions()
        try:
            other.get(CapabilityItem, _uuid.UUID(item_ids[0])).disposition = None
            other.commit()
        finally:
            other.close()

    event.listen(sessions, "do_orm_execute", before_rows_load)
    try:
        r = _finalize(c, h, svc_id)
    finally:
        event.remove(sessions, "do_orm_execute", before_rows_load)

    assert fired, "the hook never ran -- the window was not exercised"
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "capability_list_undecided_rows", r.text


@pytest.mark.unit
def test_a_normal_first_release_still_releases(app_client) -> None:
    """The passing half of round 3: every row decided, the guarded flip matches."""
    c, _, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    _decide(c, bearer, item_ids)
    _approve_list(c, bearer, svc_id)
    fin = _finalize(c, h, svc_id)
    assert fin.status_code == 201, fin.text

    r = c.post(f"/tech-debt/deliverables/{fin.json()['id']}/release", headers=h)

    assert r.status_code == 200, r.text
    assert _latest_list(c, bearer, svc_id)["status"] == "released"


@pytest.mark.unit
def test_a_repair_rerelease_over_an_undecided_row_is_refused(app_client) -> None:
    """#657 round 3, finding 1. Re-releasing an already-released deliverable is
    the REPAIR path: it flips a parent that never got flipped. Round 2's
    pre-check returned early for a released deliverable, so the repair path
    flipped an APPROVED list holding an undecided row unchecked.

    LEGACY STATE, BUILT BY DIRECT SQL: a released deliverable whose list is
    still APPROVED is what migration 0041's backfill left behind; no route
    produces it now."""
    from app.models.capability import CapabilityList as _CL
    from app.models.capability import CapabilityListStatus

    c, sessions, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    _decide(c, bearer, item_ids)
    _approve_list(c, bearer, svc_id)
    fin = _finalize(c, h, svc_id)
    assert fin.status_code == 201, fin.text
    rel = c.post(f"/tech-debt/deliverables/{fin.json()['id']}/release", headers=h)
    assert rel.status_code == 200, rel.text
    list_id = _latest_list(c, bearer, svc_id)["id"]
    with sessions() as db:
        db.get(_CL, _uuid.UUID(list_id)).status = CapabilityListStatus.APPROVED
        db.commit()
    r = c.patch(f"/tech-debt/capability-items/{item_ids[0]}", headers=h, json={"disposition": None})
    assert r.status_code == 200, r.text

    again = c.post(f"/tech-debt/deliverables/{fin.json()['id']}/release", headers=h)

    assert again.status_code == 409, again.text
    assert again.json()["error"]["reason"] == "capability_list_undecided_rows", again.text
    assert _latest_list(c, bearer, svc_id)["status"] == "approved", "the repair froze it anyway"


@pytest.mark.unit
def test_a_row_made_undecided_as_the_list_is_released_is_refused(app_client) -> None:
    """#657 round 3, finding 2: a check that runs before the flip cannot see a
    PATCH that commits between them. Forced through the route: a one-shot hook
    commits the edit from a separate session immediately before the flip --
    before the guarded UPDATE if the flip is one, or before the flush that
    writes an ORM-assigned status. Either way the flip itself must refuse."""
    from sqlalchemy import event

    from app.models.capability import CapabilityItem
    from app.models.capability import CapabilityList as _CL

    c, sessions, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    _decide(c, bearer, item_ids)
    _approve_list(c, bearer, svc_id)
    fin = _finalize(c, h, svc_id)
    assert fin.status_code == 201, fin.text

    fired: list[str] = []

    def undecide() -> None:
        other = sessions()
        try:
            other.get(CapabilityItem, _uuid.UUID(item_ids[0])).disposition = None
            other.commit()
        finally:
            other.close()

    def before_guarded_update(state) -> None:
        mapper = state.bind_mapper
        if not fired and state.is_update and mapper is not None and mapper.class_ is _CL:
            fired.append("update")
            undecide()

    def before_orm_flush(session, _ctx, _instances) -> None:
        if not fired and any(isinstance(o, _CL) for o in session.dirty):
            fired.append("flush")
            undecide()

    event.listen(sessions, "do_orm_execute", before_guarded_update)
    event.listen(sessions, "before_flush", before_orm_flush)
    try:
        r = c.post(f"/tech-debt/deliverables/{fin.json()['id']}/release", headers=h)
    finally:
        event.remove(sessions, "do_orm_execute", before_guarded_update)
        event.remove(sessions, "before_flush", before_orm_flush)

    assert fired, "the hook never ran -- the window was not exercised"
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "capability_list_undecided_rows", r.text
    assert _latest_list(c, bearer, svc_id)["status"] == "approved"


@pytest.mark.unit
def test_a_release_miss_whose_recount_finds_nothing_undecided_says_the_list_changed(
    app_client, monkeypatch
) -> None:
    """#657 round 4, approve's F2 for release. The guarded flip misses because a
    row is undecided at that instant, and by the recount it has been re-decided.
    "0 rows are still undecided" would be false; the refusal says the list moved.

    The edit before the flip is real. The re-decide cannot be: the route holds
    SQLite's write lock from its UPDATE, so the recount is modelled as returning
    the 0 a Postgres READ COMMITTED read would see after the racer's commit."""
    from sqlalchemy import event

    import app.routes.tech_debt as td
    from app.models.capability import CapabilityItem
    from app.models.capability import CapabilityList as _CL

    c, sessions, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    _decide(c, bearer, item_ids)
    _approve_list(c, bearer, svc_id)
    fin = _finalize(c, h, svc_id)
    assert fin.status_code == 201, fin.text

    fired: list[str] = []

    def before_guarded_update(state) -> None:
        mapper = state.bind_mapper
        if not fired and state.is_update and mapper is not None and mapper.class_ is _CL:
            fired.append("edit")
            other = sessions()
            try:
                other.get(CapabilityItem, _uuid.UUID(item_ids[0])).disposition = None
                other.commit()
            finally:
                other.close()

    monkeypatch.setattr(td, "undecided_row_count", lambda db, list_id: 0)
    event.listen(sessions, "do_orm_execute", before_guarded_update)
    try:
        r = c.post(f"/tech-debt/deliverables/{fin.json()['id']}/release", headers=h)
    finally:
        event.remove(sessions, "do_orm_execute", before_guarded_update)

    assert fired == ["edit"], "the flip was not raced as designed"
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["reason"] == "capability_list_changed_during_release", error
    assert "0 rows" not in error["message"], error["message"]


@pytest.mark.unit
def test_approve_succeeds_once_every_row_is_decided(app_client) -> None:
    """The passing half: zero undecided rows approve."""
    c, _, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    _decide(c, bearer, item_ids)
    list_id = _latest_list(c, bearer, svc_id)["id"]

    r = c.post(
        f"/tech-debt/capability-lists/{list_id}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"


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
    r = c.post(
        f"/tech-debt/capability-lists/{list_id}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    # A refused approval here used to be ignored, and every test after it ran
    # against a draft list it believed approved.
    assert r.status_code == 200, r.text
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
    """#298, the same-file twin.

    The status assertion is original. The two below it are not: this refusal
    was the last bare-string 409 in `routes/tech_debt.py` after
    `_refuse_approval` was typed, and a status code alone pins nothing about
    the payload -- which is exactly how one function came to carry two shapes
    for long enough to need an issue.

    Found by sweeping the SHAPE, `grep -n 'detail="' routes/tech_debt.py`
    filtered to 409s, rather than from a list anyone handed over. Every bare
    string that survives that grep is now a 404.
    """
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id, _ = _seed_three_item_list(c, bearer, provider)
    r = c.post(
        f"/tech-debt/services/{svc_id}/deliverables/finalize",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 409
    error = r.json()["error"]
    assert error["reason"] == "capability_list_not_approved", r.text
    assert error["message"] == "Capability list must be approved before finalizing the deliverable."


@pytest.mark.unit
def test_latest_returns_newest_finalized_version(app_client) -> None:
    c, _, provider = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    _decide(c, bearer, item_ids)  # #639: approval refuses undecided rows
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
    svc_id, item_ids = _seed_three_item_list(c, bearer, provider)
    _decide(c, bearer, item_ids)  # #639: approval refuses undecided rows
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


# --------------------------------------------------------------------------- #
# Extraction reconciliation reaches the client (UX finding 4 / E2E F-5).
#
# The workspace reported "12 capabilities · $891,796" for a 21-row, $1,634,236
# upload with no hint that nine rows were excluded. The counts are computed in
# code and persisted; this pins that they actually reach the response — the
# serializer builds it field-by-field, so a new model column silently reads as
# null unless it is added there too (the same shape as the released_at bug).
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_extract_response_discloses_excluded_rows(app_client) -> None:
    c, _TestSession, provider = app_client
    bearer = _register(c, "recon-admin@example.com")["tokens"]["access_token"]

    def fake(payload):
        # Four rows in, two security capabilities out — rows 1 and 3 are the
        # kind of business tooling the prompt deliberately skips.
        return LLMResponse(
            json.dumps(
                {
                    "items": [
                        {
                            "name": "Wiz",
                            "vendor": "Wiz Inc",
                            "category": "CNAPP",
                            "function": "Cloud posture",
                            "annual_cost_usd": 350000,
                            "license_count": None,
                            "notes": None,
                            "confidence_pct": 92,
                            "source_row_index": 0,
                        },
                        {
                            "name": "Splunk",
                            "vendor": "Splunk",
                            "category": "SIEM",
                            "function": "Log analytics",
                            "annual_cost_usd": 480000,
                            "license_count": None,
                            "notes": None,
                            "confidence_pct": 88,
                            "source_row_index": 2,
                        },
                    ]
                }
            )
        )

    provider.register("extract.capabilities", fake)

    sr = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"kind": "tech_debt", "title": "Reconciliation"},
    )
    svc_id = sr.json()["id"]
    csv = (
        b"Tool,Vendor,Annual Cost\n"
        b"Wiz,Wiz Inc,350000\n"
        b"SAP S4HANA,SAP,252000\n"
        b"Splunk,Splunk,480000\n"
        b"Workday HCM,Workday,81700\n"
    )
    artifact_id = _upload_csv(c, bearer, "inventory.csv", csv)

    r = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_id},
    )
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["source_rows_total"] == 4
    assert len(body["items"]) == 2
    excluded = body["excluded_rows"]
    assert [e["index"] for e in excluded] == [1, 3]
    assert "SAP S4HANA" in excluded[0]["summary"]
    assert "Workday HCM" in excluded[1]["summary"]

    # It must SURVIVE a reload — the workspace refetches on every load, and a
    # disclosure that vanishes on refresh is no disclosure.
    again = c.get(
        f"/tech-debt/services/{svc_id}/capability-lists/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert again.status_code == 200, again.text
    assert again.json()["source_rows_total"] == 4
    assert len(again.json()["excluded_rows"]) == 2


# --------------------------------------------------------------------------- #
# Bundle decomposition (UX finding 5 / E2E F-6).
#
# "Microsoft 365 E5" extracted as one $294,120 line. It contains Defender for
# Endpoint, Defender for Office 365 and Entra ID P2, and the same client
# separately licenses CrowdStrike, Proofpoint and Okta — so three of the five
# redundancies planted in the 2026-08-04 test inventory were invisible.
#
# A consultant names the components; the model is never asked what is inside a
# bundle. The parent keeps the whole cost, so decomposing can never inflate the
# portfolio total.
# --------------------------------------------------------------------------- #


def _list_with_one_item(c, bearer: str, provider, name: str, cost: float) -> tuple[str, str]:
    """Extract a one-row list and return (service_id, item_id)."""

    def fake(payload):
        return LLMResponse(
            json.dumps(
                {
                    "items": [
                        {
                            "name": name,
                            "vendor": "Microsoft",
                            "category": "Productivity and Security Suite",
                            "function": "Bundled licence",
                            "annual_cost_usd": cost,
                            "license_count": 430,
                            "notes": None,
                            "confidence_pct": 70,
                            "source_row_index": 0,
                        }
                    ]
                }
            )
        )

    provider.register("extract.capabilities", fake)
    sr = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"kind": "tech_debt", "title": "Bundle"},
    )
    svc_id = sr.json()["id"]
    artifact_id = _upload_csv(c, bearer, "inv.csv", b"Tool,Cost\nMicrosoft 365 E5,294120\n")
    r = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_id},
    )
    assert r.status_code == 201, r.text
    return svc_id, r.json()["items"][0]["id"]


@pytest.mark.unit
def test_bundle_expands_into_named_components(app_client) -> None:
    c, _TestSession, provider = app_client
    bearer = _register(c, "bundle-admin@example.com")["tokens"]["access_token"]
    svc_id, item_id = _list_with_one_item(c, bearer, provider, "Microsoft 365 E5", 294120)

    r = c.post(
        f"/tech-debt/capability-items/{item_id}/components",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "components": [
                {"name": "Microsoft Defender for Endpoint", "category": "EDR"},
                {"name": "Microsoft Entra ID P2", "category": "IAM"},
            ]
        },
    )
    assert r.status_code == 201, r.text
    items = r.json()["items"]

    parent = next(i for i in items if i["id"] == item_id)
    children = [i for i in items if i.get("parent_item_id") == item_id]
    assert len(children) == 2
    assert {ch["name"] for ch in children} == {
        "Microsoft Defender for Endpoint",
        "Microsoft Entra ID P2",
    }

    # The parent keeps the whole licence value; components carry none, so the
    # portfolio total cannot be inflated by decomposing a bundle.
    assert float(parent["annual_cost_usd"]) == 294120.0
    assert all(ch["annual_cost_usd"] is None for ch in children)
    # Components inherit the parent's source reference.
    assert all(ch["source_artifact_id"] == parent["source_artifact_id"] for ch in children)
    # They are human-named, not an AI guess.
    assert all(ch["confidence_pct"] is None for ch in children)


@pytest.mark.unit
def test_components_are_rejected_on_a_component(app_client) -> None:
    """One level only. Nesting bundles inside bundles has no real-world
    counterpart here and would make the cost story ambiguous."""
    c, _TestSession, provider = app_client
    bearer = _register(c, "bundle-admin2@example.com")["tokens"]["access_token"]
    _svc, item_id = _list_with_one_item(c, bearer, provider, "Microsoft 365 E5", 294120)

    first = c.post(
        f"/tech-debt/capability-items/{item_id}/components",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"components": [{"name": "Microsoft Intune", "category": "MDM"}]},
    )
    child_id = next(i["id"] for i in first.json()["items"] if i.get("parent_item_id") == item_id)

    r = c.post(
        f"/tech-debt/capability-items/{child_id}/components",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"components": [{"name": "Nested", "category": "X"}]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "component_cannot_be_split"


@pytest.mark.unit
def test_components_require_at_least_one_name(app_client) -> None:
    c, _TestSession, provider = app_client
    bearer = _register(c, "bundle-admin3@example.com")["tokens"]["access_token"]
    _svc, item_id = _list_with_one_item(c, bearer, provider, "Microsoft 365 E5", 294120)

    r = c.post(
        f"/tech-debt/capability-items/{item_id}/components",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"components": []},
    )
    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- #
# Review queue for excluded rows (UX finding 4, second half).
#
# Disclosure alone tells a consultant that nine rows were dropped; it does not
# let them do anything about it. A row wrongly skipped by the extractor has to
# be recoverable, and a row correctly skipped should be dismissible so the
# warning stops nagging.
# --------------------------------------------------------------------------- #


def _list_with_exclusions(c, bearer: str, provider) -> tuple[str, str]:
    """Extract 4 rows -> 2 capabilities. Returns (service_id, list_id)."""

    def fake(payload):
        return LLMResponse(
            json.dumps(
                {
                    "items": [
                        {
                            "name": "Wiz",
                            "vendor": None,
                            "category": "CNAPP",
                            "function": None,
                            "annual_cost_usd": 350000,
                            "license_count": None,
                            "notes": None,
                            "confidence_pct": 90,
                            "source_row_index": 0,
                        },
                        {
                            "name": "Splunk",
                            "vendor": None,
                            "category": "SIEM",
                            "function": None,
                            "annual_cost_usd": 480000,
                            "license_count": None,
                            "notes": None,
                            "confidence_pct": 90,
                            "source_row_index": 2,
                        },
                    ]
                }
            )
        )

    provider.register("extract.capabilities", fake)
    sr = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"kind": "tech_debt", "title": "Queue"},
    )
    svc_id = sr.json()["id"]
    csv = (
        b"Tool,Vendor,Annual Cost\n"
        b"Wiz,Wiz Inc,350000\n"
        b"Claroty xDome,Claroty,133000\n"
        b"Splunk,Splunk,480000\n"
        b"Workday HCM,Workday,81700\n"
    )
    artifact_id = _upload_csv(c, bearer, "inv.csv", csv)
    r = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_id},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert [e["index"] for e in body["excluded_rows"]] == [1, 3]
    return svc_id, body["id"]


@pytest.mark.unit
def test_excluded_row_can_be_included_as_a_capability(app_client) -> None:
    """Claroty xDome is OT security — the extractor skipped it, the consultant
    knows better and pulls it back in."""
    c, _TestSession, provider = app_client
    bearer = _register(c, "queue-admin@example.com")["tokens"]["access_token"]
    _svc, list_id = _list_with_exclusions(c, bearer, provider)

    r = c.post(
        f"/tech-debt/capability-lists/{list_id}/excluded-rows/1/include",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"name": "Claroty xDome", "category": "OT Security", "annual_cost_usd": 133000},
    )
    assert r.status_code == 201, r.text
    body = r.json()

    added = next(i for i in body["items"] if i["name"] == "Claroty xDome")
    assert added["category"] == "OT Security"
    assert float(added["annual_cost_usd"]) == 133000.0
    # Human-added, so no AI confidence badge.
    assert added["confidence_pct"] is None
    # It is no longer excluded, and the remaining exclusion is untouched.
    assert [e["index"] for e in body["excluded_rows"]] == [3]


@pytest.mark.unit
def test_excluded_row_can_be_confirmed_as_correctly_excluded(app_client) -> None:
    c, _TestSession, provider = app_client
    bearer = _register(c, "queue-admin2@example.com")["tokens"]["access_token"]
    _svc, list_id = _list_with_exclusions(c, bearer, provider)

    r = c.post(
        f"/tech-debt/capability-lists/{list_id}/excluded-rows/3/confirm",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    rows = {e["index"]: e for e in r.json()["excluded_rows"]}
    # Still listed — the reconciliation must stay honest — but acknowledged.
    assert rows[3]["confirmed"] is True
    assert rows[1]["confirmed"] is False


@pytest.mark.unit
def test_unknown_excluded_row_index_is_rejected(app_client) -> None:
    c, _TestSession, provider = app_client
    bearer = _register(c, "queue-admin3@example.com")["tokens"]["access_token"]
    _svc, list_id = _list_with_exclusions(c, bearer, provider)

    r = c.post(
        f"/tech-debt/capability-lists/{list_id}/excluded-rows/99/confirm",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 404, r.text


@pytest.mark.unit
def test_a_released_refusal_carries_a_typed_reason_like_its_twin(app_client) -> None:
    """#298. Two refusals, one function, two shapes.

    `_refuse_approval` returned `{"reason": "capability_list_discarded", ...}`
    for DISCARDED and a BARE STRING for RELEASED, so the released case reached
    the client with no `reason` key while its sibling three lines up had one.
    Core principle 2: user-facing API errors are typed.

    No PYTHON test pinned either shape, which is why the inconsistency survived
    long enough to be filed rather than noticed. An earlier draft of this
    docstring said "zero tests", which was a claim about the repo and false:
    `apps/web/src/components/admin/techdebt-workspace-surfaces-server-errors.test.ts`
    asserts this exact sentence through `proxyMessage`. Saying zero is what
    tells the next reader nothing downstream can break.

    THE MESSAGE IS ASSERTED VERBATIM, not just the reason. The conversion's
    whole safety argument is that `message` is unchanged: `proxyMessage` in
    `lib/tech_debt/client.ts` reads `error.message` and never `reason`, and the
    vitest above matches this sentence with a regex. A future edit that retypes
    the reason and rewords the copy would break exactly the consumer a typed
    reason exists to serve, and this line is what makes that loud.

    NO E2E SPEC MATCHES IT. An earlier draft claimed two. Measured:
    `rg "released and is" e2e/` returns nothing, and the control
    `rg "is locked" e2e/` returns three hits, so the search works and the
    absence is real rather than a failed search. Inventing consumers is the
    expensive direction to be wrong in -- a later reader loosens the copy
    believing e2e will catch it.
    """
    c, _, provider = app_client
    admin = _register(c, "released-refusal@example.com")
    bearer = admin["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id, item_id = _create_list_with_item(c, bearer, provider)
    _decide(c, bearer, [item_id])  # #639: approval refuses undecided rows
    list_id = c.get(f"/tech-debt/services/{svc_id}/capability-lists/latest", headers=h).json()["id"]

    assert c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=h).status_code == 200

    # SETTING THE COLUMN IS WHAT THE ONLY REAL WRITER DOES, so this fixture
    # matches production rather than inventing a state.
    #
    # This comment used to open "Drive it to RELEASED through the real
    # transition rather than by writing the column" -- directly above the
    # column write, disclaiming the thing on the next line. It was also wrong
    # about the code: NO ROUTE TRANSITIONS A CAPABILITY LIST TO RELEASED.
    # `grep -rnE "(status|\.status)\s*=\s*CapabilityListStatus\.RELEASED"
    # apps/api` returns exactly one non-test site, `scripts/seed_demo.py:501`,
    # which CONSTRUCTS the row released. Everything else in `app/` only
    # compares against it.
    #
    # So the honest version of the question `CLAUDE.md` asks of a setup -- can
    # the system under test produce this state? -- is yes, by direct
    # construction, and that is the writer this mirrors. What would make it
    # reachable by transition is W4 flipping the parent on release, which
    # `finalize_deliverable` already anticipates in its own comment; until
    # then the refusal fires for seeded and demo data, and the guard is a
    # ratchet against that change landing without one.
    from app.models.capability import CapabilityList, CapabilityListStatus

    _c, sessionmaker_, _p = app_client
    with sessionmaker_() as db:
        cl = db.get(CapabilityList, _uuid.UUID(list_id))
        assert cl is not None and cl.status == CapabilityListStatus.APPROVED
        cl.status = CapabilityListStatus.RELEASED
        db.add(cl)
        db.commit()

    r = c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=h)
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["reason"] == "capability_list_released", r.text
    assert error["message"] == "This capability list has been released and is locked."
