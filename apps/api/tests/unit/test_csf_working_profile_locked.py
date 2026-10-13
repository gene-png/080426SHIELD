"""#1120, ruling A2 (#736 6136101129): the CSF Working Profile of an APPROVED or
RELEASED assessment is not edited in place.

`export_playbook` prints these rows to the client under an approved label, so
an edit after approval is the in-place change Option A ends. Through the real
routes:

* `PATCH /csf/dimension-scores/{id}` and `PUT /csf/services/{id}/gap-actions/{code}`
  refuse an APPROVED or RELEASED assessment with a typed 409 naming "Start a
  revision" as the remedy, and change nothing;
* `POST /csf/services/{id}/profiles/seed` is allowed on an APPROVED or RELEASED
  assessment ONLY while it has no profile rows (it creates the missing rows and
  changes nothing that existed); once rows exist it refuses the same way.

Each refusal is asserted beside the positive case on a DRAFT, so a test that
passes because the route is broken cannot pass here.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.csf.catalog import SUBCATEGORIES
from tests._csf_world import make_world

REASON = "working_profile_locked"


@pytest.fixture()
def world(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    yield from make_world(tmp_path)


def _bootstrap(c: TestClient) -> tuple[dict, str, str]:
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()[
        "id"
    ]
    a = c.post(f"/csf/services/{svc_id}/assessments", headers=h).json()
    return h, svc_id, a["id"]


def _approve(c: TestClient, h: dict, assessment_id: str) -> None:
    r = c.post(f"/csf/assessments/{assessment_id}/approve", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"


def _set_released(sessions: sessionmaker, assessment_id: str) -> None:
    """RELEASED is reachable (approve, finalize, release); the release route's
    own behaviour is not under test here, so the world is built directly."""
    with sessions() as db:
        db.execute(
            text("UPDATE csf_assessments SET status = 'RELEASED' WHERE id = :id"),
            {"id": assessment_id.replace("-", "")},
        )
        db.commit()


def _first_row(c: TestClient, h: dict, svc_id: str) -> dict:
    rows = c.get(f"/csf/services/{svc_id}/profile/high", headers=h).json()["rows"]
    return rows[0]


def _assert_locked(r, status_word: str) -> None:
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["reason"] == REASON, err
    assert f"is {status_word}, so its Working Profile cannot be changed" in err["message"], err
    assert "Start a revision" in err["message"], err


def _released_or_approved(c, sessions, h, aid, status_word: str) -> None:
    _approve(c, h, aid)
    if status_word == "released":
        _set_released(sessions, aid)


@pytest.mark.unit
@pytest.mark.parametrize("status_word", ["approved", "released"])
def test_a_dimension_score_patch_is_refused_once_approved(world, status_word: str) -> None:
    c, sessions = world
    h, svc_id, aid = _bootstrap(c)
    assert (
        c.post(
            f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]}
        ).status_code
        == 200
    )
    row = _first_row(c, h, svc_id)
    ok = c.patch(f"/csf/dimension-scores/{row['id']}", headers=h, json={"governance": 1})
    assert ok.status_code == 200, ok.text  # positive first: a DRAFT is editable

    _released_or_approved(c, sessions, h, aid, status_word)
    r = c.patch(f"/csf/dimension-scores/{row['id']}", headers=h, json={"governance": 2})
    _assert_locked(r, status_word)
    assert _first_row(c, h, svc_id)["governance"] == 1  # nothing changed


@pytest.mark.unit
@pytest.mark.parametrize("status_word", ["approved", "released"])
def test_a_gap_action_upsert_is_refused_once_approved(world, status_word: str) -> None:
    c, sessions = world
    h, svc_id, aid = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    ok = c.put(f"/csf/services/{svc_id}/gap-actions/{code}", headers=h, json={"owner": "Dana"})
    assert ok.status_code == 200, ok.text  # positive first

    _released_or_approved(c, sessions, h, aid, status_word)
    r = c.put(f"/csf/services/{svc_id}/gap-actions/{code}", headers=h, json={"owner": "Eve"})
    _assert_locked(r, status_word)
    with sessions() as db:
        owners = (
            db.execute(
                text("SELECT owner FROM csf_gap_actions WHERE subcategory_code = :c"), {"c": code}
            )
            .scalars()
            .all()
        )
    assert owners == ["Dana"], owners  # nothing changed


@pytest.mark.unit
@pytest.mark.parametrize("status_word", ["approved", "released"])
def test_seed_creates_the_missing_rows_on_an_approved_record_then_refuses(
    world, status_word: str
) -> None:
    c, sessions = world
    h, svc_id, aid = _bootstrap(c)
    _released_or_approved(c, sessions, h, aid, status_word)

    first = c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})
    assert first.status_code == 200, first.text  # no rows yet: allowed
    rows = c.get(f"/csf/services/{svc_id}/profile/high", headers=h).json()["rows"]
    assert len(rows) == len(SUBCATEGORIES)

    again = c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["moderate"]})
    _assert_locked(again, status_word)
    moderate = c.get(f"/csf/services/{svc_id}/profile/moderate", headers=h).json()["rows"]
    assert moderate == [], "a refused seed wrote rows"
