"""The Risk Register's CSF Playbook fingerprint across migration 0074.

`has_evidence` became the three-valued `evidence_status`. A fingerprint a
register recorded before 0074 must still match an unchanged Playbook, or every
existing register would report CSF "changed" at its next publish. A move to
`confirmed_in_discussion` must change it, or that move would go unnoticed.

`STORED` was recorded by running this file's world on main 18447481, before
0074 (the boolean column), so it is the value a pre-0074 register holds. It
is a literal: never recomputed from the code under test.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.csf.catalog import SUBCATEGORIES
from app.risk.inputs import csf_playbook_fingerprint
from tests.unit.test_csf_playbook_override_every_artifact import app_client  # noqa: F401

pytestmark = pytest.mark.unit

CODE = SUBCATEGORIES[0].code
SCORES = {"governance": 2, "policy": 1, "implementation": 2, "monitoring": 0, "improvement": 1}
STORED = "15330925e5766d5bdea464c200b6619fa065b7834e15cbdc51adaaee34e536e4"


def _world(c, h: dict) -> tuple[str, str]:
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()["id"]
    a = c.post(f"/csf/services/{svc}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    r = c.post(f"/csf/services/{svc}/profiles/seed", headers=h, json={"tiers": ["high"]})
    assert r.status_code == 200, r.text
    return svc, a.json()["id"]


def _patch(c, h: dict, svc: str, body: dict) -> None:
    rows = c.get(f"/csf/services/{svc}/profile/high", headers=h).json()["rows"]
    sid = next(r["id"] for r in rows if r["subcategory_code"] == CODE)
    r = c.patch(f"/csf/dimension-scores/{sid}", headers=h, json=body)
    assert r.status_code == 200, r.text


def _fingerprint(aid: str) -> str:
    with Session(create_engine(os.environ["DATABASE_URL"], future=True)) as db:
        return csf_playbook_fingerprint(db, aid)


def test_a_pre_0074_fingerprint_still_matches(app_client) -> None:  # noqa: F811
    c, h = app_client
    svc, aid = _world(c, h)
    _patch(c, h, svc, {**SCORES, "has_evidence": True})
    assert _fingerprint(aid) == STORED


def test_confirmed_in_discussion_changes_it_and_on_file_restores_it(
    app_client,  # noqa: F811
) -> None:
    c, h = app_client
    svc, aid = _world(c, h)
    _patch(c, h, svc, {**SCORES, "evidence_status": "on_file"})
    assert _fingerprint(aid) == STORED  # positive first
    _patch(c, h, svc, {"evidence_status": "confirmed_in_discussion"})
    assert _fingerprint(aid) != STORED
    _patch(c, h, svc, {"evidence_status": "on_file"})
    assert _fingerprint(aid) == STORED
