"""#801: the coverage figure AFTER planned changes, through R3's own computation.

The decision (this issue, #736): a tool marked for retirement in the latest
approved or released Tech Debt list does not count after planned changes; the
figure is R3 recomputed with those tools removed -- "if these tools are cut and
nothing else changes". The proposal on #801 sets the per-tool table this file
drives: a confirmed PLANNED tool is not in place, a confirmed tool whose
retirement is UNKNOWN is awaiting review (scored at the lower bound, as Q4), and
with no retirement input every figure is today's, unchanged.

The retirement verdicts are built here from plan entries with the module's own
`build_index`, the one fold every surface reads -- the WORLD, not the outcome.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.attack import computed
from app.attack.retirement import PlanEntry, build_index

pytestmark = pytest.mark.unit

#: A preventable technique with no sub-techniques (ATT&CK 19.2).
CODE = "T1003.001"
_DRAFT = SimpleNamespace(id="a", status_rules=None, parent_rules=None)

KEPT, CUT, ON_NO_PLAN = "Kept Tool", "Cut Tool", "Unlisted Tool"
INDEX = build_index([PlanEntry(KEPT, True, False), PlanEntry(CUT, True, True)], has_plan=True)


def _row(detect, prevent, respond, *, pending=()):
    return SimpleNamespace(
        technique_code=CODE,
        status="gap",
        reason_code=None,
        reviewed_status=None,
        detection_tools=list(detect),
        prevention_tools=list(prevent),
        response_tools=list(respond),
        unconfirmed_citations=[{"tool": t, "cleared_at": None} for t in pending],
    )


def _after(row):
    (eff,) = computed.effective_coverage(_DRAFT, [row], retirement=INDEX)
    return eff


def _today(row):
    (eff,) = computed.effective_coverage(_DRAFT, [row])
    return eff


@pytest.mark.parametrize(
    ("tool", "pending", "after"),
    [
        (KEPT, False, computed.InPlace.IN_PLACE),
        (CUT, False, computed.InPlace.NOT_IN_PLACE),
        (ON_NO_PLAN, False, computed.InPlace.AWAITING_REVIEW),
        (KEPT, True, computed.InPlace.AWAITING_REVIEW),
        (CUT, True, computed.InPlace.NOT_IN_PLACE),
    ],
    ids=["kept", "planned", "unknown", "kept-pending", "planned-pending"],
)
def test_each_tool_state_after_planned_changes(tool, pending, after) -> None:
    row = _row([tool], [KEPT], [KEPT], pending=[tool] if pending else [])
    assert _after(row).capabilities.detect is after


@pytest.mark.parametrize("tool", [KEPT, CUT, ON_NO_PLAN])
def test_today_ignores_retirement(tool) -> None:
    """No retirement input is today's figure, exactly as #808 shipped it."""
    assert _today(_row([tool], [KEPT], [KEPT])).capabilities.detect is (computed.InPlace.IN_PLACE)


def test_a_cut_removes_coverage_only_where_nothing_else_provides_it() -> None:
    both = _row([CUT, KEPT], [KEPT], [KEPT])
    only = _row([CUT], [KEPT], [KEPT])
    assert (_today(both).status, _after(both).status) == ("covered", "covered")
    assert (_today(only).status, _after(only).status) == ("covered", "partial")


def test_unknown_retirement_is_disclosed_by_the_awaiting_count() -> None:
    rows = computed.effective_coverage(
        _DRAFT, [_row([ON_NO_PLAN], [KEPT], [KEPT])], retirement=INDEX
    )
    assert computed.awaiting_review_count(rows) == 1
    assert rows[0].status == "partial"  # the lower bound: D not in place


def test_no_plan_changes_nothing() -> None:
    row = _row([CUT], [KEPT], [KEPT])
    no_plan = build_index([], has_plan=False)
    (eff,) = computed.effective_coverage(_DRAFT, [row], retirement=no_plan)
    assert eff.status == _today(row).status == "covered"


def test_an_assessment_approved_before_r3_has_no_after_figure() -> None:
    """Stored statuses: there is nothing to recount, so the rows come back as
    they are, whatever the plan says."""
    stored = SimpleNamespace(id="b", status_rules=1, parent_rules=1)
    row = _row([CUT], [CUT], [CUT])
    row.status = "covered"
    (eff,) = computed.effective_coverage(stored, [row], retirement=INDEX)
    assert eff is row
