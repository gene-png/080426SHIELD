"""Contract tests for the cross-service value-loop summary (Sprint 5 T4).

Master Spec §2.5: one executive card synthesizes Tech Debt savings + ZT gap
count + ATT&CK uncovered-technique count + CSF gap count. "AI suggests, code
computes" is inviolable here — the endpoint is a DETERMINISTIC aggregation over
already-computed engine outputs, never an LLM call and never a fake number.

Visibility follows the §12 release rule (D-025): a service feeds the client-
visible summary ONLY once it has a RELEASED deliverable. A service with no
released deliverable contributes `null` (the card renders "pending"), never a
leaked pre-release number.

These tests build the underlying rows directly (a released deliverable + the
frozen answer rows) so the expected aggregate is deterministic, then assert the
endpoint recomputes it with the pure engines.
"""

from __future__ import annotations

import os
import uuid as _uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "shield-value.db"
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

    c = TestClient(app, headers={"X-Client-Id": _cid})
    c._tenant_id = _cid  # type: ignore[attr-defined]
    with c:
        yield c


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


def _session(c: TestClient) -> Session:
    from app.db.session import get_db

    gen = c.app.dependency_overrides[get_db]()
    return next(gen)


# --- Deterministic data builders (bypass routes for a frozen aggregate) -------

_NOW = datetime(2026, 7, 10, tzinfo=UTC)


def _csf_codes(n: int) -> list[str]:
    from app.csf.catalog import SUBCATEGORIES

    return [s.code for s in SUBCATEGORIES][:n]


def _zt_cisa_codes(n: int) -> list[str]:
    from app.zt.catalog import capabilities
    from app.zt.maturity import ZtFrameworkCode

    return [c.code for c in capabilities(ZtFrameworkCode.CISA_ZTMM_2_0)][:n]


def _attack_codes(n: int) -> list[str]:
    from app.attack.catalog import parent_techniques

    return [t.id for t in parent_techniques()][:n]


def _add_service(db: Session, client_id, opened_by, kind):
    from app.models.service import Service

    svc = Service(kind=kind, title=f"{kind.value} svc", client_id=client_id, opened_by=opened_by)
    db.add(svc)
    db.flush()
    return svc


def _release(db: Session, service_id, releaser) -> None:
    from app.models.deliverable import Deliverable

    db.add(
        Deliverable(
            service_id=service_id,
            title="report",
            version=1,
            finalized_at=_NOW,
            finalized_by=releaser,
            released_at=_NOW,
            released_by=releaser,
        )
    )
    db.flush()


def _make_released_csf(db, client_id, opened_by, *, gap_codes) -> None:
    from app.models.csf_assessment import CsfAnswer, CsfAssessment, CsfAssessmentStatus
    from app.models.service import ServiceKind

    svc = _add_service(db, client_id, opened_by, ServiceKind.NIST_CSF)
    a = CsfAssessment(
        service_id=svc.id,
        client_id=client_id,
        version=1,
        status=CsfAssessmentStatus.APPROVED,
    )
    db.add(a)
    db.flush()
    for code in gap_codes:
        db.add(
            CsfAnswer(
                assessment_id=a.id,
                client_id=client_id,
                subcategory_code=code,
                maturity_tier=1,  # below the tier-3 default target -> a gap
            )
        )
    _release(db, svc.id, opened_by)


def _make_released_zt(db, client_id, opened_by, *, gap_codes, released=True) -> None:
    from app.models.service import ServiceKind
    from app.models.zt_assessment import (
        ZtAnswer,
        ZtAssessment,
        ZtAssessmentStatus,
        ZtFramework,
    )

    svc = _add_service(db, client_id, opened_by, ServiceKind.ZERO_TRUST_CISA)
    a = ZtAssessment(
        service_id=svc.id,
        client_id=client_id,
        framework=ZtFramework.CISA_ZTMM_2_0,
        version=1,
        status=ZtAssessmentStatus.APPROVED,
    )
    db.add(a)
    db.flush()
    for code in gap_codes:
        db.add(
            ZtAnswer(
                assessment_id=a.id,
                client_id=client_id,
                capability_code=code,
                maturity_stage=1,  # below the stage-3 default target -> a gap
                target_stage=None,
            )
        )
    if released:
        _release(db, svc.id, opened_by)
    else:
        from app.models.deliverable import Deliverable

        db.add(Deliverable(service_id=svc.id, title="draft", version=1, finalized_at=_NOW))
        db.flush()


def _make_released_attack(db, client_id, opened_by, *, gap_codes) -> None:
    from app.models.attack_assessment import (
        AttackAssessment,
        AttackAssessmentStatus,
        AttackCoverage,
    )
    from app.models.service import ServiceKind

    svc = _add_service(db, client_id, opened_by, ServiceKind.ATTACK_COVERAGE)
    a = AttackAssessment(
        service_id=svc.id,
        client_id=client_id,
        version=1,
        status=AttackAssessmentStatus.APPROVED,
    )
    db.add(a)
    db.flush()
    for code in gap_codes:
        db.add(
            AttackCoverage(
                assessment_id=a.id,
                client_id=client_id,
                technique_code=code,
                status="gap",
            )
        )
    _release(db, svc.id, opened_by)


def _make_released_tech_debt(db, client_id, opened_by, *, cut_costs, unknown_cost=False) -> None:
    from app.models.capability import (
        CapabilityDisposition,
        CapabilityItem,
        CapabilityList,
        CapabilityListStatus,
    )
    from app.models.service import ServiceKind

    svc = _add_service(db, client_id, opened_by, ServiceKind.TECH_DEBT)
    cl = CapabilityList(service_id=svc.id, version=1, status=CapabilityListStatus.APPROVED)
    db.add(cl)
    db.flush()
    # A KEEP item that must never count toward savings.
    db.add(
        CapabilityItem(
            capability_list_id=cl.id,
            name="Keeper",
            annual_cost_usd=99999,
            disposition=CapabilityDisposition.KEEP,
        )
    )
    for i, cost in enumerate(cut_costs):
        db.add(
            CapabilityItem(
                capability_list_id=cl.id,
                name=f"Cut {i}",
                annual_cost_usd=cost,
                disposition=CapabilityDisposition.CUT,
            )
        )
    if unknown_cost:
        db.add(
            CapabilityItem(
                capability_list_id=cl.id,
                name="Cut no-cost",
                annual_cost_usd=None,
                disposition=CapabilityDisposition.CUT,
            )
        )
    _release(db, svc.id, opened_by)


# --- Tests -------------------------------------------------------------------


@pytest.mark.unit
def test_value_summary_full_data(app_client) -> None:
    """All four services released -> every slot is the recomputed engine number."""
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    cid = client["user"]["client_id"]
    admin_id = admin["user"]["id"]

    csf_codes = _csf_codes(5)
    zt_codes = _zt_cisa_codes(4)
    atk_codes = _attack_codes(3)

    db = _session(c)
    _make_released_csf(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=csf_codes)
    _make_released_zt(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=zt_codes)
    _make_released_attack(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=atk_codes)
    _make_released_tech_debt(db, _uuid.UUID(cid), _uuid.UUID(admin_id), cut_costs=[1000, 2000])
    db.commit()
    db.close()

    r = c.get(
        f"/clients/{cid}/value-summary",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["csf_gap_count"] == 5
    assert body["zt_gap_count"] == 4
    assert body["attack_uncovered_count"] == 3
    assert body["tech_debt_savings_usd"] == 3000.0
    assert body["tech_debt_savings_cost_known"] is True
    assert body["has_any_data"] is True


@pytest.mark.unit
def test_value_summary_partial_data_nulls_for_unreleased(app_client) -> None:
    """Only CSF has a RELEASED deliverable; an unreleased ZT service stays null."""
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    cid = client["user"]["client_id"]
    admin_id = admin["user"]["id"]

    db = _session(c)
    _make_released_csf(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_csf_codes(2))
    # A ZT service that is finalized but NOT released -> must not contribute.
    _make_released_zt(
        db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_zt_cisa_codes(4), released=False
    )
    db.commit()
    db.close()

    r = c.get(
        f"/clients/{cid}/value-summary",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["csf_gap_count"] == 2
    assert body["zt_gap_count"] is None  # spec-12: unreleased leaks nothing
    assert body["attack_uncovered_count"] is None
    assert body["tech_debt_savings_usd"] is None
    assert body["has_any_data"] is True


@pytest.mark.unit
def test_value_summary_no_data(app_client) -> None:
    """A client with no released deliverables -> every slot null, never a fake 0."""
    c = app_client
    _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    cid = client["user"]["client_id"]

    r = c.get(
        f"/clients/{cid}/value-summary",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["csf_gap_count"] is None
    assert body["zt_gap_count"] is None
    assert body["attack_uncovered_count"] is None
    assert body["tech_debt_savings_usd"] is None
    assert body["has_any_data"] is False


@pytest.mark.unit
def test_value_summary_tech_debt_cost_unknown(app_client) -> None:
    """A CUT item with no cost -> savings still computes, cost_known drops to False."""
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    cid = client["user"]["client_id"]
    admin_id = admin["user"]["id"]

    db = _session(c)
    _make_released_tech_debt(
        db, _uuid.UUID(cid), _uuid.UUID(admin_id), cut_costs=[500], unknown_cost=True
    )
    db.commit()
    db.close()

    r = c.get(
        f"/clients/{cid}/value-summary",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tech_debt_savings_usd"] == 500.0
    assert body["tech_debt_savings_cost_known"] is False


@pytest.mark.unit
def test_value_summary_no_llm_call(app_client) -> None:
    """The aggregation path is pure: it must never write an llm_calls row."""
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    cid = client["user"]["client_id"]
    admin_id = admin["user"]["id"]

    db = _session(c)
    _make_released_csf(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_csf_codes(3))
    db.commit()
    db.close()

    r = c.get(
        f"/clients/{cid}/value-summary",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text

    from app.models.llm_call import LLMCall

    db = _session(c)
    count = db.execute(select(func.count()).select_from(LLMCall)).scalar_one()
    db.close()
    assert count == 0

    # And the aggregation module must not reach for the egress client at all.
    import inspect

    import app.routes.clients as clients_mod

    assert "app.ai" not in inspect.getsource(clients_mod)


@pytest.mark.unit
def test_value_summary_ignores_post_release_draft(app_client) -> None:
    """A re-assessment started AFTER release must not leak into the client card.

    Spec §12: the client only ever sees released work. Once v1 is released, a
    consultant may open a new (higher-version) DRAFT assessment; its in-progress
    answers must NOT change the client-visible value numbers. The summary stays
    pinned to the released/finalized version.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    cid = client["user"]["client_id"]
    admin_id = admin["user"]["id"]

    from app.models.csf_assessment import CsfAnswer, CsfAssessment, CsfAssessmentStatus

    db = _session(c)
    # Released v1 with 5 gaps.
    _make_released_csf(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_csf_codes(5))
    # A NEW v2 DRAFT re-assessment with MORE gaps (9), never released.
    svc_id = db.execute(select(CsfAssessment.service_id)).scalar_one()
    v2 = CsfAssessment(
        service_id=svc_id,
        client_id=_uuid.UUID(cid),
        version=2,
        status=CsfAssessmentStatus.DRAFT,
    )
    db.add(v2)
    db.flush()
    for code in _csf_codes(9):
        db.add(
            CsfAnswer(
                assessment_id=v2.id,
                client_id=_uuid.UUID(cid),
                subcategory_code=code,
                maturity_tier=1,
            )
        )
    db.commit()
    db.close()

    r = c.get(
        f"/clients/{cid}/value-summary",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    # Still the released v1's 5 gaps — NOT the v2 draft's 9.
    assert r.json()["csf_gap_count"] == 5


@pytest.mark.unit
def test_value_summary_cross_tenant_404(app_client) -> None:
    """A client asking for another tenant's summary gets 404 (never 403)."""
    c = app_client
    _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    r = c.get(
        f"/clients/{_uuid.uuid4()}/value-summary",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 404, r.text


@pytest.mark.unit
def test_value_summary_admin_via_header(app_client) -> None:
    """A platform admin reads a tenant's summary via X-Client-Id."""
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    cid = client["user"]["client_id"]
    admin_id = admin["user"]["id"]

    db = _session(c)
    _make_released_csf(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_csf_codes(2))
    db.commit()
    db.close()

    # X-Client-Id defaults to the tenant in the fixture's TestClient headers.
    r = c.get(
        f"/clients/{cid}/value-summary",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["csf_gap_count"] == 2
