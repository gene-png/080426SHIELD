"""#1123 item 1 (ruled at #736 6216024281): `create_assessment` over a RELEASED
latest version is refused with a typed 409, on ZT, CSF and ATT&CK alike.

It used to mint a blank version+1 that is not a revision, so the client doors
did not apply: the client's self-assessment read returned the blank draft over
their released answers, and PATCH and submit accepted it. Start a revision is
the supported way to reopen released work.

The message is quoted from the ruling, never imported. Each test drives the
real routes: release, then create.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.unit

MESSAGE = "Version 1 is released. Use Start a revision to change it."


def _refused(r) -> None:
    assert r.status_code == 409, r.text
    err = r.json()["error"]  # the D-016 envelope
    assert (err["reason"], err["message"]) == ("version_released_use_revision", MESSAGE), err


def _versions(model, service_id: str) -> int:
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as s:
        return s.execute(
            select(func.count()).select_from(model).where(model.service_id == uuid.UUID(service_id))
        ).scalar_one()


def test_zt_create_over_a_released_version_is_refused(app_client) -> None:  # noqa: F811
    from app.models.zt_assessment import ZtAssessment
    from tests.unit.test_frozen_engagement_target import (
        _register,
        _zt_finalize_release,
        _zt_score_approve,
        _zt_service,
    )

    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc_id = _zt_service(c, bearer)
    _zt_score_approve(c, bearer, svc_id)
    _zt_finalize_release(c, bearer, svc_id)  # released
    assert _versions(ZtAssessment, svc_id) == 1

    r = c.post(f"/zt/services/{svc_id}/assessments", headers={"Authorization": f"Bearer {bearer}"})

    _refused(r)
    assert _versions(ZtAssessment, svc_id) == 1, "a blank version was minted over released work"


def test_csf_create_over_a_released_version_is_refused(app_client) -> None:  # noqa: F811
    from app.models.csf_assessment import CsfAssessment
    from tests.unit.test_deliverable_release import _finalized_csf_deliverable
    from tests.unit.test_deliverable_release import _register as _csf_register

    c = app_client
    bearer = _csf_register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    deliv = _finalized_csf_deliverable(c, bearer)
    rel = c.post(f"/csf/deliverables/{deliv['id']}/release", headers=h)
    assert rel.status_code == 200, rel.text
    svc_id = deliv["service_id"]
    assert _versions(CsfAssessment, svc_id) == 1

    r = c.post(f"/csf/services/{svc_id}/assessments", headers=h)

    _refused(r)
    assert _versions(CsfAssessment, svc_id) == 1, "a blank version was minted over released work"


def test_attack_create_over_a_released_version_is_refused(env) -> None:  # noqa: F811
    from app.models.attack_assessment import AttackAssessment
    from tests.unit.test_attack_release_readiness import (
        _approve_and_finalize,
        _auth,
        _register,
        _scored,
        _service_and_assessment,
        _stored_statuses,
    )

    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    _scored(c, bearer, a)
    deliv = _approve_and_finalize(c, bearer, svc, a)
    _stored_statuses(Sess, a["id"])
    rel = c.post(f"/attack/deliverables/{deliv}/release", headers=_auth(bearer))
    assert rel.status_code == 200, rel.text
    assert _versions(AttackAssessment, svc) == 1

    r = c.post(f"/attack/services/{svc}/assessments", headers=_auth(bearer))

    _refused(r)
    assert _versions(AttackAssessment, svc) == 1, "a blank version was minted over released work"


def test_zt_first_create_still_mints(app_client) -> None:  # noqa: F811
    """The positive state: with nothing released, create still works."""
    from tests.unit.test_frozen_engagement_target import _register, _zt_service

    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc_id = _zt_service(c, bearer)
    r = c.post(f"/zt/services/{svc_id}/assessments", headers={"Authorization": f"Bearer {bearer}"})
    assert r.status_code in (200, 201), r.text


from tests.unit.test_attack_catalog_version_guard import env  # noqa: E402,F401
from tests.unit.test_frozen_engagement_target import app_client  # noqa: E402,F401
