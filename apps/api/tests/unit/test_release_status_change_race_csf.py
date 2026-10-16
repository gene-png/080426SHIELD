"""#1123 item 2, the CSF half (ruled at #736 6216024281): a CSF release must
not commit after the assessment's status changed between the release's
pre-read and its flip.

The twin of `test_release_status_change_race.py` (ZT, ATT&CK, Tech Debt),
written by the CSF track and folded in here. CSF passes no `ParentGuard`;
before #1123 a missed flip with the status moved was logged and the release
committed. A one-shot hook commits APPROVED -> DRAFT (what #1120's unlock
would make possible) from a separate session right before the flip, and the
release is refused with the approved typed 409 and nothing is released.
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
from tests.unit.test_frozen_engagement_target import _register, app_client  # noqa: F401
from tests.unit.test_release_status_change_race import assert_refused

pytestmark = pytest.mark.unit


@contextmanager
def _status_moves_before_the_flip(model: type, parent_id, to_status) -> Iterator[list[bool]]:
    """Commit `to_status` on the parent from a separate session, once, right
    before the release's UPDATE of `model`. T2's hook, unchanged."""
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


def test_csf_release_is_refused_when_the_assessment_moved_before_the_flip(
    app_client,  # noqa: F811
) -> None:
    from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus

    c = app_client
    h = {"Authorization": f"Bearer {_register(c, 'admin@example.com')['tokens']['access_token']}"}
    svc_id = c.post(
        "/csf/services", headers=h, json={"kind": "nist_csf", "title": "Atlas - CSF"}
    ).json()["id"]
    assessment = c.post(f"/csf/services/{svc_id}/assessments", headers=h).json()
    for ans in assessment["answers"]:
        assert (
            c.patch(f"/csf/answers/{ans['id']}", headers=h, json={"maturity_tier": 2}).status_code
            == 200
        )
    assert c.post(f"/csf/assessments/{assessment['id']}/approve", headers=h).status_code == 200
    finalized = c.post(f"/csf/services/{svc_id}/deliverables/finalize", headers=h)
    assert finalized.status_code == 201, finalized.text
    deliv_id = finalized.json()["id"]
    parent = _parent_id(CsfAssessment, svc_id)

    with _status_moves_before_the_flip(CsfAssessment, parent, CsfAssessmentStatus.DRAFT) as fired:
        r = c.post(f"/csf/deliverables/{deliv_id}/release", headers=h)

    assert fired, "the hook never ran -- the race was not driven"
    assert_refused(r)
    assert not _released(deliv_id), "a release committed over an assessment that moved"
