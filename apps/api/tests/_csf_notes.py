"""Setup for tests whose CSF run must SEND rows to the model.

CSF Option 1 (D-113): `_csf_ai_request_for` leaves every subcategory whose
current answer has no notes out of the csf_score payload, in every mode. A test
world built before that change seeded a Working Profile and ran the AI with no
notes anywhere, so every row was sent; under the leave-out nothing is. These
helpers give the world's answers notes, so the rows the test is about are sent
again. They build the WORLD, never the outcome: the leave-out itself is pinned
by `tests/unit/test_csf_leave_out_before_egress.py`.

Direct SQL, not one PATCH per answer: a full catalog is over a hundred answers,
and the PATCH route is not what these tests are about.
"""

from __future__ import annotations

import os
import uuid

from sqlalchemy import create_engine, text

#: The notes every answer gets. Any non-blank text has notes (`has_notes`).
NOTE = "Recorded in the interview."


def _ids(value: str) -> dict[str, str]:
    """A UUID as SQLite stores it (32 hex digits) and as Postgres prints it."""
    return {"a": str(value), "b": uuid.UUID(str(value)).hex}


def note_every_answer(service_id: str, notes: str = NOTE) -> int:
    """Give every answer of every assessment of `service_id` notes. Returns
    how many answers it wrote, and refuses to write none: a world with no
    answers would leave the test sending nothing, silently."""
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    try:
        with engine.begin() as db:
            n = db.execute(
                text(
                    "UPDATE csf_answers SET notes = :notes WHERE assessment_id IN "
                    "(SELECT id FROM csf_assessments WHERE service_id IN (:a, :b))"
                ),
                {"notes": notes, **_ids(service_id)},
            ).rowcount
    finally:
        engine.dispose()
    assert n > 0, f"service {service_id} has no CSF answers to give notes"
    return n
