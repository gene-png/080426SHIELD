"""`GET /attack/services/{id}/ai-inputs` — provenance and exclusions.

**Not a second payload view.** `POST /ai/preview` already answers "what will be
sent?", generically for all three services, and its button already renders in
the ATT&CK workspace. This endpoint answers the question nothing answers today:
**what was NOT sent, and where did what was sent come from?**

Why that matters, in the filter's own words
(`_client_capability_inputs` in `app/routes/attack.py`):

    "a tool missing from it cannot be named, and the technique it covers reads
     as uncovered"

The filter is CORRECT on all three counts — security scope, list status, and
approved-snapshot membership. That is exactly the point: this is not a bug, it
is a correct filter whose drops are invisible. A `gap` on a client deliverable
can mean "no control here" or "the tool was filtered and nobody could see it",
and the client cannot tell which.

Each test below drives one drop-path, and each asserts the capability is
ABSENT from what would be sent as well as PRESENT in the exclusions — because
"it appears in not_sent" and "it was actually withheld" are different claims,
and only asserting the first would pass over an endpoint that reported
everything twice.
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
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus
from app.models.service import Service, ServiceKind, ServiceStatus


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    url = f"sqlite:///{tmp_path / 'shield-aiinputs.db'}"
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


def _tech_debt_list(
    TestSession: sessionmaker,
    cid: str,
    user_id: str,
    tools: list[tuple[str, bool | None, bool]],
    *,
    status: CapabilityListStatus = CapabilityListStatus.APPROVED,
) -> None:
    """A Tech Debt service + capability list. `tools` is (name, security_related, confirmed)."""
    with TestSession() as db:
        svc = Service(
            kind=ServiceKind.TECH_DEBT,
            status=ServiceStatus.IN_PROGRESS,
            title="Acme Tech Debt",
            client_id=_uuid.UUID(cid),
            opened_by=_uuid.UUID(user_id),
        )
        db.add(svc)
        db.flush()
        cl = CapabilityList(service_id=svc.id, version=1, status=status)
        db.add(cl)
        db.flush()
        for name, related, confirmed in tools:
            db.add(
                CapabilityItem(
                    capability_list_id=cl.id,
                    name=name,
                    security_related=related,
                    security_class_confirmed=confirmed,
                )
            )
        db.commit()


def _attack_service(c: TestClient, bearer: str, cid: str) -> str:
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    return c.post(
        "/attack/services",
        headers=h,
        json={"kind": "attack_coverage", "title": "Acme ATT&CK"},
    ).json()["id"]


@pytest.mark.unit
def test_a_capability_filtered_by_security_scope_is_reported_as_not_sent(app_client) -> None:
    """The misclassification case, and the reason this endpoint exists.

    A tool confirmed non-security is CORRECTLY dropped by `security_scope_filter`.
    Nothing in the product shows that it was dropped, so the technique it covers
    reads as a gap and the client cannot tell that from "no control here".
    """
    c, TestSession = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _tech_debt_list(
        TestSession,
        cid,
        me["id"],
        [("Splunk", None, False), ("Figma", False, True)],
    )
    sid = _attack_service(c, bearer, cid)

    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    r = c.get(f"/attack/services/{sid}/ai-inputs", headers=h)

    assert r.status_code == 200, r.text
    body = r.json()

    sent = [x["name"] for x in body["capabilities"]]
    assert "Splunk" in sent
    assert "Figma" not in sent, "an out-of-scope tool must not be offered to the model"

    withheld = {x["name"]: x for x in body["not_sent"]}
    assert "Figma" in withheld, "the drop must be visible, not merely correct"
    assert withheld["Figma"]["reason"] == "security_scope"


def _approved_list_with_post_approval_drift(
    TestSession: sessionmaker,
    cid: str,
    user_id: str,
) -> None:
    """An APPROVED list whose live rows have moved on since the snapshot was taken.

    Two-phase on purpose -- seed, snapshot, THEN mutate -- because a snapshot
    taken after the mutations records the mutations, and there is no drift left
    to test.

    Seeded through `build_approved_membership`, the production writer, never by
    hand. Its own docstring says why: a hand-written snapshot agrees with the
    reader by construction, so renaming `item_id` in the writer would leave this
    test green while the live join returned nothing. Calling it also means
    `security_scope_filter()` decides which rows the snapshot contains
    (`tech_debt.py:822`) -- this fixture does not get to assert that, which is
    the half the drift cases below turn on.
    """
    with TestSession() as db:
        svc = Service(
            kind=ServiceKind.TECH_DEBT,
            status=ServiceStatus.IN_PROGRESS,
            title="Acme Tech Debt",
            client_id=_uuid.UUID(cid),
            opened_by=_uuid.UUID(user_id),
        )
        db.add(svc)
        db.flush()
        cl = CapabilityList(service_id=svc.id, version=1, status=CapabilityListStatus.APPROVED)
        db.add(cl)
        db.flush()

        # PHASE 1 -- the world as it stood at approval.
        for name, related, confirmed in [
            ("Splunk", None, False),  # in scope -> snapshotted
            ("Wireshark", None, False),  # in scope -> snapshotted
            ("Qualys", True, False),  # in scope -> snapshotted
            ("Figma", False, True),  # out of scope -> the writer drops it
        ]:
            db.add(
                CapabilityItem(
                    capability_list_id=cl.id,
                    name=name,
                    security_related=related,
                    security_class_confirmed=confirmed,
                )
            )
        db.flush()

        from app.routes.tech_debt import build_approved_membership

        cl.approved_membership = build_approved_membership(db, cl.id)
        db.flush()

        # PHASE 2 -- the doors that stay open on an APPROVED list.
        by_name = {
            i.name: i
            for i in db.execute(
                select(CapabilityItem).where(CapabilityItem.capability_list_id == cl.id)
            )
            .scalars()
            .all()
        }
        # `add_capability_components` decomposing a bundle after approval.
        db.add(
            CapabilityItem(
                capability_list_id=cl.id,
                name="Nessus",
                security_related=True,
                security_class_confirmed=False,
            )
        )
        # The confirm queue agreeing with a non-security call after approval.
        by_name["Wireshark"].security_related = False
        by_name["Wireshark"].security_class_confirmed = True
        # A live row deleted out from under its snapshot entry.
        db.delete(by_name["Qualys"])
        db.commit()


@pytest.mark.unit
def test_an_approved_lists_snapshot_is_its_membership_not_its_live_rows(app_client) -> None:
    """Path 3, and the one an implementation built on live rows passes anyway.

    The other test in this file seeds `approved_membership` NULL, so it takes
    the LIVE branch at `attack.py:624`. An endpoint that derives `not_sent` by
    re-querying `CapabilityItem` and negating `security_scope_filter()` is green
    on that test and wrong in BOTH directions here -- it invents a drop for a row
    the snapshot keeps, and hides a drop for a row the snapshot never had.

    **The state space, decided here because no query exists yet to read it off
    of.** Two independent facts about a tool -- is it in the approved snapshot,
    and is it in security scope right now -- so four cells, plus the orthogonal
    case of a snapshot entry with no live row at all:

    ===============  ================  =========================================
    In snapshot?     In scope NOW?     Outcome
    ===============  ================  =========================================
    yes              yes               sent
    yes              no                sent -- the confirm queue removing a row
                                       after approval is deliberate, and the
                                       snapshot is the membership
    yes              (row deleted)     sent, under the snapshot's own name -- the
                                       #96 fail-safe: a deletion must not
                                       silently narrow the allow-list
    no               yes               NOT sent, reason `not_in_approved_snapshot`
    no               no                NOT sent, reason `security_scope`
    ===============  ================  =========================================

    (The sixth cell -- not in the snapshot, no live row -- is unrepresentable:
    neither side holds the tool, so there is nothing to report.)

    **Why the fourth cell's reason names no cause.** That row is live and in
    scope and absent from the snapshot, which happens two ways: it was CREATED
    after approval, or it was created before and re-classified INTO scope after
    (`override_security_classification`, whose exclusion at approval time
    happened inside `build_approved_membership`'s own `security_scope_filter()`).
    Nothing readable at request time separates those -- only an audit trail
    would -- so a reason spelled `added_after_approval` would assert a cause the
    endpoint cannot know, and would read as false to a consultant looking at a
    tool they did not add. `not_in_approved_snapshot` names the state that IS
    observable, and it names the remedy: it is true exactly when
    `approved_membership_stale` is true, and re-approval is what clears both.

    **Why the fifth cell reuses `security_scope` rather than getting its own.**
    Being out of scope now and absent from the snapshot means the filter dropped
    it at approval and would drop it again today, so the same tool in the same
    state gets the same reason whether the list is DRAFT or APPROVED. A separate
    reason would make the consultant's remedy depend on the list's status, which
    it does not.
    """
    c, TestSession = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _approved_list_with_post_approval_drift(TestSession, cid, me["id"])
    sid = _attack_service(c, bearer, cid)

    # The fixture's claim, checked against production code rather than against
    # this file's belief about what it just wrote. If the snapshot and current
    # scope agree, every assertion below passes for the wrong reason -- a
    # live-only implementation would satisfy them too -- and nothing else here
    # would say so.
    with TestSession() as db:
        from app.routes.tech_debt import approved_membership_stale

        cap_list = db.execute(select(CapabilityList)).scalars().one()
        assert approved_membership_stale(db, cap_list) is True, (
            "fixture precondition: the snapshot must actually differ from current "
            "security scope, or this test cannot tell the two implementations apart"
        )

    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    r = c.get(f"/attack/services/{sid}/ai-inputs", headers=h)

    assert r.status_code == 200, r.text
    body = r.json()

    sent = [x["name"] for x in body["capabilities"]]
    withheld = {x["name"]: x for x in body["not_sent"]}

    # In snapshot, still in scope.
    assert "Splunk" in sent
    assert "Splunk" not in withheld

    # In snapshot, moved OUT of scope after approval. A live-only implementation
    # withholds this, and withholding it is #32 facing the other way: a
    # post-approval edit silently rewriting what the model may cite, with no
    # re-approval and no audit.
    assert "Wireshark" in sent, "the snapshot is the membership; a later confirm does not revoke it"
    assert "Wireshark" not in withheld

    # In snapshot, live row deleted. Sent under the snapshot's own name, with no
    # description available -- dropping it would let a deletion narrow the
    # allow-list in silence (#96).
    assert "Qualys" in sent, "a deleted live row must not silently narrow the allow-list"
    assert "Qualys" not in withheld

    # Live and in scope, but the snapshot predates it. A live-only implementation
    # reports this as SENT, which is the lie: the model never sees it, and every
    # technique it covers comes back a fabricated gap.
    assert "Nessus" not in sent, "a row absent from the membership is not offered to the model"
    assert "Nessus" in withheld, "and its absence must be visible, not merely correct"
    assert withheld["Nessus"]["reason"] == "not_in_approved_snapshot"

    # Out of scope at approval and still out of scope. Dropped by the filter
    # inside the writer, and reported the way the DRAFT path reports it.
    assert "Figma" not in sent
    assert "Figma" in withheld
    assert withheld["Figma"]["reason"] == "security_scope"
