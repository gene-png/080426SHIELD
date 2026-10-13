"""#1120: an assessment that a revision minted says so, for the V3/V4/V5 banners.

`revision` on the ATT&CK, CSF and ZT assessment responses: NULL on every
record no revision minted; on a revision, the version it copied, who started
it, when, why, whether the source was approved under EARLIER rules (V3), and
the ATT&CK codes the current catalog no longer holds (V4). Read from the
`*.revision_started` audit row, which the revision writes in its own
transaction. Through the real routes.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests._csf_world import make_world

pytestmark = pytest.mark.unit

_BODY = {
    "attack": {"title": "ATT&CK"},
    "csf": {"kind": "nist_csf", "title": "CSF"},
    "zt": {"kind": "zero_trust_cisa", "title": "ZT"},
}
_STAMP = {"attack": "parent_rules", "csf": "rollup_rules"}


@pytest.fixture()
def world(tmp_path):
    yield from make_world(tmp_path)


def _admin(c) -> dict:
    r = c.post(
        "/auth/register",
        json={
            "email": "dana@example.com",
            "password": "correct horse battery staple!",
            "display_name": "Dana Reyes",
        },
    )
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}


def _approved(c, h, kind):
    svc = c.post(f"/{kind}/services", headers=h, json=_BODY[kind]).json()["id"]
    v1 = c.post(f"/{kind}/services/{svc}/assessments", headers=h).json()
    assert c.post(f"/{kind}/assessments/{v1['id']}/approve", headers=h).status_code == 200
    return svc, v1


@pytest.mark.parametrize("kind", sorted(_BODY))
def test_a_record_no_revision_minted_has_no_revision(world, kind: str) -> None:
    c, _ = world
    h = _admin(c)
    svc, v1 = _approved(c, h, kind)
    assert v1["revision"] is None
    latest = c.get(f"/{kind}/services/{svc}/assessments/latest", headers=h).json()
    assert latest["revision"] is None


@pytest.mark.parametrize("kind", sorted(_BODY))
def test_a_revision_names_its_source_who_when_and_why(world, kind: str) -> None:
    c, _ = world
    h = _admin(c)
    svc, v1 = _approved(c, h, kind)
    r = c.post(
        f"/{kind}/services/{svc}/assessments/{v1['id']}/revisions",
        headers=h,
        json={"reason": "Client found a typo"},
    )
    assert r.status_code == 201, r.text
    for body in (r.json(), c.get(f"/{kind}/services/{svc}/assessments/latest", headers=h).json()):
        rev = body["revision"]
        assert rev["from_version"] == 1
        assert rev["started_by_name"] == "Dana Reyes"
        assert rev["reason"] == "Client found a typo"
        assert rev["started_at"]
        assert rev["rules_changed"] is False
        assert rev["retired_codes"] == []


@pytest.mark.parametrize("kind", sorted(_STAMP))
def test_a_revision_of_an_earlier_rules_record_says_the_rules_changed(world, kind: str) -> None:
    c, sessions = world
    h = _admin(c)
    svc, v1 = _approved(c, h, kind)
    with sessions() as s:
        s.execute(
            text(f"UPDATE {kind}_assessments SET {_STAMP[kind]} = 1 WHERE id = :id"),  # noqa: S608
            {"id": uuid.UUID(v1["id"]).hex},
        )
        s.commit()
    r = c.post(
        f"/{kind}/services/{svc}/assessments/{v1['id']}/revisions",
        headers=h,
        json={"reason": "r"},
    )
    assert r.json()["revision"]["rules_changed"] is True


_TABLE = {"attack": "attack_assessments", "csf": "csf_assessments", "zt": "zt_assessments"}


def _released_revision(world, kind: str):
    """A client and an admin, the service, and its v2: a revision of v1,
    approved and released, so a client reads it."""
    c, sessions = world
    admin = _admin(c)
    r = c.post(
        "/auth/register",
        json={
            "email": "client@example.com",
            "password": "correct horse battery staple!",
            "display_name": "Cleo Client",
        },
    )
    assert r.status_code == 201, r.text
    client = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    svc, v1 = _approved(c, admin, kind)
    v2 = c.post(
        f"/{kind}/services/{svc}/assessments/{v1['id']}/revisions",
        headers=admin,
        json={"reason": "Consultant-only note"},
    ).json()
    assert c.post(f"/{kind}/assessments/{v2['id']}/approve", headers=admin).status_code == 200
    with sessions() as s:  # RELEASED is reachable; the release route is not under test
        s.execute(
            text(f"UPDATE {_TABLE[kind]} SET status = 'RELEASED' WHERE id = :id"),  # noqa: S608
            {"id": uuid.UUID(v2["id"]).hex},
        )
        s.commit()
    return c, admin, client, svc, v2


@pytest.mark.parametrize("kind", ["csf", "zt"])
def test_a_client_is_never_served_a_revisions_provenance(world, kind: str) -> None:
    """The reason is the consultant's audit-log text and the name may be an
    email: neither is the client's to read. CSF's and ZT's `latest` take any
    signed-in user (ATT&CK's refuses a client: pinned below)."""
    c, admin, client, svc, v2 = _released_revision(world, kind)
    mine = c.get(f"/{kind}/services/{svc}/assessments/latest", headers=client)
    assert mine.status_code == 200, mine.text
    assert mine.json()["id"] == v2["id"]
    assert mine.json()["revision"] is None
    theirs = c.get(f"/{kind}/services/{svc}/assessments/latest", headers=admin).json()
    assert theirs["id"] == v2["id"]
    assert theirs["revision"]["reason"] == "Consultant-only note"


@pytest.mark.parametrize("kind", ["csf", "zt"])
def test_a_clients_self_assessment_carries_no_provenance(world, kind: str) -> None:
    c, admin, client, svc, v2 = _released_revision(world, kind)
    mine = c.get(f"/{kind}/services/{svc}/self-assessment", headers=client)
    assert mine.status_code == 200, mine.text
    assert mine.json()["id"] == v2["id"]
    assert mine.json()["revision"] is None
    theirs = c.get(f"/{kind}/services/{svc}/self-assessment", headers=admin).json()
    assert theirs["revision"]["reason"] == "Consultant-only note"


def test_attack_latest_refuses_a_client_outright(world) -> None:
    """Why ATT&CK has no client case above: its `latest` is admin-only, so no
    client reaches its serializer through a route. The serializer withholds
    provenance from a non-admin regardless."""
    c, admin, client, svc, v2 = _released_revision(world, "attack")
    r = c.get(f"/attack/services/{svc}/assessments/latest", headers=client)
    assert r.status_code == 403, r.text
