"""A DISCARDED assessment must not be approvable (#702; CSF and ZT).

#664's sweep found that `approve_assessment` in CSF and ZT refuses only
RELEASED (and returns early on APPROVED), so a DISCARDED assessment -- retired
from every "latest" consumer by D-031 -- would flip to APPROVED and become
finalizable again. Written before the fix, to establish whether that is real.
ATT&CK has the same shape but its routes are being changed by another open PR,
so it is not covered here.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.audit_entry import AuditEntry

pytestmark = pytest.mark.unit


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    url = f"sqlite:///{tmp_path / 'discarded.db'}"
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
    from app.models.client import Client
    from app.models.client_domain import ClientDomain

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestSession() as seed:
        tenant = Client(legal_name="Test Tenant")
        seed.add(tenant)
        seed.flush()
        seed.add(ClientDomain(client_id=tenant.id, domain="example.com"))
        seed.commit()
        cid = str(tenant.id)
    with TestClient(app, headers={"X-Client-Id": cid}) as c:
        yield c, TestSession


def _admin(c: TestClient) -> dict:
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "admin",
        },
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}


# (service prefix, the body that opens a service of that kind)
SERVICES = [
    ("csf", {"kind": "nist_csf", "title": "CSF"}),
    ("zt", {"kind": "zero_trust_cisa", "title": "ZT"}),
]


def _discarded_assessment(c: TestClient, hdr: dict, prefix: str, body: dict) -> str:
    sr = c.post(f"/{prefix}/services", headers=hdr, json=body)
    assert sr.status_code == 201, sr.text
    ar = c.post(f"/{prefix}/services/{sr.json()['id']}/assessments", headers=hdr)
    assert ar.status_code == 201, ar.text
    aid = ar.json()["id"]
    d = c.post(f"/{prefix}/assessments/{aid}/discard", headers=hdr)
    assert d.status_code == 200, d.text
    # Not vacuous: the discard really landed before approve is tried.
    assert d.json()["status"] == "discarded", d.json()
    return aid


def _stored_status(TestSession: sessionmaker, prefix: str, aid: str) -> str:
    """Read from the database: neither service has a GET-by-id route."""
    import uuid

    from app.models.csf_assessment import CsfAssessment
    from app.models.zt_assessment import ZtAssessment

    model = {"csf": CsfAssessment, "zt": ZtAssessment}[prefix]
    with TestSession() as db:
        return str(db.get(model, uuid.UUID(aid)).status.value)


def _approved_audit_rows(TestSession: sessionmaker, prefix: str) -> int:
    with TestSession() as db:
        return db.execute(
            select(func.count())
            .select_from(AuditEntry)
            .where(AuditEntry.action == f"{prefix}.assessment.approved")
        ).scalar_one()


@pytest.mark.parametrize(("prefix", "body"), SERVICES, ids=[s[0] for s in SERVICES])
def test_approving_a_discarded_assessment_is_refused(app_client, prefix: str, body: dict) -> None:
    c, TestSession = app_client
    hdr = _admin(c)
    aid = _discarded_assessment(c, hdr, prefix, body)

    r = c.post(f"/{prefix}/assessments/{aid}/approve", headers=hdr)

    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["reason"] == "assessment_discarded", err
    assert "discarded" in err["message"].lower()
    # Nothing changed: still discarded, and no approval was audited.
    assert _stored_status(TestSession, prefix, aid) == "discarded"
    assert _approved_audit_rows(TestSession, prefix) == 0


# The tenant lookup each approve route calls first, by module.
_LOOKUP = {"csf": "require_csf_assessment_in_tenant", "zt": "require_zt_assessment_in_tenant"}


@pytest.mark.parametrize(("prefix", "body"), SERVICES, ids=[s[0] for s in SERVICES])
def test_a_discard_landing_after_approve_loads_the_row_still_wins(
    app_client, monkeypatch, prefix: str, body: dict
) -> None:
    """The race a status check alone cannot close. Approve loads a DRAFT; a
    discard commits (discard's own UPDATE is conditional on DRAFT); approve
    then writes. A plain `a.status = APPROVED` flushes over the discard, so the
    write itself must be conditional. The hook commits the discard, in its own
    session, right after the route's tenant lookup has loaded the row."""
    import importlib
    import uuid

    from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus
    from app.models.zt_assessment import ZtAssessment, ZtAssessmentStatus

    c, TestSession = app_client
    hdr = _admin(c)
    sr = c.post(f"/{prefix}/services", headers=hdr, json=body)
    ar = c.post(f"/{prefix}/services/{sr.json()['id']}/assessments", headers=hdr)
    aid = ar.json()["id"]
    model, discarded = {
        "csf": (CsfAssessment, CsfAssessmentStatus.DISCARDED),
        "zt": (ZtAssessment, ZtAssessmentStatus.DISCARDED),
    }[prefix]

    routes = importlib.import_module(f"app.routes.{prefix}")
    original = getattr(routes, _LOOKUP[prefix])
    fired = []

    def load_then_discard(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        row = original(*args, **kwargs)
        if not fired:
            fired.append(True)
            with TestSession() as other:
                other.get(model, uuid.UUID(aid)).status = discarded
                other.commit()
        return row

    monkeypatch.setattr(routes, _LOOKUP[prefix], load_then_discard)
    r = c.post(f"/{prefix}/assessments/{aid}/approve", headers=hdr)

    assert fired, "the hook never ran, so this proved nothing"
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "assessment_discarded"
    assert _stored_status(TestSession, prefix, aid) == "discarded"
    assert _approved_audit_rows(TestSession, prefix) == 0
