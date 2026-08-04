"""Draft discard contract across all four assessment services (SPRINT_9 T0, D-031).

Discard is an admin-only soft-delete state transition: a DRAFT resource flips to
DISCARDED, one audit row is written, and the version is retired from every
"latest" consumer (the service route helpers, the Risk Register synthesis, and
the client engagement cards) WITHOUT colliding on the (service_id, version)
unique constraint on the next mint.

TDD-first: these contracts are authored before the endpoints exist and must fail
loudly until T0 lands. Fixture shape copied from test_tech_debt_routes.py so the
tech-debt extract seam (LLM fixture + storage) is available in one place.
"""

from __future__ import annotations

import io
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


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker, FixtureProvider]]:
    db_path = tmp_path / "shield-discard.db"
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
    from app.routes.artifacts import _storage_dep
    from app.routes.tech_debt import _llm_dep
    from app.storage.local import LocalFilesystemStorage

    storage = LocalFilesystemStorage(tmp_path / "storage")
    provider = FixtureProvider()
    llm = LLMClient(provider)

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_storage_dep] = lambda: storage
    app.dependency_overrides[_llm_dep] = lambda: llm

    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain

    _seed = TestSession()
    _tenant = _Client(legal_name="Test Tenant")
    _seed.add(_tenant)
    _seed.flush()
    _seed.add(_ClientDomain(client_id=_tenant.id, domain="example.com"))
    _seed.commit()
    _cid = str(_tenant.id)
    _seed.close()

    with TestClient(app, headers={"X-Client-Id": _cid}) as c:
        yield c, TestSession, provider


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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


def _admin(c: TestClient) -> str:
    return _register(c, "admin@example.com")["tokens"]["access_token"]


def _hdr(bearer: str) -> dict:
    return {"Authorization": f"Bearer {bearer}"}


def _audit_count(TestSession: sessionmaker, action: str) -> int:
    with TestSession() as db:
        return db.execute(
            select(func.count()).select_from(AuditEntry).where(AuditEntry.action == action)
        ).scalar_one()


# --- tech-debt -------------------------------------------------------------


def _td_extract(c: TestClient, bearer: str, provider: FixtureProvider) -> tuple[str, str, str]:
    """Open a tech-debt service, upload a CSV, extract a v1 draft list.

    Returns (service_id, list_id, artifact_id).
    """
    provider.register(
        "extract.capabilities",
        lambda _p: LLMResponse('{"items": [{"name": "Wiz"}, {"name": "Splunk"}]}'),
    )
    sr = c.post("/tech-debt/services", headers=_hdr(bearer), json={"title": "TD"})
    svc_id = sr.json()["id"]
    up = c.post(
        "/artifacts",
        headers=_hdr(bearer),
        files={"file": ("inv.csv", io.BytesIO(b"Tool\nWiz\nSplunk\n"), "text/csv")},
    )
    artifact_id = up.json()["id"]
    er = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers=_hdr(bearer),
        json={"artifact_id": artifact_id},
    )
    assert er.status_code == 201, er.text
    return svc_id, er.json()["id"], artifact_id


def _td_approve(c: TestClient, bearer: str, list_id: str) -> None:
    r = c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=_hdr(bearer))
    assert r.status_code == 200, r.text


# --- attack ----------------------------------------------------------------


def _attack_assessment(c: TestClient, bearer: str) -> tuple[str, dict]:
    sr = c.post(
        "/attack/services",
        headers=_hdr(bearer),
        json={"kind": "attack_coverage", "title": "ATT&CK"},
    )
    svc_id = sr.json()["id"]
    ar = c.post(f"/attack/services/{svc_id}/assessments", headers=_hdr(bearer))
    assert ar.status_code == 201, ar.text
    return svc_id, ar.json()


def _attack_approve(c: TestClient, bearer: str, aid: str) -> None:
    r = c.post(f"/attack/assessments/{aid}/approve", headers=_hdr(bearer))
    assert r.status_code == 200, r.text


# --- csf -------------------------------------------------------------------


def _csf_assessment(c: TestClient, bearer: str) -> tuple[str, dict]:
    sr = c.post("/csf/services", headers=_hdr(bearer), json={"kind": "nist_csf", "title": "CSF"})
    svc_id = sr.json()["id"]
    ar = c.post(f"/csf/services/{svc_id}/assessments", headers=_hdr(bearer))
    assert ar.status_code == 201, ar.text
    return svc_id, ar.json()


# --- zt --------------------------------------------------------------------


def _zt_assessment(c: TestClient, bearer: str) -> tuple[str, dict]:
    sr = c.post(
        "/zt/services",
        headers=_hdr(bearer),
        json={"kind": "zero_trust_cisa", "title": "ZT"},
    )
    svc_id = sr.json()["id"]
    ar = c.post(f"/zt/services/{svc_id}/assessments", headers=_hdr(bearer))
    assert ar.status_code == 201, ar.text
    return svc_id, ar.json()


# ===========================================================================
# Tech-debt discard
# ===========================================================================


@pytest.mark.unit
def test_techdebt_discard_draft_200_one_audit(app_client) -> None:
    c, TestSession, provider = app_client
    bearer = _admin(c)
    _svc, list_id, _art = _td_extract(c, bearer, provider)

    r = c.post(f"/tech-debt/capability-lists/{list_id}/discard", headers=_hdr(bearer))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "discarded"
    assert _audit_count(TestSession, "capability_list.discarded") == 1


@pytest.mark.unit
def test_techdebt_rediscard_idempotent_no_second_audit(app_client) -> None:
    c, TestSession, provider = app_client
    bearer = _admin(c)
    _svc, list_id, _art = _td_extract(c, bearer, provider)

    first = c.post(f"/tech-debt/capability-lists/{list_id}/discard", headers=_hdr(bearer))
    assert first.status_code == 200, first.text
    second = c.post(f"/tech-debt/capability-lists/{list_id}/discard", headers=_hdr(bearer))
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "discarded"
    assert _audit_count(TestSession, "capability_list.discarded") == 1


@pytest.mark.unit
def test_techdebt_discard_approved_409(app_client) -> None:
    c, _TS, provider = app_client
    bearer = _admin(c)
    _svc, list_id, _art = _td_extract(c, bearer, provider)
    _td_approve(c, bearer, list_id)

    r = c.post(f"/tech-debt/capability-lists/{list_id}/discard", headers=_hdr(bearer))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "not_discardable"


@pytest.mark.unit
def test_techdebt_discard_client_role_403(app_client) -> None:
    c, _TS, provider = app_client
    admin_bearer = _admin(c)
    _svc, list_id, _art = _td_extract(c, admin_bearer, provider)
    client = _register(c, "client@example.com")
    c.headers["X-Client-Id"] = client["user"]["client_id"]
    r = c.post(
        f"/tech-debt/capability-lists/{list_id}/discard",
        headers=_hdr(client["tokens"]["access_token"]),
    )
    assert r.status_code == 403


@pytest.mark.unit
def test_techdebt_discard_unknown_404(app_client) -> None:
    c, _TS, _p = app_client
    bearer = _admin(c)
    r = c.post(f"/tech-debt/capability-lists/{_uuid.uuid4()}/discard", headers=_hdr(bearer))
    assert r.status_code == 404


@pytest.mark.unit
def test_techdebt_version_trap_discard_non_v1_then_mint(app_client) -> None:
    """v1 approved -> v2 draft -> discard v2 -> next extract mints v3, no IntegrityError."""
    c, _TS, provider = app_client
    bearer = _admin(c)
    svc_id, list_v1, artifact_id = _td_extract(c, bearer, provider)
    _td_approve(c, bearer, list_v1)

    # Mint v2 draft.
    r2 = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers=_hdr(bearer),
        json={"artifact_id": artifact_id},
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["version"] == 2
    list_v2 = r2.json()["id"]

    # Discard v2.
    d = c.post(f"/tech-debt/capability-lists/{list_v2}/discard", headers=_hdr(bearer))
    assert d.status_code == 200, d.text

    # Next extract must mint v3 (max version + 1), never collide on v2.
    r3 = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers=_hdr(bearer),
        json={"artifact_id": artifact_id},
    )
    assert r3.status_code == 201, r3.text
    assert r3.json()["version"] == 3


@pytest.mark.unit
def test_techdebt_latest_after_discard_returns_prior_approved(app_client) -> None:
    c, _TS, provider = app_client
    bearer = _admin(c)
    svc_id, list_v1, artifact_id = _td_extract(c, bearer, provider)
    _td_approve(c, bearer, list_v1)
    r2 = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers=_hdr(bearer),
        json={"artifact_id": artifact_id},
    )
    list_v2 = r2.json()["id"]
    c.post(f"/tech-debt/capability-lists/{list_v2}/discard", headers=_hdr(bearer))

    latest = c.get(f"/tech-debt/services/{svc_id}/capability-lists/latest", headers=_hdr(bearer))
    assert latest.status_code == 200, latest.text
    assert latest.json()["version"] == 1
    assert latest.json()["status"] == "approved"


@pytest.mark.unit
def test_techdebt_latest_404_when_only_draft_discarded(app_client) -> None:
    c, _TS, provider = app_client
    bearer = _admin(c)
    svc_id, list_id, _art = _td_extract(c, bearer, provider)
    c.post(f"/tech-debt/capability-lists/{list_id}/discard", headers=_hdr(bearer))
    latest = c.get(f"/tech-debt/services/{svc_id}/capability-lists/latest", headers=_hdr(bearer))
    assert latest.status_code == 404


@pytest.mark.unit
def test_techdebt_reextract_after_discard_reuses_artifact_fires_llm_once(app_client) -> None:
    """Discard, then a re-extract with the SAME artifact succeeds (artifact survives)
    and fires the LLM seam exactly once for that fresh extraction."""
    c, TestSession, provider = app_client
    bearer = _admin(c)

    calls = {"n": 0}

    def fake(_p) -> LLMResponse:
        calls["n"] += 1
        return LLMResponse('{"items": [{"name": "Wiz"}]}')

    provider.register("extract.capabilities", fake)
    sr = c.post("/tech-debt/services", headers=_hdr(bearer), json={"title": "TD"})
    svc_id = sr.json()["id"]
    up = c.post(
        "/artifacts",
        headers=_hdr(bearer),
        files={"file": ("inv.csv", io.BytesIO(b"Tool\nWiz\n"), "text/csv")},
    )
    artifact_id = up.json()["id"]
    r1 = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers=_hdr(bearer),
        json={"artifact_id": artifact_id},
    )
    assert r1.status_code == 201, r1.text
    assert calls["n"] == 1
    c.post(f"/tech-debt/capability-lists/{r1.json()['id']}/discard", headers=_hdr(bearer))

    # Same artifact still resolves; a fresh extraction runs (LLM fires again).
    r2 = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers=_hdr(bearer),
        json={"artifact_id": artifact_id},
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["version"] == 2
    assert calls["n"] == 2


@pytest.mark.unit
def test_techdebt_child_mutation_after_discard_409(app_client) -> None:
    """A stale-tab item edit into a discarded list loses loudly (D-031).

    The four-service parity for attack/csf/zt; tech-debt's editable child is a
    capability item, patched by row id through its own route.
    """
    c, _TS, provider = app_client
    bearer = _admin(c)
    svc_id, list_id, _art = _td_extract(c, bearer, provider)
    latest = c.get(f"/tech-debt/services/{svc_id}/capability-lists/latest", headers=_hdr(bearer))
    item_id = latest.json()["items"][0]["id"]

    d = c.post(f"/tech-debt/capability-lists/{list_id}/discard", headers=_hdr(bearer))
    assert d.status_code == 200, d.text

    stale = c.patch(
        f"/tech-debt/capability-items/{item_id}",
        headers=_hdr(bearer),
        json={"notes": "stale edit"},
    )
    assert stale.status_code == 409, stale.text


# ===========================================================================
# Attack discard
# ===========================================================================


@pytest.mark.unit
def test_attack_discard_draft_200_one_audit(app_client) -> None:
    c, TestSession, _p = app_client
    bearer = _admin(c)
    _svc, a = _attack_assessment(c, bearer)
    r = c.post(f"/attack/assessments/{a['id']}/discard", headers=_hdr(bearer))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "discarded"
    assert _audit_count(TestSession, "attack.assessment.discarded") == 1


@pytest.mark.unit
def test_attack_rediscard_idempotent(app_client) -> None:
    c, TestSession, _p = app_client
    bearer = _admin(c)
    _svc, a = _attack_assessment(c, bearer)
    c.post(f"/attack/assessments/{a['id']}/discard", headers=_hdr(bearer))
    r = c.post(f"/attack/assessments/{a['id']}/discard", headers=_hdr(bearer))
    assert r.status_code == 200, r.text
    assert _audit_count(TestSession, "attack.assessment.discarded") == 1


@pytest.mark.unit
def test_attack_discard_approved_409(app_client) -> None:
    c, _TS, _p = app_client
    bearer = _admin(c)
    _svc, a = _attack_assessment(c, bearer)
    _attack_approve(c, bearer, a["id"])
    r = c.post(f"/attack/assessments/{a['id']}/discard", headers=_hdr(bearer))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "not_discardable"


@pytest.mark.unit
def test_attack_discard_client_role_403(app_client) -> None:
    c, _TS, _p = app_client
    admin_bearer = _admin(c)
    _svc, a = _attack_assessment(c, admin_bearer)
    client = _register(c, "client@example.com")
    c.headers["X-Client-Id"] = client["user"]["client_id"]
    r = c.post(
        f"/attack/assessments/{a['id']}/discard",
        headers=_hdr(client["tokens"]["access_token"]),
    )
    assert r.status_code == 403


@pytest.mark.unit
def test_attack_version_trap_and_child_mutation_after_discard(app_client) -> None:
    c, _TS, _p = app_client
    bearer = _admin(c)
    svc_id, a1 = _attack_assessment(c, bearer)
    _attack_approve(c, bearer, a1["id"])

    a2r = c.post(f"/attack/services/{svc_id}/assessments", headers=_hdr(bearer))
    assert a2r.status_code == 201
    a2 = a2r.json()
    assert a2["version"] == 2
    coverage_id = a2["coverage"][0]["id"]

    d = c.post(f"/attack/assessments/{a2['id']}/discard", headers=_hdr(bearer))
    assert d.status_code == 200, d.text

    # Stale-tab child write into the discarded parent loses loudly.
    stale = c.patch(
        f"/attack/coverage/{coverage_id}",
        headers=_hdr(bearer),
        json={"status": "covered"},
    )
    assert stale.status_code == 409, stale.text

    # Next mint is v3 (never collides on the discarded v2).
    a3 = c.post(f"/attack/services/{svc_id}/assessments", headers=_hdr(bearer))
    assert a3.status_code == 201, a3.text
    assert a3.json()["version"] == 3


# ===========================================================================
# CSF discard
# ===========================================================================


@pytest.mark.unit
def test_csf_discard_draft_200_audit_has_answered_count(app_client) -> None:
    c, TestSession, _p = app_client
    bearer = _admin(c)
    _svc, a = _csf_assessment(c, bearer)
    r = c.post(f"/csf/assessments/{a['id']}/discard", headers=_hdr(bearer))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "discarded"
    assert _audit_count(TestSession, "csf.assessment.discarded") == 1
    with TestSession() as db:
        row = db.execute(
            select(AuditEntry).where(AuditEntry.action == "csf.assessment.discarded")
        ).scalar_one()
        assert "answered_count" in row.details
        assert "version" in row.details


@pytest.mark.unit
def test_csf_rediscard_idempotent(app_client) -> None:
    c, TestSession, _p = app_client
    bearer = _admin(c)
    _svc, a = _csf_assessment(c, bearer)
    c.post(f"/csf/assessments/{a['id']}/discard", headers=_hdr(bearer))
    r = c.post(f"/csf/assessments/{a['id']}/discard", headers=_hdr(bearer))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "discarded"
    assert _audit_count(TestSession, "csf.assessment.discarded") == 1


@pytest.mark.unit
def test_csf_discard_submitted_409_not_discardable(app_client) -> None:
    c, _TS, _p = app_client
    bearer = _admin(c)
    svc_id, a = _csf_assessment(c, bearer)
    # Drive to SUBMITTED via the self-assessment submit endpoint.
    sub = c.post(
        f"/csf/services/{svc_id}/self-assessment/submit",
        headers=_hdr(bearer),
        json={},
    )
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "submitted"
    r = c.post(f"/csf/assessments/{a['id']}/discard", headers=_hdr(bearer))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "not_discardable"


@pytest.mark.unit
def test_csf_client_touched_draft_is_discardable(app_client) -> None:
    c, _TS, _p = app_client
    admin_bearer = _admin(c)
    svc_id, a = _csf_assessment(c, admin_bearer)
    answer_id = a["answers"][0]["id"]
    client = _register(c, "client@example.com")
    c.headers["X-Client-Id"] = client["user"]["client_id"]
    # Client enters data on their own draft (still DRAFT).
    p = c.patch(
        f"/csf/self-assessment/answers/{answer_id}",
        headers=_hdr(client["tokens"]["access_token"]),
        json={"maturity_tier": 2},
    )
    assert p.status_code == 200, p.text
    # Admin can still discard a client-touched draft.
    r = c.post(f"/csf/assessments/{a['id']}/discard", headers=_hdr(admin_bearer))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "discarded"


@pytest.mark.unit
def test_csf_child_mutation_after_discard_409(app_client) -> None:
    c, _TS, _p = app_client
    bearer = _admin(c)
    _svc, a = _csf_assessment(c, bearer)
    answer_id = a["answers"][0]["id"]
    c.post(f"/csf/assessments/{a['id']}/discard", headers=_hdr(bearer))
    stale = c.patch(f"/csf/answers/{answer_id}", headers=_hdr(bearer), json={"maturity_tier": 3})
    assert stale.status_code == 409, stale.text


@pytest.mark.unit
def test_csf_version_trap(app_client) -> None:
    c, _TS, _p = app_client
    bearer = _admin(c)
    svc_id, a1 = _csf_assessment(c, bearer)
    ap = c.post(f"/csf/assessments/{a1['id']}/approve", headers=_hdr(bearer))
    assert ap.status_code == 200
    a2 = c.post(f"/csf/services/{svc_id}/assessments", headers=_hdr(bearer)).json()
    assert a2["version"] == 2
    c.post(f"/csf/assessments/{a2['id']}/discard", headers=_hdr(bearer))
    a3 = c.post(f"/csf/services/{svc_id}/assessments", headers=_hdr(bearer))
    assert a3.status_code == 201, a3.text
    assert a3.json()["version"] == 3


# ===========================================================================
# ZT discard
# ===========================================================================


@pytest.mark.unit
def test_zt_discard_draft_200_one_audit(app_client) -> None:
    c, TestSession, _p = app_client
    bearer = _admin(c)
    _svc, a = _zt_assessment(c, bearer)
    r = c.post(f"/zt/assessments/{a['id']}/discard", headers=_hdr(bearer))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "discarded"
    assert _audit_count(TestSession, "zt.assessment.discarded") == 1


@pytest.mark.unit
def test_zt_rediscard_idempotent(app_client) -> None:
    c, TestSession, _p = app_client
    bearer = _admin(c)
    _svc, a = _zt_assessment(c, bearer)
    c.post(f"/zt/assessments/{a['id']}/discard", headers=_hdr(bearer))
    r = c.post(f"/zt/assessments/{a['id']}/discard", headers=_hdr(bearer))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "discarded"
    assert _audit_count(TestSession, "zt.assessment.discarded") == 1


@pytest.mark.unit
def test_zt_discard_submitted_409(app_client) -> None:
    c, _TS, _p = app_client
    bearer = _admin(c)
    svc_id, a = _zt_assessment(c, bearer)
    sub = c.post(
        f"/zt/services/{svc_id}/self-assessment/submit",
        headers=_hdr(bearer),
        json={},
    )
    assert sub.status_code == 200, sub.text
    r = c.post(f"/zt/assessments/{a['id']}/discard", headers=_hdr(bearer))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "not_discardable"


@pytest.mark.unit
def test_zt_child_mutation_after_discard_409(app_client) -> None:
    c, _TS, _p = app_client
    bearer = _admin(c)
    _svc, a = _zt_assessment(c, bearer)
    answer_id = a["answers"][0]["id"]
    c.post(f"/zt/assessments/{a['id']}/discard", headers=_hdr(bearer))
    stale = c.patch(f"/zt/answers/{answer_id}", headers=_hdr(bearer), json={"maturity_stage": 2})
    assert stale.status_code == 409, stale.text


@pytest.mark.unit
def test_zt_version_trap(app_client) -> None:
    c, _TS, _p = app_client
    bearer = _admin(c)
    svc_id, a1 = _zt_assessment(c, bearer)
    c.post(f"/zt/assessments/{a1['id']}/approve", headers=_hdr(bearer))
    a2 = c.post(f"/zt/services/{svc_id}/assessments", headers=_hdr(bearer)).json()
    assert a2["version"] == 2
    c.post(f"/zt/assessments/{a2['id']}/discard", headers=_hdr(bearer))
    a3 = c.post(f"/zt/services/{svc_id}/assessments", headers=_hdr(bearer))
    assert a3.status_code == 201, a3.text
    assert a3.json()["version"] == 3


# ===========================================================================
# Hidden "latest" consumers: Risk Register gate/synthesis + engagement cards
# ===========================================================================


def _build_service(db: Session, *, kind, client_id, opened_by, title="x"):
    from app.models.service import Service, ServiceStatus

    svc = Service(
        kind=kind,
        status=ServiceStatus.IN_PROGRESS,
        title=title,
        client_id=client_id,
        opened_by=opened_by,
    )
    db.add(svc)
    db.flush()
    return svc


@pytest.mark.unit
def test_risk_gate_and_findings_skip_discarded(app_client) -> None:
    c, TestSession, _p = app_client
    reg = _register(c, "admin@example.com")
    admin_id = _uuid.UUID(reg["user"]["id"])
    client_id = _uuid.UUID(c.headers["X-Client-Id"])

    from app.models.attack_assessment import (
        AttackAssessment,
        AttackAssessmentStatus,
        AttackCoverage,
    )
    from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus
    from app.models.service import ServiceKind
    from app.routes.risk import _gate, _gather_findings

    with TestSession() as db:
        # Attack v1 APPROVED with a gap; v2 DISCARDED without.
        attack_svc = _build_service(
            db, kind=ServiceKind.ATTACK_COVERAGE, client_id=client_id, opened_by=admin_id
        )
        a1 = AttackAssessment(
            service_id=attack_svc.id,
            client_id=client_id,
            version=1,
            status=AttackAssessmentStatus.APPROVED,
        )
        a2 = AttackAssessment(
            service_id=attack_svc.id,
            client_id=client_id,
            version=2,
            status=AttackAssessmentStatus.DISCARDED,
        )
        db.add_all([a1, a2])
        db.flush()
        db.add(
            AttackCoverage(
                assessment_id=a1.id,
                client_id=client_id,
                technique_code="T1003",
                status="gap",
            )
        )
        db.add(
            AttackCoverage(
                assessment_id=a2.id,
                client_id=client_id,
                technique_code="T1003",
                status="covered",
            )
        )
        # A CSF draft so the gate can unlock (needs attack AND csf|zt).
        csf_svc = _build_service(
            db, kind=ServiceKind.NIST_CSF, client_id=client_id, opened_by=admin_id
        )
        db.add(
            CsfAssessment(
                service_id=csf_svc.id,
                client_id=client_id,
                version=1,
                status=CsfAssessmentStatus.DRAFT,
            )
        )
        db.commit()

        g = _gate(db, client_id)
        assert g.has_attack is True  # v1 approved satisfies it, v2 discarded ignored
        assert g.unlocked is True

        findings, _techs, _controls = _gather_findings(db, client_id)
        attack_findings = [f for f in findings if f["kind"] == "attack"]
        # The gap comes from v1; v2's "covered" must never be read.
        assert len(attack_findings) == 1
        assert attack_findings[0]["source_id"] == "T1003"
        assert "gap" in attack_findings[0]["label"]


@pytest.mark.unit
def test_risk_gate_locked_when_only_attack_discarded(app_client) -> None:
    c, TestSession, _p = app_client
    reg = _register(c, "admin@example.com")
    admin_id = _uuid.UUID(reg["user"]["id"])
    client_id = _uuid.UUID(c.headers["X-Client-Id"])

    from app.models.attack_assessment import AttackAssessment, AttackAssessmentStatus
    from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus
    from app.models.service import ServiceKind
    from app.routes.risk import _gate

    with TestSession() as db:
        attack_svc = _build_service(
            db, kind=ServiceKind.ATTACK_COVERAGE, client_id=client_id, opened_by=admin_id
        )
        db.add(
            AttackAssessment(
                service_id=attack_svc.id,
                client_id=client_id,
                version=1,
                status=AttackAssessmentStatus.DISCARDED,
            )
        )
        csf_svc = _build_service(
            db, kind=ServiceKind.NIST_CSF, client_id=client_id, opened_by=admin_id
        )
        db.add(
            CsfAssessment(
                service_id=csf_svc.id,
                client_id=client_id,
                version=1,
                status=CsfAssessmentStatus.DRAFT,
            )
        )
        db.commit()

        g = _gate(db, client_id)
        assert g.has_attack is False
        assert g.unlocked is False


@pytest.mark.unit
def test_intake_engagement_status_skips_discarded(app_client) -> None:
    c, TestSession, _p = app_client
    reg = _register(c, "admin@example.com")
    admin_id = _uuid.UUID(reg["user"]["id"])
    client_id = _uuid.UUID(c.headers["X-Client-Id"])

    from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus
    from app.models.service import ServiceKind
    from app.routes.intake import _latest_assessment_status

    with TestSession() as db:
        svc = _build_service(db, kind=ServiceKind.NIST_CSF, client_id=client_id, opened_by=admin_id)
        db.add(
            CsfAssessment(
                service_id=svc.id,
                client_id=client_id,
                version=1,
                status=CsfAssessmentStatus.APPROVED,
            )
        )
        db.add(
            CsfAssessment(
                service_id=svc.id,
                client_id=client_id,
                version=2,
                status=CsfAssessmentStatus.DISCARDED,
            )
        )
        db.commit()
        db.refresh(svc)
        # Reports the latest NON-discarded status, not the discarded v2.
        assert _latest_assessment_status(db, svc) == "approved"

        # Discarded-only -> no active assessment status.
        svc2 = _build_service(
            db, kind=ServiceKind.NIST_CSF, client_id=client_id, opened_by=admin_id
        )
        db.add(
            CsfAssessment(
                service_id=svc2.id,
                client_id=client_id,
                version=1,
                status=CsfAssessmentStatus.DISCARDED,
            )
        )
        db.commit()
        db.refresh(svc2)
        assert _latest_assessment_status(db, svc2) is None
