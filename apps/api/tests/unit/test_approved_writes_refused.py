"""#1120 (Option A, ruling item 1): every write route that the ratchet
(`test_approved_record_writers.py`) classifies REFUSED answers 409 for an
APPROVED record, driven through the route itself.

One test per handler, named in `WRITER_VERDICTS`, so the ratchet can require
that each REFUSED verdict is pinned by a test that exists. The Working Profile
writers (A2) are pinned in `test_csf_working_profile_locked.py`.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests._csf_world import make_world

pytestmark = pytest.mark.unit


@pytest.fixture()
def world(tmp_path):
    yield from make_world(tmp_path)


_BODY = {
    "attack": {"title": "ATT&CK"},
    "csf": {"kind": "nist_csf", "title": "CSF"},
    "zt": {"kind": "zero_trust_cisa", "title": "ZT"},
}


def _approved(world, kind: str):
    c, sessions = world
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    svc = c.post(f"/{kind}/services", headers=h, json=_BODY[kind]).json()["id"]
    a = c.post(f"/{kind}/services/{svc}/assessments", headers=h).json()
    ok = c.post(f"/{kind}/assessments/{a['id']}/approve", headers=h)
    assert ok.status_code == 200 and ok.json()["status"] == "approved", ok.text
    return c, h, svc, a


LOCKED = "This assessment is locked."
NOT_DISCARDABLE = "Only a draft assessment can be discarded."


def _refused(r, message: str) -> None:
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == message, r.text


# --- ATT&CK ------------------------------------------------------------------


def test_attack_patch_coverage_refuses_approved(world) -> None:
    c, h, _svc, a = _approved(world, "attack")
    _refused(
        c.patch(f"/attack/coverage/{a['coverage'][0]['id']}", headers=h, json={"notes": "x"}),
        LOCKED,
    )


def test_attack_confirm_coverage_citations_refuses_approved(world) -> None:
    c, h, _svc, a = _approved(world, "attack")
    _refused(
        c.post(f"/attack/coverage/{a['coverage'][0]['id']}/confirm-citations", headers=h), LOCKED
    )


def test_attack_run_ai_refuses_approved(world) -> None:
    c, h, svc, _a = _approved(world, "attack")
    _refused(
        c.post(f"/attack/services/{svc}/run-ai", headers=h, json={"serves": "offline"}), LOCKED
    )


def test_attack_discard_assessment_refuses_approved(world) -> None:
    c, h, _svc, a = _approved(world, "attack")
    _refused(c.post(f"/attack/assessments/{a['id']}/discard", headers=h), NOT_DISCARDABLE)


# --- CSF and ZT --------------------------------------------------------------


@pytest.mark.parametrize("kind", ["csf", "zt"])
def test_patch_answer_refuses_approved(world, kind: str) -> None:
    c, h, _svc, a = _approved(world, kind)
    _refused(
        c.patch(f"/{kind}/answers/{a['answers'][0]['id']}", headers=h, json={"notes": "x"}), LOCKED
    )


@pytest.mark.parametrize("kind", ["csf", "zt"])
def test_patch_self_assessment_answer_refuses_approved(world, kind: str) -> None:
    c, h, _svc, a = _approved(world, kind)
    r = c.patch(
        f"/{kind}/self-assessment/answers/{a['answers'][0]['id']}", headers=h, json={"notes": "x"}
    )
    _refused(r, "Your self-assessment is no longer editable.")


@pytest.mark.parametrize("kind", ["csf", "zt"])
def test_submit_self_assessment_refuses_approved(world, kind: str) -> None:
    c, h, svc, _a = _approved(world, kind)
    _refused(
        c.post(f"/{kind}/services/{svc}/self-assessment/submit", headers=h, json={}),
        "This self-assessment has already been submitted.",
    )


@pytest.mark.parametrize("kind", ["csf", "zt"])
def test_discard_assessment_refuses_approved(world, kind: str) -> None:
    c, h, _svc, a = _approved(world, kind)
    _refused(c.post(f"/{kind}/assessments/{a['id']}/discard", headers=h), NOT_DISCARDABLE)


@pytest.mark.parametrize("kind", ["csf", "zt"])
def test_run_ai_refuses_approved(world, kind: str) -> None:
    c, h, svc, _a = _approved(world, kind)
    _refused(
        c.post(f"/{kind}/services/{svc}/run-ai", headers=h, json={"serves": "offline"}), LOCKED
    )


# --- Tech Debt ---------------------------------------------------------------


def test_tech_debt_discard_capability_list_refuses_approved(world) -> None:
    c, sessions = world
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    svc = c.post("/tech-debt/services", headers=h, json={"title": "TD"}).json()["id"]
    list_id = uuid.uuid4()
    with sessions() as s:  # an APPROVED list is reachable; extraction is not under test
        s.execute(
            text(
                "INSERT INTO capability_lists (id, service_id, version, status, revision, "
                "created_at, updated_at) VALUES (:id, :svc, 1, 'APPROVED', 0, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": list_id.hex, "svc": uuid.UUID(svc).hex},
        )
        s.commit()
    _refused(
        c.post(f"/tech-debt/capability-lists/{list_id}/discard", headers=h),
        "Only a draft capability list can be discarded.",
    )
