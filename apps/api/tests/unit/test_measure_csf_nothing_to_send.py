"""The CSF measurement refuses an assessment with nothing to send (#1203 review,
finding 2). The route leaves every subcategory without notes out and makes no
call when none is left (CSF Option 1, D-114). Before this guard,
`measure_csf` sent the empty payload whole (`_csf_batch_inputs`'s
`or [inputs]`) and paid for a call that asked for nothing, counting it as a
good run.

The world is `test_measure_ai_consistency.py`'s `csf_world` (every answer has
notes), with every answer's notes then blanked.
"""

from __future__ import annotations

import pytest
from scripts.measure_ai_consistency import Refused, measure_csf
from sqlalchemy import func, select

from app.ai.llm import LLMClient, LLMResponse
from tests._csf_notes import note_every_answer
from tests.unit.test_measure_ai_consistency import csf_world, world  # noqa: F401  (fixtures)

pytestmark = pytest.mark.unit


def _calls(TestSession) -> int:
    from app.models.llm_call import LLMCall

    with TestSession() as db:
        return db.execute(select(func.count()).select_from(LLMCall)).scalar_one()


def test_a_profile_with_no_notes_is_refused_before_any_call(csf_world) -> None:  # noqa: F811
    c, TestSession, provider, h, svc_id = csf_world
    asked: list[dict] = []
    provider.register(
        "csf_score", lambda payload: asked.append(payload) or LLMResponse('{"scores": []}')
    )
    note_every_answer(svc_id, notes="   ")  # blank: whitespace only
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_csf(db, LLMClient(provider), runs=1)
    assert exc.value.reason == "csf_nothing_to_send", exc.value
    assert asked == [], "a call was made for a payload with nothing to score"
    assert _calls(TestSession) == 0


def test_a_profile_with_notes_is_measured(csf_world) -> None:  # noqa: F811
    """Positive control: the same world with its notes is measured, so the
    refusal above is about the notes, not the world."""
    c, TestSession, provider, h, svc_id = csf_world
    asked: list[dict] = []
    provider.register(
        "csf_score", lambda payload: asked.append(payload) or LLMResponse('{"scores": []}')
    )
    with TestSession() as db:
        report = measure_csf(db, LLMClient(provider), runs=1)
    assert asked, "the measurement made no call"
    assert report["rows_sent"] > 0, report
