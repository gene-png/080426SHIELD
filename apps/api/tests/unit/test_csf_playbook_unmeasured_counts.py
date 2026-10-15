"""#1031 / #1077, ruling 2 (#736 6128447366): a row whose only targets sit on
unscored tiers HAS a target that was not measured. It is counted apart from
"no target set", with its own line, approved verbatim, and "No gaps — every
in-scope subcategory meets its target." fires only when BOTH counts are 0.

Driven through the export helpers every renderer calls, over rows shaped as
`enterprise_subcategories` builds them (the route-level path is pinned in
`test_csf_rollup_freeze_and_kept.py`). Every expected string is written out.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.csf.playbook_export import (
    _function_summary,
    _next_steps,
    _no_gaps_sentence,
    _overview_sentences,
    _scorecard_gaps,
    _scorecard_target,
)

pytestmark = pytest.mark.unit

ONE = (
    "1 in-scope subcategory has a target only on tiers that were not scored, so it was "
    "not measured."
)
TWO = (
    "2 in-scope subcategories have a target only on tiers that were not scored, so it was "
    "not measured."
)
ALL_MET = "No gaps — every in-scope subcategory meets its target."


def _row(code: str, *, target: int | None, unmeasured: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        subcategory_code=code,
        name=code,
        function="GV",
        tier_levels={"high": 3},
        enterprise_level=3,
        rollup_rule=1,
        target_level=target,
        gap=False,
        priority=None,
        unscored_tiers=["moderate"] if unmeasured else [],
        target_not_measured=unmeasured,
    )


MET = _row("GV.OC-01", target=3)
NO_TARGET = _row("GV.OC-02", target=None)
UNMEASURED = _row("GV.OC-03", target=None, unmeasured=True)
UNMEASURED_2 = _row("GV.OC-04", target=None, unmeasured=True)


def test_no_gaps_fires_only_when_both_counts_are_zero() -> None:
    assert _no_gaps_sentence([MET]) == ALL_MET  # positive first
    with_unmeasured = _no_gaps_sentence([MET, UNMEASURED])
    assert with_unmeasured == f"No gaps among the 1 subcategory with a target. {ONE}"
    with_untargeted = _no_gaps_sentence([MET, NO_TARGET])
    assert with_untargeted == (
        "No gaps among the 1 subcategory with a target. 1 in-scope subcategory has no "
        "target set, so it is not assessed for gaps."
    )


def test_the_no_target_count_excludes_unmeasured_rows() -> None:
    both = _no_gaps_sentence([MET, NO_TARGET, UNMEASURED, UNMEASURED_2])
    assert both == (
        "No gaps among the 1 subcategory with a target. 1 in-scope subcategory has no "
        f"target set, so it is not assessed for gaps. {TWO}"
    )
    assert _no_gaps_sentence([UNMEASURED]) == ONE


def test_the_overview_states_the_unmeasured_count_singular_and_plural() -> None:
    one = _overview_sentences([MET, UNMEASURED], scored_only=True)
    assert ONE in one, one
    two = _overview_sentences([MET, UNMEASURED, UNMEASURED_2], scored_only=True)
    assert TWO in two, two
    assert not any("no target set" in line for line in two), two
    assert not any("not measured" in line for line in _overview_sentences([MET, NO_TARGET]))


def test_next_steps_name_the_unmeasured_rows() -> None:
    assert ONE in _next_steps([MET, UNMEASURED])


def test_the_scorecard_keeps_the_two_counts_apart() -> None:
    (only_unmeasured,) = _function_summary([UNMEASURED])
    assert (_scorecard_target(only_unmeasured), _scorecard_gaps(only_unmeasured)) == (
        "Not measured",
        "—",
    )
    (only_untargeted,) = _function_summary([NO_TARGET])
    assert (_scorecard_target(only_untargeted), _scorecard_gaps(only_untargeted)) == (
        "No target",
        "—",
    )
    (mixed,) = _function_summary([MET, NO_TARGET, UNMEASURED])
    assert (_scorecard_target(mixed), _scorecard_gaps(mixed)) == (
        "L3",
        "0 (1 no target, 1 not measured)",
    )
