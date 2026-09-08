"""What states a capability list can actually reach, established by RUNNING.

Written because a reviewer's read of the state graph decided the wording of a
user-facing remedy in the ATT&CK ai-inputs panel (#178). A reading is not a
measurement: the panel tells a consultant what to DO, and if the reachable
states are not what the reader believed, the instruction is wrong in the place
someone acts on it.
"""

from __future__ import annotations

import os
import uuid as _uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.capability import CapabilityList, CapabilityListStatus
from app.models.service import Service, ServiceKind, ServiceStatus

pytestmark = pytest.mark.unit


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    url = f"sqlite:///{tmp_path / 'shield-status-graph.db'}"
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
    with TestClient(app) as c:
        yield c, TestSession
    app.dependency_overrides.clear()


def _admin(c: TestClient) -> tuple[str, str]:
    admin = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    bearer = admin.json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Acme"},
    ).json()["id"]
    return bearer, cid


def _draft_list(TestSession: sessionmaker, cid: str, uid: str) -> str:
    with TestSession() as db:
        svc = Service(
            kind=ServiceKind.TECH_DEBT,
            status=ServiceStatus.IN_PROGRESS,
            title="Acme Tech Debt",
            client_id=_uuid.UUID(cid),
            opened_by=_uuid.UUID(uid),
        )
        db.add(svc)
        db.flush()
        cl = CapabilityList(service_id=svc.id, version=1, status=CapabilityListStatus.DRAFT)
        db.add(cl)
        db.commit()
        return str(cl.id)


def test_approving_a_discarded_list_resurrects_it(app_client) -> None:
    """CURRENT behaviour, pinned as a DEFECT rather than endorsed.

    `discard_capability_list` refuses anything but a DRAFT; `approve_capability_list`
    refuses only RELEASED. So approve is the product's only un-discard, and it is
    undocumented. D-031's stated rule is that an approved/released resource returns
    a typed 409 — this path returns 200 and silently clears the discard, with an
    approval audit row and no record that anything was resurrected.

    Tracked as #231. When it is fixed this test goes RED, and it should:
    the ai-inputs panel's `list_discarded` copy names the remedy for a discarded
    list, and that copy has to change in the same commit.
    """
    c, TestSession = app_client
    bearer, cid = _admin(c)
    uid = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()["id"]
    lid = _draft_list(TestSession, cid, uid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}

    assert c.post(f"/tech-debt/capability-lists/{lid}/discard", headers=h).status_code == 200
    with TestSession() as db:
        assert db.get(CapabilityList, _uuid.UUID(lid)).status == CapabilityListStatus.DISCARDED

    resp = c.post(f"/tech-debt/capability-lists/{lid}/approve", headers=h)
    with TestSession() as db:
        after = db.get(CapabilityList, _uuid.UUID(lid))
        assert (resp.status_code, after.status) == (200, CapabilityListStatus.APPROVED), (
            "if this now refuses, the defect is fixed -- update the ai-inputs "
            "list_discarded remedy copy in the same commit"
        )


def test_a_list_cannot_be_both_discarded_and_carry_an_approved_snapshot(app_client) -> None:
    """The state `_offer`'s snapshot branch was built for is UNREACHABLE via the API.

    `approved_membership` is written in exactly one place, which also sets
    APPROVED; discard accepts only a DRAFT. So approved-then-discarded cannot be
    produced through the product. The unit fixture that constructs it writes the
    rows directly, which is legitimate defence-in-depth against a future writer —
    but the PR body must not claim it closes a live leak, and this test is what
    keeps that claim honest.
    """
    c, TestSession = app_client
    bearer, cid = _admin(c)
    uid = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()["id"]
    lid = _draft_list(TestSession, cid, uid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}

    c.post(f"/tech-debt/capability-lists/{lid}/approve", headers=h)
    discarded = c.post(f"/tech-debt/capability-lists/{lid}/discard", headers=h)
    assert discarded.status_code == 409, "an APPROVED list must not be discardable"

    with TestSession() as db:
        cl = db.get(CapabilityList, _uuid.UUID(lid))
        assert not (
            cl.status == CapabilityListStatus.DISCARDED and cl.approved_membership is not None
        )
