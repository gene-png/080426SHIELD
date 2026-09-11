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
from sqlalchemy import create_engine, select, update
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


def _assert_no_discarded_row_carries_a_snapshot(TestSession: sessionmaker) -> None:
    """No row ANYWHERE is both DISCARDED and carrying an approved snapshot.

    Table-wide on purpose. The first version asserted this on the single list
    the test had just driven, immediately after asserting discard returned 409 --
    so the list was APPROVED, the left conjunct was False, and the assertion held
    whatever `approved_membership` contained. It restated the 409's consequence
    and could not fail independently of it.

    Run after BOTH sequences here, because the discard -> approve one is what
    actually writes a snapshot onto a formerly-discarded row, and nothing
    checked the invariant on that path at all.
    """
    with TestSession() as db:
        offenders = (
            db.execute(
                select(CapabilityList).where(
                    CapabilityList.status == CapabilityListStatus.DISCARDED,
                    CapabilityList.approved_membership.is_not(None),
                )
            )
            .scalars()
            .all()
        )
    assert offenders == [], (
        "a row is both DISCARDED and carrying an approved snapshot -- the state "
        "`_offer`'s snapshot branch guards is no longer unreachable, and the "
        "PR body's defence-in-depth framing needs revisiting"
    )


def test_approving_a_discarded_list_is_refused(app_client) -> None:
    """#231 FIXED. This test was written to go red, and it did.

    It previously pinned the defect: `approve_capability_list` refused only
    RELEASED, so approve was the product's only un-discard -- 200, status
    flipped, `approved_membership` rebuilt, and nothing anywhere recording that
    a consultant's decision to throw the list away had been reversed.

    Its docstring named what had to change with it, and both were changed in
    the commit that fixed this: the `list_discarded` prose in
    `schemas/attack.py` and `lib/attack/types.ts`, each of which described the
    resurrect path as a defect that EXISTS. The remedy copy on the panel --
    "upload a replacement list" -- needed no change at all, which is exactly why
    it was written to point there rather than at the bug.

    Inverted rather than deleted, per core principle 3: the behaviour genuinely
    changed and the record of what it used to be is worth keeping.

    **The egress consequence is why this matters** rather than state-graph
    tidiness: a discarded list contributes nothing to
    `_client_capability_membership`, so resurrecting it made every in-scope row
    citable again -- exactly what the consultant discarded the list to prevent.
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
    assert resp.status_code == 409, resp.text
    body = resp.json()["error"]
    assert body["reason"] == "capability_list_discarded", body
    assert "replacement" in body["message"].lower(), (
        "the refusal must name the remedy that exists -- a replacement list -- "
        "rather than leaving the consultant at a closed door. CLAUDE.md: a "
        "user-facing string naming an action must name a control that works."
    )

    # AND THE ROW MUST NOT HAVE MOVED. Asserting the 409 alone would pass
    # against a route that COMMITTED and then refused, which is a half-applied
    # refusal and worse than either outcome.
    #
    # Bound, stated so the coverage is not overread: it is commit-then-refuse
    # these catch, not write-then-raise. `override_get_db` closes the session in
    # `finally`, which rolls back an uncommitted write, so a route that set
    # `approved_at` and then raised would still read `None` here and pass. An
    # earlier draft of this comment claimed the wider property.
    with TestSession() as db:
        after = db.get(CapabilityList, _uuid.UUID(lid))
        assert after.status == CapabilityListStatus.DISCARDED
        assert after.approved_at is None
        assert after.approved_by is None

    # The path the invariant helper was WRITTEN for. Its docstring says "run
    # after BOTH sequences ... because the discard -> approve one is what
    # actually writes a snapshot onto a formerly-discarded row", and it had one
    # call site, in the other test -- where the row is APPROVED and the left
    # conjunct is false. The guard it describes was running only where it could
    # not fail.
    _assert_no_discarded_row_carries_a_snapshot(TestSession)


def test_a_discard_committing_mid_approval_is_not_overwritten(app_client, monkeypatch) -> None:
    """The guard is a READ. Without a conditional write it is advisory.

    `approve_capability_list` loaded the row with `db.get`, checked its status,
    and then set `status = APPROVED` unconditionally. Two consultants, or one
    with two tabs: the approve request passes both guards while the row is
    DRAFT, a `/discard` commits, and the unconditional write lands on top of it.
    Final state APPROVED with a fresh snapshot, a discard audit row and an
    approve audit row -- #231's outcome, with the new guard having fired on
    nobody.

    `discard_capability_list` already stated the contract this route did not
    honour: "two racing transactions cannot both observe DRAFT and proceed
    (D-031 concurrency contract)". The two routes read alike; only the SQL
    differed.

    **The interleaving is produced through the real route, not simulated.**
    `build_approved_membership` runs after the guards and before the write, so
    patching it to commit a discard puts a real competing transaction in the
    real window. A test that issued the conditional UPDATE itself would agree
    with the route by construction and stay green over an unconditional one.

    **Bound:** SQLite, one process. This pins the STATEMENT -- that the write
    carries a status predicate and the route refuses when it matches nothing --
    not Postgres' isolation behaviour. Deleting the `.where(... status.in_(...))`
    turns it red, which is the property it was written for.
    """
    c, TestSession = app_client
    bearer, cid = _admin(c)
    uid = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()["id"]
    lid = _draft_list(TestSession, cid, uid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}

    from app.routes import tech_debt as route_mod

    real = route_mod.build_approved_membership
    fired = {"n": 0}

    def discard_then_build(db, list_id):
        # The competing transaction, committed on its OWN connection, which is
        # the part that makes this a race. The audit row a real `/discard` would
        # also write plays no part in it and is left out to keep the injection
        # to the one fact under test.
        if fired["n"] == 0:
            fired["n"] = 1
            with TestSession() as other:
                other.execute(
                    update(CapabilityList)
                    .where(CapabilityList.id == _uuid.UUID(lid))
                    .values(status=CapabilityListStatus.DISCARDED)
                )
                other.commit()
        return real(db, list_id)

    monkeypatch.setattr(route_mod, "build_approved_membership", discard_then_build)

    resp = c.post(f"/tech-debt/capability-lists/{lid}/approve", headers=h)
    assert fired["n"] == 1, (
        "the competing discard never ran, so nothing was raced and this test "
        "proves nothing -- `build_approved_membership` is no longer called "
        "between the guards and the write"
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["reason"] == "capability_list_discarded", resp.text

    with TestSession() as db:
        after = db.get(CapabilityList, _uuid.UUID(lid))
        assert after.status == CapabilityListStatus.DISCARDED, (
            "the approve write overwrote a committed discard: the guard read a "
            "status it then did not write against"
        )
        assert after.approved_membership is None
        assert after.approved_at is None

    _assert_no_discarded_row_carries_a_snapshot(TestSession)


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

    _assert_no_discarded_row_carries_a_snapshot(TestSession)
