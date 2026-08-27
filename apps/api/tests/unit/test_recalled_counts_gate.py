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
    """The fixed form the gate steers towards must not itself be a violation.

    The fixture MUST carry a volatile noun. An earlier version read
    "14 open, per the command below." -- no volatile noun anywhere, so it
    returned [] whether or not digits were matched and the test could not
    fail. Verified by mutation: adding a digit alternative to the cardinals
    left this file green at 18/18, its size then. #72's pattern inside a file written
    because this gate shipped as a blocking check with no behaviour test.
    """
    assert check("14 open blockers, per the command below.\n") == []


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


@pytest.mark.unit
def test_one_missing_target_exits_2_rather_than_being_skipped(tmp_path: Path) -> None:
    """PARTIAL blindness, which is the likely failure, not total blindness.

    The old guard fired only when EVERY target was missing -- a case that cannot
    occur -- and stayed silent on one missing document. Removing a single
    enforced doc produced `clean (6 documents)` and exit 0 from a gate that had
    read five.
    """
    (tmp_path / "CLAUDE.md").write_text("nothing to see\n", encoding="utf-8")
    assert main(["prog"], root=tmp_path) == 2


@pytest.mark.unit
def test_the_clean_message_states_a_count_of_documents(tmp_path: Path, capsys) -> None:
    """Pins the message FORMAT. It cannot pin which value produced it.

    The gate now derives that number by counting reads rather than taking
    `len(targets)`, which is the honest form -- the old one was a count asserted
    rather than derived, in the success message of the gate built to catch
    exactly that.

    But this test cannot tell the two apart, and saying so is the point.
    Reverting `checked` to `len(targets)` leaves this file green, because the
    missing-target guard makes them provably EQUAL on every path that reaches
    this line: any target that cannot be read exits 2 before it. Verified by
    reverting; it stayed green.

    So the derived count is defence in depth against a future skip branch, not a
    behaviour a test can observe today. The behaviour that IS observable is
    pinned by the two missing-target cases, one above this and one below, and
    they go red on the OTHER revert -- the one restoring the `continue` for a
    missing target. Naming which revert matters: an earlier draft said they go
    red on "that revert", whose nearest antecedent was the `len(targets)`
    revert, under which nothing goes red at all. A false sentence inside the
    justification for keeping a test that cannot fail is the one place this
    repo can least afford one, and it survived until a reviewer read it.
    Written out because an unexplained non-discriminating test is
    indistinguishable from an oversight -- which this file already has one
    recorded instance of.
    """
    for name in ("a.md", "b.md"):
        (tmp_path / name).write_text("nothing to see\n", encoding="utf-8")

    assert main(["prog", "a.md", "b.md"], root=tmp_path) == 0
    assert "clean (2 documents)" in capsys.readouterr().out


@pytest.mark.unit
def test_a_partial_set_never_reports_a_clean_count(tmp_path: Path, capsys) -> None:
    """The discriminating half: three asked for, one present, no clean line."""
    (tmp_path / "a.md").write_text("nothing to see\n", encoding="utf-8")

    assert main(["prog", "a.md", "gone.md", "also-gone.md"], root=tmp_path) == 2
    captured = capsys.readouterr()
    assert (
        "check-recalled-counts: clean" not in captured.out
    ), f"reported clean over a set it did not read: {captured.out!r}"
    # stderr, deliberately: stdout is --porcelain's machine-readable stream,
    # and the baseline-regeneration command redirects it into a data file.
    assert "MISSING target gone.md" in captured.err
