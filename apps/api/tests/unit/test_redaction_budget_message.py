"""The budget sentences with a FRACTIONAL limit, pinned at the function (#1143).

`test_redaction_places.py` quotes the part-way sentence at {N} = 5, the budget
its route test needs, so nothing there could tell `0.5` from `0` or `1`: a
formatting that rounded the limit would stay green. These pin both sentences at
0.5, each against the approved text QUOTED as it stood in the route tests
(#736 6094274195 for the neutral one; the part-way one drafted for #552), not
built from the code under test.
"""

from __future__ import annotations

import pytest

from app.ai.isolation import budget_message

#: Quoted from `test_redaction_budget.py` (`_NEUTRAL_BUDGET_COPY`).
_NEUTRAL_AT_HALF_A_SECOND = (
    "Checking this payload for people's names took longer than the 0.5-second "
    "limit, so the check was stopped and nothing was sent to the AI provider."
)

#: Quoted from `test_redaction_places.py` (`_BUDGET_PART_WAY`) as it read
#: before #1143 moved that test to a 5 s budget.
_PART_WAY_AT_HALF_A_SECOND = (
    "Checking a payload in this run for people's names took longer than the "
    "0.5-second limit, so the run was stopped part-way. Nothing from it was applied."
)


@pytest.mark.unit
def test_the_part_way_sentence_names_a_fractional_limit_exactly() -> None:
    assert budget_message(0.5, sent_before=True) == _PART_WAY_AT_HALF_A_SECOND


@pytest.mark.unit
def test_the_neutral_sentence_names_a_fractional_limit_exactly() -> None:
    assert budget_message(0.5, sent_before=False) == _NEUTRAL_AT_HALF_A_SECOND
