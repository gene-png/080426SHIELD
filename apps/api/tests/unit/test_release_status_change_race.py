"""#1123 item 2 (ruled at #736 6216024281): a release must not commit after the
parent's status changed between the release's pre-read and its flip.

`deliverable_release._release_parent` flips the parent with a conditional
UPDATE (`status = APPROVED`, plus the caller's guard). On a missed flip it
raises the guard's refusal only when the parent is still APPROVED; when the
status itself moved it logs `release_parent_changed_concurrently` and the
release commits. These tests drive that move: a one-shot hook commits
APPROVED -> DRAFT (what #1120's unlock would make possible) from a separate
session immediately before the flip, as
`test_deliverable_release.py::test_a_parent_released_concurrently_is_logged_not_overwritten`
drives APPROVED -> RELEASED.

The release is refused with the approved typed 409 and nothing is released.
On main 2f89930b every one of these returned 200: the release committed over a
parent that moved. The message is quoted from the ruling, never imported.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.deliverable import Deliverable

pytestmark = pytest.mark.unit

#: Approved verbatim at #736 comment 6216024281 (one sentence, every service).
CHANGED = (
    "This assessment changed while the report was being released, so nothing "
    "was released. Reload the page, check the assessment, and release again."
)


def assert_refused(r) -> None:
    assert r.status_code == 409, r.text
    err = r.json()["error"]  # the D-016 envelope
    assert (err["reason"], err["message"]) == ("parent_changed_during_release", CHANGED), err


@contextmanager
def _status_moves_before_the_flip(model: type, parent_id, to_status) -> Iterator[list[bool]]:
    """Commit `to_status` on the parent from a separate session, once, right
    before the release's UPDATE of `model`."""
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    fired: list[bool] = []

    def before_flip(state) -> None:
        mapper = state.bind_mapper
        if not fired and state.is_update and mapper is not None and mapper.class_ is model:
            fired.append(True)
            with sessionmaker(bind=engine, future=True)() as other:
                row = other.get(model, parent_id)
                row.status = to_status
                other.commit()

    event.listen(Session, "do_orm_execute", before_flip)
    try:
        yield fired
    finally:
        event.remove(Session, "do_orm_execute", before_flip)


def _released(deliverable_id: str) -> bool:
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as s:
        return s.get(Deliverable, uuid.UUID(deliverable_id)).released_at is not None


def _parent_id(model: type, service_id: str):
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as s:
        return (
            s.execute(select(model.id).where(model.service_id == uuid.UUID(service_id)))
            .scalars()
            .one()
        )


# --- ZT: no guard today -----------------------------------------------------


def test_zt_release_is_refused_when_the_assessment_moved_before_the_flip(
    app_client,  # noqa: F811
) -> None:
    from app.models.zt_assessment import ZtAssessment, ZtAssessmentStatus
    from tests.unit.test_frozen_engagement_target import (
        _register,
        _zt_finalize_release,
        _zt_score_approve,
        _zt_service,
    )

    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = _zt_service(c, bearer)
    _zt_score_approve(c, bearer, svc_id)
    deliv_id = _zt_finalize_release(c, bearer, svc_id, release=False)
    parent = _parent_id(ZtAssessment, svc_id)

    with _status_moves_before_the_flip(ZtAssessment, parent, ZtAssessmentStatus.DRAFT) as fired:
        r = c.post(f"/zt/deliverables/{deliv_id}/release", headers=h)

    assert fired, "the hook never ran -- the race was not driven"
    assert_refused(r)
    assert not _released(deliv_id), "a release committed over a parent that moved"


def test_zt_release_is_refused_when_the_version_was_approved_after_its_finalize(
    app_client,  # noqa: F811
) -> None:
    """(a), the ratchet: still APPROVED, but the approval in force is newer than
    the deliverable's finalize, as #1120's unlock followed by a re-approval would
    leave it. The guard's condition misses in the flip's own WHERE.

    Red-on-revert: drop `parent_guard=` from the ZT release route and this
    releases (200)."""
    from datetime import UTC, datetime, timedelta

    from app.models.zt_assessment import ZtAssessment
    from tests.unit.test_frozen_engagement_target import (
        _register,
        _zt_finalize_release,
        _zt_score_approve,
        _zt_service,
    )

    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = _zt_service(c, bearer)
    _zt_score_approve(c, bearer, svc_id)
    deliv_id = _zt_finalize_release(c, bearer, svc_id, release=False)
    parent = _parent_id(ZtAssessment, svc_id)
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as s:
        s.get(ZtAssessment, parent).approved_at = datetime.now(UTC) + timedelta(hours=1)
        s.commit()

    r = c.post(f"/zt/deliverables/{deliv_id}/release", headers=h)

    assert_refused(r)
    assert not _released(deliv_id)


def test_a_zt_release_with_nothing_moved_still_releases(app_client) -> None:  # noqa: F811
    """The positive state the guards must not break."""
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
    deliv_id = _zt_finalize_release(c, bearer, svc_id, release=False)

    r = c.post(
        f"/zt/deliverables/{deliv_id}/release", headers={"Authorization": f"Bearer {bearer}"}
    )

    assert r.status_code == 200, r.text
    assert _released(deliv_id)


# --- ATT&CK: its guard does not cover a status change -----------------------


def test_attack_release_is_refused_when_the_assessment_moved_before_the_flip(
    env,  # noqa: F811
) -> None:
    from app.models.attack_assessment import AttackAssessment, AttackAssessmentStatus
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
    deliv_id = _approve_and_finalize(c, bearer, svc, a)
    _stored_statuses(Sess, a["id"])

    with _status_moves_before_the_flip(
        AttackAssessment, uuid.UUID(a["id"]), AttackAssessmentStatus.DRAFT
    ) as fired:
        r = c.post(f"/attack/deliverables/{deliv_id}/release", headers=_auth(bearer))

    assert fired, "the hook never ran -- the race was not driven"
    assert_refused(r)
    assert not _released(deliv_id), "a release committed over an assessment that moved"


# The two fixtures (Tech Debt's `app_client` has a different shape, so its
# test lives in `test_release_status_change_race_tech_debt.py`).
from tests.unit.test_attack_catalog_version_guard import env  # noqa: E402,F401
from tests.unit.test_frozen_engagement_target import app_client  # noqa: E402,F401
