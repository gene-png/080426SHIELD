"""The recalled-counts gate must be able to fail, and to say why.

Written late: this gate was wired into CI as a BLOCKING check with only the
generic crash case covering it, while every other gate in the repo ships a
behaviour test. That gap was found by the adversarial reviewer, not by the
author, and it is the reason these exist.

Expected values come from the documented convention -- 0 clean, 1 findings,
2 could not look -- and from prose written by hand here, never from the
module's own constants. Nothing below imports `_PATTERN`, `_CARDINALS` or
`_VOLATILE`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.check_recalled_counts import (
    ADVISORY_TARGETS,
    ENFORCED_TARGETS,
    check,
    main,
    root_from,
)


@pytest.mark.unit
def test_an_unprovenanced_spelled_count_is_flagged() -> None:
    findings = check("We closed nine blockers this week.\n")
    assert [(ln, phrase) for ln, phrase, _ in findings] == [(1, "nine blockers")]


@pytest.mark.unit
def test_digits_are_deliberately_not_flagged() -> None:
    """The fixed form the gate steers towards must not itself be a violation."""
    assert check("14 open, per the command below.\n") == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "marker",
    [
        "<!-- counted: historical -->",
        "<!-- counted: gh issue list --json number | jq length, 2026-08-26 -->",
        "<!-- counted: an illustration, not a tally -->",
    ],
)
def test_a_marker_with_a_reason_exempts(marker: str) -> None:
    assert check(f"We closed nine blockers this week. {marker}\n") == []


@pytest.mark.unit
def test_an_empty_marker_is_not_a_marker() -> None:
    """The claim the module docstring makes, pinned rather than asserted."""
    assert len(check("We closed nine blockers. <!-- counted: -->\n")) == 1


@pytest.mark.unit
@pytest.mark.parametrize("offset", [-2, -1, 0, 1, 2])
def test_the_provenance_window_reaches_two_lines_either_way(offset: int) -> None:
    lines = ["filler"] * 5
    lines[2] = "We closed nine blockers this week."
    lines[2 + offset] = lines[2 + offset] + " <!-- counted: historical -->"
    assert check("\n".join(lines)) == []


@pytest.mark.unit
def test_the_window_does_not_reach_three_lines() -> None:
    """A marker written too far away silently fails to exempt. It must not.

    This is the mechanic that made a three-line marker not register during the
    sweep: the closing delimiter fell outside the window.
    """
    lines = ["filler"] * 6
    lines[3] = "We closed nine blockers this week."
    lines[0] = "filler <!-- counted: historical -->"
    assert len(check("\n".join(lines))) == 1


@pytest.mark.unit
def test_a_count_split_across_a_line_break_is_missed() -> None:
    """A KNOWN limit, pinned so it is a decision rather than a surprise.

    Matching is per line, so prose reflow -- `prettier --write` is mandatory
    before every commit -- can move a cardinal onto the previous line and
    silently un-flag a count. Recorded in CLAUDE.md beside the other limits.
    If this test ever goes red, the gate got BETTER and the limit should be
    struck from that list.
    """
    assert check("We closed nine\nblockers this week.\n") == []


@pytest.mark.unit
def test_unreadable_input_exits_2_and_not_0(tmp_path: Path) -> None:
    """Fail-closed: 'I could not look' must not share a code with 'clean'."""
    assert main(["prog", "nope.md", "also-nope.md"], root=tmp_path) == 2


@pytest.mark.unit
def test_an_unknown_flag_exits_2_rather_than_silently_using_a_default_set() -> None:
    assert main(["prog", "--not-a-real-flag"]) == 2


@pytest.mark.unit
def test_the_two_target_sets_are_disjoint_and_advisory_holds_only_context() -> None:
    """The split CI depends on: bare invocation must never reach context/*.md."""
    assert set(ENFORCED_TARGETS).isdisjoint(ADVISORY_TARGETS)
    assert all(t.startswith("context/") for t in ADVISORY_TARGETS)
    assert not any(t.startswith("context/") for t in ENFORCED_TARGETS)


@pytest.mark.unit
def test_the_repo_root_rule_climbs_exactly_three_parents() -> None:
    assert root_from(Path("/w/apps/api/scripts/g.py")) == Path("/w")


@pytest.mark.unit
def test_too_short_a_path_raises_a_NAMED_error_rather_than_an_IndexError() -> None:
    """It must not silently pick a different root and then report clean.

    Inside the api container `/app` IS `apps/api`, so there is no fourth parent.
    That used to surface as a bare pathlib IndexError, which tells the reader
    nothing; the outcome (crash handler -> exit 2) was already right.
    """
    with pytest.raises(RuntimeError, match="cannot resolve the repo root"):
        root_from(Path("/app/scripts/g.py"))
