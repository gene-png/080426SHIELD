"""#1120: a revision DRAFT is the consultant's, never the client's.

Through the real routes, for a CSF and a ZT service whose v1 the client submitted and
the consultant approved and released, with a revision v2 open as a DRAFT:

1. the client's self-assessment GET returns v1, not the draft;
2. a self-assessment PATCH on the draft's answer is refused (409), whoever
   calls it;
3. a self-assessment submit is refused (409), whoever calls it, with no status
   change;
4. `assessments/latest` for the client returns the newest RELEASED record;
5. `/services/{id}/stages` for the client describes v1;
6. `/intake/engagements` for the client reports v1's status.

The refusals reuse main's existing sentences (advisor, #736 6136520005, (a)).
Every check is asserted beside its admin counterpart, which still sees v2.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests._csf_world import make_world

pytestmark = pytest.mark.unit


@pytest.fixture()
def world(tmp_path):
    yield from make_world(tmp_path)


def _register(c, email: str) -> dict:
    r = c.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple!",
            "display_name": email.split("@")[0],
        },
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}


_BODY = {
    "csf": {"kind": "nist_csf", "title": "CSF"},
    "zt": {"kind": "zero_trust_cisa", "title": "ZT"},
}
_TABLE = {"csf": "csf_assessments", "zt": "zt_assessments"}
KINDS = pytest.mark.parametrize("kind", ["csf", "zt"])


def _revised(world, kind: str):
    """Admin and client headers, the service id, v1's id and v2's id."""
    c, sessions = world
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    svc_id = c.post(f"/{kind}/services", headers=admin, json=_BODY[kind]).json()["id"]
    v1 = c.post(f"/{kind}/services/{svc_id}/assessments", headers=admin).json()["id"]
    r = c.post(f"/{kind}/services/{svc_id}/self-assessment/submit", headers=client, json={})
    assert r.status_code == 200, r.text
    assert c.post(f"/{kind}/assessments/{v1}/approve", headers=admin).status_code == 200
    with sessions() as s:  # RELEASED is reachable; the release route is not under test
        s.execute(
            text(f"UPDATE {_TABLE[kind]} SET status = 'RELEASED' WHERE id = :id"),  # noqa: S608
            {"id": v1.replace("-", "")},
        )
        s.commit()
    r = c.post(
        f"/{kind}/services/{svc_id}/assessments/{v1}/revisions",
        headers=admin,
        json={"reason": "Correct a score"},
    )
    assert r.status_code == 201, r.text
    return c, admin, client, svc_id, v1, r.json()


@KINDS
def test_the_client_self_assessment_reads_v1_not_the_draft(world, kind: str) -> None:
    c, admin, client, svc_id, v1, v2 = _revised(world, kind)
    mine = c.get(f"/{kind}/services/{svc_id}/self-assessment", headers=client)
    assert mine.status_code == 200, mine.text
    assert mine.json()["id"] == v1 and mine.json()["status"] == "released"
    theirs = c.get(f"/{kind}/services/{svc_id}/self-assessment", headers=admin).json()
    assert theirs["id"] == v2["id"]  # the admin still reaches the draft


@KINDS
@pytest.mark.parametrize("who", ["client", "admin"])
def test_a_self_assessment_patch_on_the_draft_is_refused(world, who: str, kind: str) -> None:
    c, admin, client, svc_id, v1, v2 = _revised(world, kind)
    answer_id = v2["answers"][0]["id"]
    r = c.patch(
        f"/{kind}/self-assessment/answers/{answer_id}",
        headers=client if who == "client" else admin,
        json={"notes": "edited"},
    )
    assert r.status_code == 409, r.text
    assert "Your self-assessment is no longer editable." in r.text


@KINDS
@pytest.mark.parametrize("who", ["client", "admin"])
def test_a_submit_on_the_draft_is_refused_and_changes_nothing(world, who: str, kind: str) -> None:
    c, admin, client, svc_id, v1, v2 = _revised(world, kind)
    r = c.post(
        f"/{kind}/services/{svc_id}/self-assessment/submit",
        headers=client if who == "client" else admin,
        json={},
    )
    assert r.status_code == 409, r.text
    assert "This self-assessment has already been submitted." in r.text
    latest = c.get(f"/{kind}/services/{svc_id}/assessments/latest", headers=admin).json()
    assert latest["id"] == v2["id"] and latest["status"] == "draft"


@KINDS
def test_latest_for_the_client_is_the_newest_released_record(world, kind: str) -> None:
    c, admin, client, svc_id, v1, v2 = _revised(world, kind)
    r = c.get(f"/{kind}/services/{svc_id}/assessments/latest", headers=client)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == v1
    assert c.get(f"/{kind}/services/{svc_id}/assessments/latest", headers=admin).json()["id"] == (
        v2["id"]
    )


@KINDS
def test_the_stage_bar_for_the_client_describes_v1(world, kind: str) -> None:
    c, admin, client, svc_id, v1, v2 = _revised(world, kind)
    mine = c.get(f"/services/{svc_id}/stages", headers=client)
    assert mine.status_code == 200, mine.text
    assert mine.json()["version"] == 1
    assert c.get(f"/services/{svc_id}/stages", headers=admin).json()["version"] == 2


@KINDS
def test_the_engagement_list_for_the_client_reports_v1s_status(world, kind: str) -> None:
    c, admin, client, svc_id, v1, v2 = _revised(world, kind)

    def status_for(h) -> str:
        rows = c.get("/intake/engagements", headers=h).json()
        return next(e for e in rows if e["service_id"] == svc_id)["assessment_status"]

    assert status_for(client) == "released"
    assert status_for(admin) == "draft"
