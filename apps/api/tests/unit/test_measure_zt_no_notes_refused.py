"""#1084, for #1194: the consistency measure refuses what the run refuses.

A ZT capability with blank notes is never sent, and the run drops an entry
naming one as `no_notes` before reading its values. So the measure must treat
that entry as refused by its KEY, never as an answer two runs agree on. The
expected counts come from which row the test gives a note, not from a constant
of the module under test.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from tests.unit.test_measure_ai_consistency import _zt_assessment, world  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def test_an_entry_for_a_blank_notes_capability_is_refused_not_compared(
    world,  # noqa: F811
) -> None:
    """Two runs each answer a noted row and a blank row with `current: 2`.
    The noted row is an agreement; the blank row is refused in both runs.

    Red-on-revert: scope the measure by every row (`req.rows`) again, and the
    blank row counts as a second agreement."""
    from scripts.measure_ai_consistency import measure_zt

    from app.ai.llm import LLMClient, LLMResponse
    from app.models.zt_assessment import ZtAnswer

    c, TestSession, provider = world
    noted = _zt_assessment(c)
    with TestSession() as db:
        rows = db.execute(select(ZtAnswer).order_by(ZtAnswer.capability_code)).scalars().all()
        blank = next(r.capability_code for r in rows if r.capability_code != noted)
        next(r for r in rows if r.capability_code == noted).notes = "MFA everywhere."
        db.commit()
    provider.register_static(
        "zt_score",
        LLMResponse(
            '{"capabilities": [{"code": "'
            + noted
            + '", "current": 2}, {"code": "'
            + blank
            + '", "current": 2}]}'
        ),
    )

    with TestSession() as db:
        report = measure_zt(db, LLMClient(provider), framework="cisa", runs=2)
        db.commit()

    current = report["pairs"][0]["fields"]["current"]
    # The positive state first: the noted row is compared and agrees.
    assert (current["compared"], current["equal"]) == (2, 1), current
    assert current["both_absent"] == 1, current
