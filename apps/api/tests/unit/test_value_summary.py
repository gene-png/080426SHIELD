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
from sqlalchemy import update as sa_update
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


def _service_ids(db: Session, client_id) -> list:
    """Every service id belonging to a client, in insertion order."""
    from app.models.service import Service

    return list(
        db.execute(select(Service.id).where(Service.client_id == client_id)).scalars().all()
    )


def _add_service(db: Session, client_id, opened_by, kind):
    from app.models.service import Service

    svc = Service(kind=kind, title=f"{kind.value} svc", client_id=client_id, opened_by=opened_by)
    db.add(svc)
    db.flush()
    return svc


def _release(db: Session, service_id, releaser, *, parent_version: int = 1) -> None:
    """Seed a released deliverable the way FINALIZE builds one.

    `parent_version` is stamped here because all four finalize routes stamp it
    (`attack.py`, `csf.py`, `zt.py`, `tech_debt.py`, each `parent_version=<parent>.version`)
    and `seed_demo.py` stamps it too — a deliverable without it is a row only a
    pre-migration-0041 database can hold. This fixture left it NULL, so it
    described a world the product cannot produce, and every assertion built on it
    was silently exercising the legacy path rather than the shipped one (#114).
    """
    from app.models.deliverable import Deliverable

    db.add(
        Deliverable(
            service_id=service_id,
            title="report",
            version=1,
            parent_version=parent_version,
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

        db.add(
            Deliverable(
                service_id=svc.id,
                title="draft",
                version=1,
                parent_version=1,
                finalized_at=_NOW,
            )
        )
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


def _choose_target(db, client_id, requested_by, service_id, *, zt=None, csf=None) -> None:
    """Attach an intake request carrying the client's chosen target.

    The seeds above create a Service with NO `source_request_id`, so every
    target in this file resolves to "default" -- the client chose nothing. That
    is a legitimate state and it is also the state that hid #207: with nothing
    but defaults in the fixtures, a card saying "your target" was wrong in every
    test and no assertion could see it.
    """
    from app.models.service import Service
    from app.models.service_request import ServiceRequest, ServiceType

    sr = ServiceRequest(
        service_type=ServiceType.ZERO_TRUST_CISA if zt is not None else ServiceType.NIST_CSF,
        client_id=client_id,
        requested_by=requested_by,
        zt_target_stage=zt,
        csf_target_tier=csf,
    )
    db.add(sr)
    db.flush()
    svc = db.get(Service, service_id)
    svc.source_request_id = sr.id
    db.flush()


def _latest_service(db, client_id, kind):
    """The most recently added service of a kind, for attaching a request to."""
    from app.models.service import Service

    rows = (
        db.execute(select(Service.id).where(Service.client_id == client_id, Service.kind == kind))
        .scalars()
        .all()
    )
    return rows[-1]


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


@pytest.mark.unit
def test_value_summary_ignores_a_post_release_APPROVED_reassessment(app_client) -> None:
    """#114, the value-summary half — the case its §12 twin above cannot reach.

    `test_value_summary_ignores_post_release_draft` cuts v2 as a DRAFT, and the
    old "latest APPROVED or RELEASED" rule already excluded drafts. So that test
    passed for the life of the defect while proving nothing about it: the status
    filter it exercised was never the half that broke. The state that breaks is
    v2 APPROVED — which is not an edge case but the mandatory step before v2 can
    be finalized at all.
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
    svc_id = db.execute(select(CsfAssessment.service_id)).scalar_one()
    # A v2 re-assessment with 9 gaps, APPROVED and NOT finalized: nothing has
    # been delivered, and the client still holds only the v1 report.
    v2 = CsfAssessment(
        service_id=svc_id,
        client_id=_uuid.UUID(cid),
        version=2,
        status=CsfAssessmentStatus.APPROVED,
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
    assert r.json()["csf_gap_count"] == 5, (
        "the executive card reported v2's 9 gaps from an assessment the client "
        "has never been given, with no version label beside the number to say so"
    )


def _break_parent_link(db: Session, service_id) -> None:
    """Point a released deliverable at a parent version that does not exist.

    This constructs the LEGACY state deliberately. It is not reachable through
    the product -- every finalize route stamps a real `parent_version` and
    nothing moves a parent backwards -- so a pre-migration-0041 database is the
    only place it occurs naturally, and a direct write is the only way to build
    it in a test.

    **What this is NOT.** It is not a test supplying its own precondition from
    the thing under test (#72). The claim under test is what `/value-summary`
    DOES when a parent cannot be resolved; the claim that releasing establishes
    the link is a different one, is not asserted here, and is #59's. The setup
    builds the world; the assertion is entirely about the response.
    """
    from app.models.deliverable import Deliverable

    db.execute(
        sa_update(Deliverable).where(Deliverable.service_id == service_id).values(parent_version=99)
    )
    db.flush()


@pytest.mark.unit
def test_value_summary_flags_are_false_when_everything_resolves(app_client) -> None:
    """The FALSE side of every flag, through every flag's SUCCESS return.

    Three tests assert the flags go True. None asserted they stay False, so an
    implementation setting `unresolved=True` unconditionally would satisfy all
    of them — the flag would be a constant wearing a predicate's name.

    **All four kinds are seeded, and that is the point rather than thoroughness.**
    The first version of this test seeded CSF alone, so `attack_uncovered_unresolved`
    and `tech_debt_savings_unresolved` read False through
    `if not service_ids: return _KindTotal(None, False)` — the empty-list early
    return — and never through the success return the assertion is about. The
    docstring claimed "every flag" while pinning two, which is the defect this
    test exists to prevent, one level down. Flipping
    `_attack_uncovered_total`'s final `_KindTotal(total, False)` to `True` left
    the whole suite green while a client would see a real technique count
    captioned "we're not showing a number".
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    cid = client["user"]["client_id"]
    admin_id = admin["user"]["id"]

    db = _session(c)
    _make_released_csf(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_csf_codes(5))
    _make_released_zt(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_zt_cisa_codes(4))
    _make_released_attack(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_attack_codes(3))
    _make_released_tech_debt(db, _uuid.UUID(cid), _uuid.UUID(admin_id), cut_costs=[1000])
    db.commit()
    db.close()

    body = c.get(
        f"/clients/{cid}/value-summary",
        headers={"Authorization": f"Bearer {bearer_client}"},
    ).json()

    # Preconditions: every kind reached its SUCCESS return. Without these the
    # flag assertions below pass through the empty-list branch and say nothing.
    assert body["csf_gap_count"] == 5
    assert body["zt_gap_count"] == 4
    assert body["attack_uncovered_count"] == 3
    assert body["tech_debt_savings_usd"] == 1000.0
    assert body["has_unresolved"] is False
    for flag in (
        "csf_gap_unresolved",
        "zt_gap_unresolved",
        "attack_uncovered_unresolved",
        "tech_debt_savings_unresolved",
    ):
        assert body[flag] is False, flag


@pytest.mark.unit
def test_value_summary_reports_an_unresolvable_kind_instead_of_refusing(app_client) -> None:
    """One unresolvable kind nulls ITS slot and flags it. The others still compute.

    The refusal this replaces raised out of the endpoint, and
    `apps/web/src/app/home/page.tsx` fetches it in an unguarded `Promise.all`
    with no Next error boundary anywhere under `apps/web/src/app` -- so one
    unresolvable service cost the client the whole home page. Trigger rates
    decided it: the raise fired on ONE unresolvable kind.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    cid = client["user"]["client_id"]
    admin_id = admin["user"]["id"]

    db = _session(c)
    csf_svc_before = set(_service_ids(db, _uuid.UUID(cid)))
    _make_released_csf(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_csf_codes(5))
    csf_sid = next(iter(set(_service_ids(db, _uuid.UUID(cid))) - csf_svc_before))
    _make_released_zt(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_zt_cisa_codes(4))
    _break_parent_link(db, csf_sid)
    db.commit()
    db.close()

    r = c.get(
        f"/clients/{cid}/value-summary",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, (
        "an unresolvable parent must not refuse the whole response -- that took "
        f"the client's home page down with it. Got {r.status_code}: {r.text}"
    )
    body = r.json()
    assert body["csf_gap_count"] is None, "an unresolvable kind must not publish a figure"
    assert body["csf_gap_unresolved"] is True, (
        "the null must say WHY. Without this flag it reads as 'pending', which "
        "tells a client who HAS a released report that they do not"
    )
    assert body["zt_gap_count"] == 4, "one unresolvable kind must not affect another"
    assert body["zt_gap_unresolved"] is False
    assert body["has_unresolved"] is True
    assert body["has_any_data"] is True


@pytest.mark.unit
def test_value_summary_unresolved_and_pending_are_distinguishable(app_client) -> None:
    """The discriminating test: two null slots, two different causes, told apart.

    `csf_gap_count` and `zt_gap_count` are both null here. One is null because
    the client has no released ZT service at all -- genuinely pending. The other
    is null because the deliverable cannot be resolved to its assessment. Before
    this change both rendered as "pending" and nothing could separate them.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    cid = client["user"]["client_id"]
    admin_id = admin["user"]["id"]

    db = _session(c)
    before = set(_service_ids(db, _uuid.UUID(cid)))
    _make_released_csf(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_csf_codes(5))
    csf_sid = next(iter(set(_service_ids(db, _uuid.UUID(cid))) - before))
    _break_parent_link(db, csf_sid)
    db.commit()
    db.close()

    body = c.get(
        f"/clients/{cid}/value-summary",
        headers={"Authorization": f"Bearer {bearer_client}"},
    ).json()

    assert (
        body["csf_gap_count"] is None and body["zt_gap_count"] is None
    ), "precondition: both slots null, so the flag is the ONLY thing separating them"
    assert body["csf_gap_unresolved"] is True, "unresolvable -> flagged"
    assert body["zt_gap_unresolved"] is False, "never released -> pending, NOT flagged"


@pytest.mark.unit
def test_value_summary_with_every_kind_unresolvable_still_renders(app_client) -> None:
    """All four unresolvable: 200, no data, and `has_unresolved` True.

    This is the case that used to disappear in silence. `ValueLoopCard` returns
    null on `!has_any_data`, so a response with no figures and no flag renders
    NOTHING -- no card, no message, no gap. `has_unresolved` is what keeps the
    card on the page to say the figures could not be resolved.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    cid = client["user"]["client_id"]
    admin_id = admin["user"]["id"]

    db = _session(c)
    _make_released_csf(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_csf_codes(5))
    _make_released_zt(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_zt_cisa_codes(4))
    _make_released_attack(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_attack_codes(3))
    _make_released_tech_debt(db, _uuid.UUID(cid), _uuid.UUID(admin_id), cut_costs=[1000])
    for sid in _service_ids(db, _uuid.UUID(cid)):
        _break_parent_link(db, sid)
    db.commit()
    db.close()

    r = c.get(
        f"/clients/{cid}/value-summary",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_any_data"] is False
    assert body["has_unresolved"] is True, (
        "without this the card renders nothing at all and the client is told "
        "nothing -- the silent disappearance this change exists to prevent"
    )
    for slot in (
        "csf_gap_count",
        "zt_gap_count",
        "attack_uncovered_count",
        "tech_debt_savings_usd",
    ):
        assert body[slot] is None, slot
    for flag in (
        "csf_gap_unresolved",
        "zt_gap_unresolved",
        "attack_uncovered_unresolved",
        "tech_debt_savings_unresolved",
    ):
        assert body[flag] is True, flag


# ---------------------------------------------------------------------------
# #207 -- the target the gap figures were counted against.
#
# `_zt_gap_total` and `_csf_gap_total` each sum across every released service of
# their kind, and each summand is counted against a target RESOLVED per service.
# Both computed the source and bound it to `_source`, so the card said "your
# target maturity stage" over a figure that may have been counted against the
# engine default for every one of them.
#
# There is no honest single SOURCE for a mixed set, which is why the response
# carries COUNTS. These tests pin the counts; `lib/home/value-summary.test.ts`
# pins the sentence they turn into.
# ---------------------------------------------------------------------------


def _summary(c, cid, bearer):
    r = c.get(f"/clients/{cid}/value-summary", headers={"Authorization": f"Bearer {bearer}"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.unit
def test_a_client_chosen_target_is_reported_as_chosen(app_client) -> None:
    """The PASSING state. Without it the counts are only observed non-zero."""
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    cid, admin_id = client["user"]["client_id"], admin["user"]["id"]

    db = _session(c)
    _make_released_zt(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_zt_cisa_codes(4))
    _make_released_csf(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_csf_codes(5))
    from app.models.service import ServiceKind

    _choose_target(
        db,
        _uuid.UUID(cid),
        _uuid.UUID(admin_id),
        _latest_service(db, _uuid.UUID(cid), ServiceKind.ZERO_TRUST_CISA),
        zt=3,
    )
    _choose_target(
        db,
        _uuid.UUID(cid),
        _uuid.UUID(admin_id),
        _latest_service(db, _uuid.UUID(cid), ServiceKind.NIST_CSF),
        csf=2,
    )
    db.commit()
    db.close()

    body = _summary(c, cid, client["tokens"]["access_token"])
    assert body["zt_services"] == 1
    assert body["zt_targets_defaulted"] == 0
    assert body["zt_targets_unusable"] == 0
    assert body["csf_services"] == 1
    assert body["csf_targets_defaulted"] == 0
    assert body["csf_targets_unusable"] == 0


@pytest.mark.unit
def test_an_absent_choice_is_reported_as_defaulted(app_client) -> None:
    """The state every other fixture in this file is in, and nothing said so."""
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    cid, admin_id = client["user"]["client_id"], admin["user"]["id"]

    db = _session(c)
    _make_released_zt(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_zt_cisa_codes(4))
    _make_released_csf(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_csf_codes(5))
    db.commit()
    db.close()

    body = _summary(c, cid, client["tokens"]["access_token"])
    assert body["zt_gap_count"] == 4, "the figure itself must be unchanged"
    assert body["zt_targets_defaulted"] == 1
    assert body["zt_targets_unusable"] == 0
    assert body["csf_targets_defaulted"] == 1
    assert body["csf_targets_unusable"] == 0


@pytest.mark.unit
def test_an_unusable_choice_is_not_reported_as_an_absent_one(app_client) -> None:
    """The distinction both resolvers carry the whole way, kept at the last step.

    "The client chose nothing" and "the client's choice could not be used"
    resolve to the same NUMBER and are different facts, and only the second is
    answerable by re-asking them. An aggregate that flattens them throws away the
    actionable half after the resolvers went to some trouble to keep it.

    9 is out of range on every ladder either service has, so this does not
    depend on which stage count a framework happens to publish.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    cid, admin_id = client["user"]["client_id"], admin["user"]["id"]

    db = _session(c)
    _make_released_zt(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_zt_cisa_codes(4))
    _make_released_csf(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_csf_codes(5))
    from app.models.service import ServiceKind

    _choose_target(
        db,
        _uuid.UUID(cid),
        _uuid.UUID(admin_id),
        _latest_service(db, _uuid.UUID(cid), ServiceKind.ZERO_TRUST_CISA),
        zt=9,
    )
    _choose_target(
        db,
        _uuid.UUID(cid),
        _uuid.UUID(admin_id),
        _latest_service(db, _uuid.UUID(cid), ServiceKind.NIST_CSF),
        csf=9,
    )
    db.commit()
    db.close()

    body = _summary(c, cid, client["tokens"]["access_token"])
    assert body["zt_targets_unusable"] == 1
    assert body["zt_targets_defaulted"] == 0, (
        "an out-of-range stored stage was reported as 'chose nothing', which "
        "tells the client they made no choice when they made one that was "
        "discarded"
    )
    assert body["csf_targets_unusable"] == 1
    assert body["csf_targets_defaulted"] == 0


@pytest.mark.unit
def test_a_mixed_set_reports_a_fraction_rather_than_a_label(app_client) -> None:
    """The case that made a single source impossible, and the reason for counts.

    One engagement on the client's own stage and another on the default is
    neither "client" nor "default". Two of three here, so a test that reported
    the FIRST service's source, or the LAST, gets a different answer than one
    that counts -- and a boolean cannot express this state at all.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    cid, admin_id = client["user"]["client_id"], admin["user"]["id"]
    from app.models.service import ServiceKind

    db = _session(c)
    for _ in range(3):
        _make_released_zt(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_zt_cisa_codes(2))
    chosen = _latest_service(db, _uuid.UUID(cid), ServiceKind.ZERO_TRUST_CISA)
    _choose_target(db, _uuid.UUID(cid), _uuid.UUID(admin_id), chosen, zt=3)
    db.commit()
    db.close()

    body = _summary(c, cid, client["tokens"]["access_token"])
    assert body["zt_services"] == 3
    assert body["zt_targets_defaulted"] == 2
    assert body["zt_targets_unusable"] == 0
    assert body["zt_gap_count"] == 6, "three services of two gaps each, still summed"


@pytest.mark.unit
def test_an_unresolvable_kind_reports_null_counts_and_not_zero(app_client) -> None:
    """`0` would read as "nothing was assumed" over something nobody measured.

    A kind goes unresolved WHOLESALE and returns on the FIRST unresolvable
    service, so any tally reached by then describes a prefix of a sum that was
    never published. The invariant is asserted rather than described:
    `(targets_defaulted is None) == (gap_count is None)`.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    cid, admin_id = client["user"]["client_id"], admin["user"]["id"]
    from app.models.service import ServiceKind

    db = _session(c)
    _make_released_zt(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_zt_cisa_codes(4))
    _break_parent_link(db, _latest_service(db, _uuid.UUID(cid), ServiceKind.ZERO_TRUST_CISA))
    db.commit()
    db.close()

    body = _summary(c, cid, client["tokens"]["access_token"])
    assert body["zt_gap_unresolved"] is True
    assert body["zt_gap_count"] is None
    assert body["zt_targets_defaulted"] is None
    assert body["zt_targets_unusable"] is None
    assert body["zt_services"] == 1, (
        "the DENOMINATOR is still known -- the client has one released ZT "
        "report whether or not its figure resolved"
    )


@pytest.mark.unit
def test_the_null_invariant_holds_across_every_state_this_file_produces(app_client) -> None:
    """One assertion over the whole response, not per field.

    A per-field check passes as soon as each field is individually plausible.
    What matters is the PAIRING: a count beside a figure that does not exist is
    a number about nothing, and a null count beside a real figure withholds a
    fact that was measured.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    cid, admin_id = client["user"]["client_id"], admin["user"]["id"]

    db = _session(c)
    _make_released_csf(db, _uuid.UUID(cid), _uuid.UUID(admin_id), gap_codes=_csf_codes(5))
    db.commit()
    db.close()

    body = _summary(c, cid, client["tokens"]["access_token"])
    for kind in ("zt", "csf"):
        figure_absent = body[f"{kind}_gap_count"] is None
        for field in ("targets_defaulted", "targets_unusable"):
            assert (body[f"{kind}_{field}"] is None) == figure_absent, (
                f"{kind}_{field} and {kind}_gap_count disagree about whether "
                f"there is anything to describe"
            )
    # And the two halves of the pairing are BOTH exercised here rather than one:
    # CSF has a released report and ZT has none.
    assert body["csf_gap_count"] == 5 and body["csf_targets_defaulted"] == 1
    assert body["zt_gap_count"] is None and body["zt_targets_defaulted"] is None
    assert body["zt_services"] == 0
