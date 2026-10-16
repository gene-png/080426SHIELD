"""#982 (A), ruled at #736 6216024281: a ZT per-capability target records who
set it. The consultant's PATCH stamps `target_source = "consultant"`; clearing
the target clears it; a target with no recorded origin reads NULL, which the
consultant workspace discloses. Driven through the routes.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.unit.test_zt_run_ai import _admin_service, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def _first_answer(c, h, svc_id: str) -> dict:
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    return a.json()["answers"][0]


def test_a_consultant_set_target_records_its_origin(app_client) -> None:  # noqa: F811
    c, _ = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    ans = _first_answer(c, h, svc_id)
    assert ans["target_source"] is None  # nothing set yet

    r = c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"target_stage": 4})

    assert r.status_code == 200, r.text
    assert (r.json()["target_stage"], r.json()["target_source"]) == (4, "consultant")


def test_clearing_the_target_clears_its_origin(app_client) -> None:  # noqa: F811
    c, _ = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    ans = _first_answer(c, h, svc_id)
    assert (
        c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"target_stage": 4}).status_code == 200
    )

    r = c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"target_stage": None})

    assert r.status_code == 200, r.text
    assert (r.json()["target_stage"], r.json()["target_source"]) == (None, None)


def test_a_notes_only_patch_leaves_the_origin_alone(app_client) -> None:  # noqa: F811
    c, _ = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    ans = _first_answer(c, h, svc_id)
    assert (
        c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"target_stage": 4}).status_code == 200
    )

    r = c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"notes": "MFA everywhere."})

    assert r.status_code == 200, r.text
    assert (r.json()["target_stage"], r.json()["target_source"]) == (4, "consultant")


def test_a_target_stored_before_the_column_reads_not_recorded(app_client) -> None:  # noqa: F811
    """A row with a target and no origin (every target written before 0076)
    serialises `target_source: null`, never a default origin."""
    from app.models.zt_assessment import ZtAnswer

    c, _ = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    ans = _first_answer(c, h, svc_id)
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as s:
        row = s.get(ZtAnswer, uuid.UUID(ans["id"]))
        row.target_stage = 3  # as an earlier AI run or a pre-0076 edit left it
        s.commit()

    latest = c.get(f"/zt/services/{svc_id}/assessments/latest", headers=h).json()
    got = next(a for a in latest["answers"] if a["id"] == ans["id"])

    assert (got["target_stage"], got["target_source"]) == (3, None)
