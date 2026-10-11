"""#802 slice A: which assessment a what-if is compared with.

The base is the service's newest ATT&CK assessment that is APPROVED or
RELEASED, whose statuses R3 computes (`status_rules` 2), and whose review queue
is empty -- the predicate the release gate re-computes (#554, #808). Anything
else is not "confirmed", and a newer confirmed assessment makes an older
scenario stale.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import update

from app.attack import scenario
from app.models.attack_assessment import (
    AttackAssessment,
    AttackAssessmentStatus,
    AttackCoverage,
)
from tests._attack_rows import standalone_rows
from tests.unit.test_attack_catalog_version_guard import (  # noqa: F401  (fixture)
    _auth,
    _register,
    _service_and_assessment,
    env,
)

pytestmark = pytest.mark.unit


def _world(env):  # noqa: F811
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    return c, Sess, bearer, svc, a


def _stamp(Sess, assessment_id, *, status, rules):
    with Sess() as s:
        s.execute(
            update(AttackAssessment)
            .where(AttackAssessment.id == uuid.UUID(assessment_id))
            .values(status=status, status_rules=rules)
        )
        s.commit()


def _base(Sess, svc):
    with Sess() as s:
        found = scenario.confirmed_base(s, uuid.UUID(svc))
        return None if found is None else str(found.id)


def test_a_draft_is_never_a_base(env) -> None:  # noqa: F811
    _c, Sess, _b, svc, _a = _world(env)
    assert _base(Sess, svc) is None


@pytest.mark.parametrize(
    "status", [AttackAssessmentStatus.APPROVED, AttackAssessmentStatus.RELEASED]
)
def test_an_approved_or_released_r3_assessment_with_no_queue_is_the_base(
    env, status  # noqa: F811
) -> None:
    _c, Sess, _b, svc, a = _world(env)
    _stamp(Sess, a["id"], status=status, rules=2)
    assert _base(Sess, svc) == a["id"]


def test_an_assessment_approved_before_r3_is_not_a_base(env) -> None:  # noqa: F811
    """Its statuses are the AI's suggestions, never reviewed under R3."""
    _c, Sess, _b, svc, a = _world(env)
    _stamp(Sess, a["id"], status=AttackAssessmentStatus.APPROVED, rules=1)
    assert _base(Sess, svc) is None


def test_an_assessment_with_an_unreviewed_queue_is_not_a_base(env) -> None:  # noqa: F811
    """Stored Covered, but only Detect is in place: R3 computes Partial, so the
    row waits in the review queue and nothing about it is confirmed."""
    c, Sess, bearer, svc, a = _world(env)
    (row,) = standalone_rows(a["coverage"], 1)
    r = c.patch(
        f"/attack/coverage/{row['id']}",
        headers=_auth(bearer),
        json={"status": "covered", "detection_tools": ["EDR Tool"]},
    )
    assert r.status_code == 200, r.text
    with Sess() as s:
        s.execute(
            update(AttackCoverage)
            .where(AttackCoverage.id == uuid.UUID(row["id"]))
            .values(unconfirmed_citations=[])
        )
        s.commit()
    _stamp(Sess, a["id"], status=AttackAssessmentStatus.APPROVED, rules=2)
    assert _base(Sess, svc) is None


def test_a_newer_confirmed_assessment_makes_an_older_scenario_stale(env) -> None:  # noqa: F811
    _c, Sess, _b, svc, a = _world(env)
    _stamp(Sess, a["id"], status=AttackAssessmentStatus.RELEASED, rules=2)
    with Sess() as s:
        old = s.get(AttackAssessment, uuid.UUID(a["id"]))
        assert scenario.is_stale(s, uuid.UUID(svc), old.id) is False
        newer = AttackAssessment(
            service_id=old.service_id,
            client_id=old.client_id,
            version=old.version + 1,
            status=AttackAssessmentStatus.APPROVED,
            status_rules=2,
            parent_rules=2,
            catalog_version=old.catalog_version,
        )
        s.add(newer)
        s.commit()
        assert scenario.confirmed_base(s, uuid.UUID(svc)).id == newer.id
        assert scenario.is_stale(s, uuid.UUID(svc), old.id) is True
