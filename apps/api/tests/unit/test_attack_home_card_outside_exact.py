"""#1016: the client home card's note ("may be understated": a Covered or
Partial technique relies on a tool outside the client's security tool list)
fires for a row whose status does not depend on that tool.

Approved (advisor, #736 6216024281; narrowed in 6219475831): on an assessment
whose statuses are computed (R3), flag a row only when its status, recomputed
WITHOUT its outside tools -- R3's own computation, as #801's "after planned
changes" recounts without retiring tools -- falls to Gap, the one status the
total sums. A row that would fall only to Partial is outside the total either
way. Before R3 the stored status cannot be recomputed, so the flag stays as it
is.

World: #851's. EDR stays in the security tool list; LEGACY leaves it after
release (`confirm_not_security`). Expected values are written from the rows
the test builds, never from the module.
"""

from __future__ import annotations

import pytest

from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)
from tests.unit.test_attack_subset_after_release import (
    _approve_finalize,
    _release,
    _value_summary,
)
from tests.unit.test_attack_subset_drift import EDR, LEGACY, _codes, _with_storage, _world

pytestmark = pytest.mark.unit


def _row(w, code: str, detect: list[str], prevent: list[str], respond: list[str]) -> None:
    r = w.patch(
        code,
        {
            "status": "covered",
            "detection_tools": detect,
            "prevention_tools": prevent,
            "response_tools": respond,
        },
    )
    assert r.status_code == 200, r.text


def _flag_after_drift(app_parts, tmp_path, detect, prevent, respond):  # noqa: F811
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    code = _codes(w)[0]
    _row(w, code, detect, prevent, respond)
    (row,) = [t for t in w.get()["coverage"] if t["technique_code"] == code]
    assert row["computed_status"] == "covered", "setup: the row computes to Covered"
    _release(w, _approve_finalize(w))
    before = _value_summary(w)
    assert before["attack_covered_relies_on_outside_tool"] is False, before
    w.confirm_not_security(LEGACY)
    return _value_summary(w)["attack_covered_relies_on_outside_tool"]


def test_a_covered_row_that_stays_covered_without_the_outside_tool_does_not_raise_it(
    app_parts, tmp_path  # noqa: F811
) -> None:
    """EDR is in every list, so the row is Covered with or without LEGACY."""
    both = [EDR, LEGACY]
    assert _flag_after_drift(app_parts, tmp_path, both, both, both) is False


def test_a_covered_row_that_would_fall_only_to_partial_does_not_raise_it(
    app_parts, tmp_path  # noqa: F811
) -> None:
    """LEGACY is the only Respond tool: without it the row would be Partial,
    which the Gap-only total leaves out either way, so it is exact."""
    assert _flag_after_drift(app_parts, tmp_path, [EDR], [EDR], [LEGACY]) is False


def test_a_covered_row_that_would_fall_to_gap_without_the_outside_tool_raises_it(
    app_parts, tmp_path  # noqa: F811
) -> None:
    """LEGACY is the only tool: without it the row would be a Gap, which the
    total would count, so the total may be understated."""
    only = [LEGACY]
    assert _flag_after_drift(app_parts, tmp_path, only, only, only) is True
