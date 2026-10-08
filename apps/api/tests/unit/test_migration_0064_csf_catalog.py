"""Migration 0064 (#852): stored CSF answers survive the catalog correction.

The world is built through the ORM at revision 0063 (0064 changes no schema, so
the models fit both), then upgraded. What the migration must do comes from the
approved plan (#736 comment 6054419744), not from the migration: every
non-discarded assessment gets an empty `RC.CO-04` answer row, and a
`RC.CO-04` Working Profile row for each tier it had already seeded; an existing
`RC.CO-04` row is never duplicated or overwritten; `ID.AM-09` rows are KEPT,
untouched; a discarded assessment and the Risk Register are not touched; and a
downgrade never deletes an answered row.

Statuses are written through the ORM on purpose: the column stores the enum
member NAME, and a migration matching the lowercase value would match nothing
(0045 records the first version that did).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

pytestmark = pytest.mark.unit

NEW = "RC.CO-04"
RETIRED = "ID.AM-09"


def _cfg(url: str) -> Config:
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture()
def world(tmp_path):
    from app.models.client import Client
    from app.models.csf_assessment import CsfAnswer, CsfAssessment, CsfAssessmentStatus
    from app.models.csf_profile import CsfDimensionScore
    from app.models.risk_register import RiskEntry, RiskRegister
    from app.models.service import Service, ServiceKind
    from app.models.user import User, UserRole

    url = f"sqlite:///{tmp_path / 'm0064.db'}"
    os.environ["DATABASE_URL"] = url
    cfg = _cfg(url)
    command.upgrade(cfg, "0063")
    engine = create_engine(url, future=True)
    ids: dict[str, object] = {}
    with Session(engine) as db:
        user = User(email="a@example.com", password_hash="x", role=UserRole.ADMIN, display_name="A")
        client = Client(legal_name="Acme")
        db.add_all([user, client])
        db.flush()
        svc = Service(client_id=client.id, kind=ServiceKind.NIST_CSF, title="t", opened_by=user.id)
        db.add(svc)
        db.flush()

        def assessment(st: CsfAssessmentStatus, version: int) -> CsfAssessment:
            a = CsfAssessment(service_id=svc.id, client_id=client.id, version=version, status=st)
            db.add(a)
            db.flush()
            db.add(
                CsfAnswer(
                    assessment_id=a.id,
                    client_id=client.id,
                    subcategory_code="GV.OC-01",
                    maturity_tier=3,
                )
            )
            db.add(
                CsfAnswer(
                    assessment_id=a.id,
                    client_id=client.id,
                    subcategory_code=RETIRED,
                    maturity_tier=2,
                    notes="personnel list",
                )
            )
            return a

        draft = assessment(CsfAssessmentStatus.DRAFT, 1)
        submitted = assessment(CsfAssessmentStatus.SUBMITTED, 2)
        approved = assessment(CsfAssessmentStatus.APPROVED, 3)
        released = assessment(CsfAssessmentStatus.RELEASED, 4)
        gone = assessment(CsfAssessmentStatus.DISCARDED, 5)
        # Already holds RC.CO-04, answered: never duplicated, never overwritten.
        db.add(
            CsfAnswer(
                assessment_id=released.id,
                client_id=client.id,
                subcategory_code=NEW,
                maturity_tier=3,
                notes="already answered",
            )
        )
        # The draft seeded two tiers of its Working Profile; `low` was never seeded.
        for tier in ("high", "moderate"):
            db.add(
                CsfDimensionScore(
                    assessment_id=draft.id,
                    client_id=client.id,
                    tier=tier,
                    subcategory_code="GV.OC-01",
                )
            )
        db.add(
            CsfDimensionScore(
                assessment_id=draft.id,
                client_id=client.id,
                tier="high",
                subcategory_code=RETIRED,
                governance=2,
                answer_source="consultant",
            )
        )
        # A discarded assessment's seeded tier gets nothing.
        db.add(
            CsfDimensionScore(
                assessment_id=gone.id, client_id=client.id, tier="high", subcategory_code="GV.OC-01"
            )
        )
        register = RiskRegister(client_id=client.id)
        db.add(register)
        db.flush()
        db.add(
            RiskEntry(
                register_id=register.id,
                client_id=client.id,
                title="t",
                source="questionnaire_response",
                source_id=RETIRED,
                linked_controls=["GV.OC-01", RETIRED],
            )
        )
        db.commit()
        ids.update(
            draft=draft.id,
            submitted=submitted.id,
            approved=approved.id,
            released=released.id,
            gone=gone.id,
        )
    yield cfg, engine, ids


def _answers(engine, assessment_id) -> dict[str, tuple]:
    from app.models.csf_assessment import CsfAnswer

    with Session(engine) as db:
        rows = db.execute(select(CsfAnswer).where(CsfAnswer.assessment_id == assessment_id))
        return {r.subcategory_code: (r.maturity_tier, r.notes) for r in rows.scalars()}


def _profile(engine, assessment_id) -> dict[tuple[str, str], tuple]:
    from app.models.csf_profile import CsfDimensionScore

    with Session(engine) as db:
        rows = db.execute(
            select(CsfDimensionScore).where(CsfDimensionScore.assessment_id == assessment_id)
        ).scalars()
        return {
            (r.tier, r.subcategory_code): (
                r.governance,
                r.policy,
                r.implementation,
                r.monitoring,
                r.improvement,
                r.in_scope,
                r.has_evidence,
                r.locked,
                r.target_level,
                r.answer_source,
            )
            for r in rows
        }


def _risk(engine) -> list[tuple]:
    from app.models.risk_register import RiskEntry

    with Session(engine) as db:
        return [(e.source_id, e.linked_controls) for e in db.execute(select(RiskEntry)).scalars()]


SEED_DEFAULT = (0, 0, 0, 0, 0, True, False, False, None, None)


def test_upgrade_inserts_rc_co_04_and_keeps_everything(world) -> None:
    cfg, engine, ids = world
    command.upgrade(cfg, "0064")
    for key in ("draft", "submitted", "approved"):
        rows = _answers(engine, ids[key])
        assert rows[NEW] == (None, None), key  # inserted, empty
        assert rows[RETIRED] == (2, "personnel list"), key  # kept, untouched
        assert rows["GV.OC-01"] == (3, None), key
    released = _answers(engine, ids["released"])
    assert released[NEW] == (3, "already answered")
    assert released[RETIRED] == (2, "personnel list")
    gone = _answers(engine, ids["gone"])
    assert NEW not in gone
    assert gone[RETIRED] == (2, "personnel list")

    profile = _profile(engine, ids["draft"])
    assert profile[("high", NEW)] == SEED_DEFAULT
    assert profile[("moderate", NEW)] == SEED_DEFAULT
    assert ("low", NEW) not in profile  # a tier never seeded gets nothing
    assert profile[("high", RETIRED)][0] == 2  # kept, untouched
    assert profile[("high", RETIRED)][9] == "consultant"
    assert _profile(engine, ids["submitted"]) == {}
    assert ("high", NEW) not in _profile(engine, ids["gone"])

    assert _risk(engine) == [(RETIRED, ["GV.OC-01", RETIRED])]


def test_upgrade_twice_adds_nothing_more(world) -> None:
    cfg, engine, ids = world
    command.upgrade(cfg, "0064")
    first = (_answers(engine, ids["draft"]), _profile(engine, ids["draft"]))
    command.downgrade(cfg, "0063")
    command.upgrade(cfg, "0064")
    assert (_answers(engine, ids["draft"]), _profile(engine, ids["draft"])) == first


def test_downgrade_deletes_only_rows_that_are_still_empty(world) -> None:
    from app.models.csf_assessment import CsfAnswer
    from app.models.csf_profile import CsfDimensionScore

    cfg, engine, ids = world
    command.upgrade(cfg, "0064")
    with Session(engine) as db:  # someone answers the draft's new rows
        ans = db.execute(
            select(CsfAnswer).where(
                CsfAnswer.assessment_id == ids["draft"], CsfAnswer.subcategory_code == NEW
            )
        ).scalar_one()
        ans.maturity_tier = 2
        dim = db.execute(
            select(CsfDimensionScore).where(
                CsfDimensionScore.assessment_id == ids["draft"],
                CsfDimensionScore.tier == "high",
                CsfDimensionScore.subcategory_code == NEW,
            )
        ).scalar_one()
        dim.governance = 1
        dim.answer_source = "consultant"
        db.commit()
    command.downgrade(cfg, "0063")

    draft = _answers(engine, ids["draft"])
    assert draft[NEW] == (2, None)  # answered: never deleted
    assert draft[RETIRED] == (2, "personnel list")
    profile = _profile(engine, ids["draft"])
    assert profile[("high", NEW)][0] == 1  # scored: never deleted
    assert ("moderate", NEW) not in profile  # inserted and empty: removed
    assert profile[("high", RETIRED)][0] == 2
    assert NEW not in _answers(engine, ids["approved"])  # inserted and empty: removed
    assert _answers(engine, ids["released"])[NEW] == (3, "already answered")  # pre-existing
    assert _risk(engine) == [(RETIRED, ["GV.OC-01", RETIRED])]
