"""Migration 0045: grandfather LOCKED assessments' citations (D-056).

Written as a stepwise migration test rather than a `head` smoke test, because
the thing under test is a DATA change and data written after `head` would never
meet the migration. The DB is brought to **0044**, rows are inserted in exactly
the state the defect describes, and only then does it step to 0045.

The defect: #102 withholds a `covered` status whose citations were never
resolved (`unconfirmed_citations IS NULL`), which is migration 0044's deliberate
fail-closed reading. 0044's affordability argument was "the cost is one Run-AI
on each of the existing drafts" -- but APPROVED assessments are not drafts, and
every write path refuses them: `run_ai` re-reads the parent status and 409s,
`patch_coverage` 409s, and `confirm-citations` 409s. A locked assessment was
therefore pinned at 0% coverage with no route out anywhere in the product.

The affordability check that WAS done verified zero RELEASED assessments. It
never asked about APPROVED, and on the dev database 14 approved assessments held
8,862 such rows.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Uuid, bindparam, create_engine, text


def _cfg(url: str) -> Config:
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _seed_assessment(engine, *, status: str) -> str:
    """One assessment in `status` with one NULL-citation `covered` row.

    Seeded through the **ORM**, not by hand-written INSERTs, and that is the
    point of this helper rather than a convenience.

    The first version wrote `INSERT INTO attack_assessments (... status) VALUES
    ('approved')` -- and passed over a migration that grandfathered zero rows in
    production, because `SAEnum(..., native_enum=False)` persists the member's
    NAME and the real column holds `'APPROVED'`. The fixture had supplied the
    precondition in exactly the shape the migration expected, so it agreed by
    construction and could never have gone red. CLAUDE.md records that shape:
    let the setup build only the WORLD, never the outcome.

    Going through the model means the stored representation comes from the same
    code path production uses. If SQLAlchemy's enum storage ever changes, these
    tests move with it instead of pinning a guess.
    """
    from sqlalchemy.orm import Session

    from app.models.attack_assessment import (
        AttackAssessment,
        AttackAssessmentStatus,
        AttackCoverage,
    )

    with Session(engine) as db:
        a = AttackAssessment(
            service_id=uuid.uuid4(),
            client_id=uuid.uuid4(),
            version=1,
            status=AttackAssessmentStatus(status),
        )
        db.add(a)
        db.flush()
        row = AttackCoverage(
            assessment_id=a.id,
            client_id=a.client_id,
            technique_code="T1003",
            status="covered",
        )
        db.add(row)
        db.commit()
        return row.id


def _citations(conn, coverage_id: uuid.UUID):
    """The RAW stored value, with the id bound through the same type the ORM used.

    `Mapped[uuid.UUID]` maps to SQLAlchemy's `Uuid`, which on SQLite stores
    32 hex chars with no dashes. Binding `str(id)` here silently matched nothing
    and every assertion died on `NoResultFound` rather than on its own message.
    """
    return conn.execute(
        text("SELECT unconfirmed_citations FROM attack_coverage WHERE id = :i").bindparams(
            bindparam("i", type_=Uuid)
        ),
        {"i": coverage_id},
    ).scalar_one()


@pytest.mark.unit
def test_backfill_frees_locked_assessments_and_leaves_drafts_alone(tmp_path) -> None:
    """The whole decision, in one table.

    APPROVED and RELEASED are grandfathered because nothing can reach them.
    DRAFT is NOT, because re-running AI reaches it and that is the work 0044
    said was owed -- grandfathering a draft would spend the fail-closed
    guarantee to save a click.

    DISCARDED is NOT either, and that is the least obvious of the four: it is
    equally unreachable, but it is a soft-deleted assessment nobody will read.
    Writing "these citations are confirmed" onto data no one will look at
    asserts something no human checked, to no benefit.
    """
    url = f"sqlite:///{tmp_path / 'shield-backfill.db'}"
    os.environ["DATABASE_URL"] = url
    cfg = _cfg(url)
    command.upgrade(cfg, "0044")

    engine = create_engine(url, future=True)
    approved = _seed_assessment(engine, status="approved")
    released = _seed_assessment(engine, status="released")
    draft = _seed_assessment(engine, status="draft")
    discarded = _seed_assessment(engine, status="discarded")

    # The state the defect describes: every row unreachable-and-withheld.
    with engine.connect() as conn:
        for cid in (approved, released, draft, discarded):
            assert _citations(conn, cid) is None

    command.upgrade(cfg, "0045")

    with engine.connect() as conn:
        assert _citations(conn, approved) == "[]", "an approved row was left stuck"
        assert _citations(conn, released) == "[]", "a released row was left stuck"
        assert _citations(conn, draft) is None, (
            "a DRAFT was grandfathered -- it is reachable by Run-AI, which is "
            "exactly the work migration 0044 said was owed"
        )
        assert (
            _citations(conn, discarded) is None
        ), "a soft-deleted assessment was asserted to be confirmed"


@pytest.mark.unit
def test_the_column_stores_the_enum_NAME_which_is_what_the_migration_matches(
    tmp_path,
) -> None:
    """The defect this file shipped once, pinned so it cannot come back.

    `SAEnum(AttackAssessmentStatus, native_enum=False)` persists the member's
    NAME. `AttackAssessmentStatus.APPROVED.value` is `'approved'`; the column
    holds `'APPROVED'`. Migration 0045 matched on the value and selected
    **zero** of 8,862 rows while reporting success.

    Asserted on the RAW column, and against a literal rather than against
    `.name` -- reading it back through the same enum that produced it would
    agree by construction, which is the failure one layer down.
    """
    url = f"sqlite:///{tmp_path / 'shield-enumcase.db'}"
    os.environ["DATABASE_URL"] = url
    cfg = _cfg(url)
    command.upgrade(cfg, "0044")

    engine = create_engine(url, future=True)
    coverage_id = _seed_assessment(engine, status="approved")

    with engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT a.status FROM attack_assessments a "
                "JOIN attack_coverage c ON c.assessment_id = a.id WHERE c.id = :i"
            ).bindparams(bindparam("i", type_=Uuid)),
            {"i": coverage_id},
        ).scalar_one()
    assert stored == "APPROVED", (
        f"the column stores {stored!r}. Migration 0045 matches "
        "`upper(status) IN ('APPROVED','RELEASED')` -- if this representation "
        "changed, that match needs to change with it"
    )


@pytest.mark.unit
def test_backfill_does_not_overwrite_a_row_that_was_already_resolved(tmp_path) -> None:
    """`IS NULL` only. A locked row that DOES carry an outstanding flag keeps it.

    This is the difference between grandfathering rows nobody ever checked and
    erasing a review queue. An approved assessment whose run left a real
    inference on record must keep it -- the flag is the disclosure, and blanket
    `SET unconfirmed_citations = '[]'` on locked rows would delete exactly the
    thing #101 exists to persist.
    """
    url = f"sqlite:///{tmp_path / 'shield-backfill2.db'}"
    os.environ["DATABASE_URL"] = url
    cfg = _cfg(url)
    command.upgrade(cfg, "0044")

    engine = create_engine(url, future=True)
    flagged = (
        '[{"tool": "Splunk Enterprise", "cited": "Splunk", "reason": "substring", '
        '"field": "detection_tools", "cleared_at": null}]'
    )
    kept = _seed_assessment(engine, status="approved")
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE attack_coverage SET unconfirmed_citations = :v WHERE id = :i").bindparams(
                bindparam("i", type_=Uuid)
            ),
            {"v": flagged, "i": kept},
        )

    command.upgrade(cfg, "0045")

    with engine.connect() as conn:
        assert _citations(conn, kept) == flagged, "the backfill erased a live review queue"


@pytest.mark.unit
def test_the_backfilled_value_is_what_the_scoring_rule_reads_as_confirmed(tmp_path) -> None:
    """Ties the migration to the rule it exists to satisfy.

    A backfill writing a value the predicate does not accept would be green here
    and useless in the product. Asserted through `is_pending_review` itself
    rather than by eyeballing `'[]'`, so the two cannot drift apart.
    """
    from app.attack.pending import is_pending_review

    url = f"sqlite:///{tmp_path / 'shield-backfill3.db'}"
    os.environ["DATABASE_URL"] = url
    cfg = _cfg(url)
    command.upgrade(cfg, "0044")

    engine = create_engine(url, future=True)
    approved = _seed_assessment(engine, status="approved")

    with engine.connect() as conn:
        before = _citations(conn, approved)
    assert (
        is_pending_review("covered", before, ["Splunk"]) is True
    ), "the fixture does not reproduce the stuck state"

    command.upgrade(cfg, "0045")

    import json

    with engine.connect() as conn:
        after = json.loads(_citations(conn, approved))
    assert (
        is_pending_review("covered", after, ["Splunk"]) is False
    ), "the backfilled value is not what the scoring rule reads as confirmed"
