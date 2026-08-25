"""The plan-totals gate must fail closed, and be able to fail at all.

Written with the gate rather than after it, which is the difference CLAUDE.md
records between the fail-closed lesson working (`check_issue_references.py`,
whose test shipped in the first commit) and not working
(`check_no_control_chars.py`, which shipped without one and had two real defects
found by review).

Both real instances of the defect are pinned below as regression cells: the
"10.5-13.5 over 10-14.5" and "12-18.5 over 11.5-17.5" totals that this repo
actually produced.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.check_plan_totals import check, main

_GOOD = """
## Preamble that should be ignored

| not | a | totals table |
| --- | --- | --- |

### Total remaining: 11.5-17.5 sessions, and the parts sum to it

Prose in between.

| Item | Estimate |
| --- | --- |
| 10 - redaction boundary | 1.5-2.5 |
| 7 - W1 ATT&CK step | 1-1.5 |
| 9 - correctness defects | 4-6 |
| 6 - W1 Risk step | 4-6 |
| 8 - W6 export split | 1-1.5 |
| **Total** | **11.5-17.5** |

### A later section

| 99 - not counted | 100-200 |
"""


@pytest.mark.unit
def test_a_correct_table_passes() -> None:
    code, msgs = check(_GOOD)
    assert code == 0, msgs
    assert "11.5-17.5" in msgs[0]
    assert "5 items" in msgs[0]


@pytest.mark.unit
def test_rows_after_the_next_heading_are_not_counted() -> None:
    """The '99 - not counted | 100-200' row sits under a later '###'.

    Without the break this would pass anyway (the total would just be wrong),
    so the assertion is that the count is 5 -- deleting the break makes it 6.
    """
    code, msgs = check(_GOOD)
    assert code == 0 and "5 items" in msgs[0], msgs


@pytest.mark.unit
@pytest.mark.parametrize(
    ("label", "bad_total"),
    [
        # The two totals this repo actually produced, both by an author who had
        # just written the rule against them.
        ("the 12-18.5 instance", "12-18.5"),
        ("the 10.5-13.5 instance", "10.5-13.5"),
        ("low end only", "11-17.5"),
        ("high end only", "11.5-18"),
    ],
)
def test_a_total_that_does_not_sum_fails(label: str, bad_total: str) -> None:
    text = _GOOD.replace("| **Total** | **11.5-17.5** |", f"| **Total** | **{bad_total}** |")
    code, msgs = check(text)
    assert code == 1, f"{label}: not caught"
    assert any("sum to 11.5-17.5" in m for m in msgs), msgs


@pytest.mark.unit
def test_a_heading_that_disagrees_with_the_table_fails() -> None:
    """The total is written twice; drift between them is its own defect."""
    text = _GOOD.replace(
        "### Total remaining: 11.5-17.5 sessions", "### Total remaining: 12-18 sessions"
    )
    code, msgs = check(text)
    assert code == 1
    assert any("heading says" in m for m in msgs), msgs


@pytest.mark.unit
def test_an_en_dash_is_equivalent_to_a_hyphen() -> None:
    """prettier leaves en dashes in prose, so the parser must accept both."""
    text = _GOOD.replace("11.5-17.5", "11.5–17.5").replace("4-6", "4–6")
    code, msgs = check(text)
    assert code == 0, msgs


@pytest.mark.unit
def test_a_single_number_estimate_is_accepted() -> None:
    """An item sized "1" rather than "1-1.5" counts as 1-1.

    Both the heading and the Total row have to move with it -- an earlier draft
    of this test changed only the table and the gate failed it for heading drift,
    which is the gate being right and the test being wrong.
    """
    text = (
        _GOOD.replace("| 8 - W6 export split | 1-1.5 |", "| 8 - W6 export split | 1 |")
        .replace("| **Total** | **11.5-17.5** |", "| **Total** | **11.5-17** |")
        .replace("### Total remaining: 11.5-17.5 sessions", "### Total remaining: 11.5-17 sessions")
    )
    code, msgs = check(text)
    assert code == 0, msgs


@pytest.mark.unit
def test_a_missing_heading_fails_closed_with_2() -> None:
    code, msgs = check("# A plan with no totals section\n\nnothing here\n")
    assert code == 2, msgs
    assert "no '### Total remaining' heading" in msgs[0]


@pytest.mark.unit
def test_a_heading_with_no_rows_fails_closed_with_2() -> None:
    code, msgs = check("### Total remaining: 5-10 sessions\n\nprose, no table\n")
    assert code == 2, msgs


@pytest.mark.unit
def test_rows_without_a_total_row_fail_closed_with_2() -> None:
    text = _GOOD.replace("| **Total** | **11.5-17.5** |", "")
    code, msgs = check(text)
    assert code == 2, msgs
    assert "no '| **Total** |' row" in msgs[0]


@pytest.mark.unit
def test_the_failure_report_lists_the_rows_it_counted() -> None:
    """A gate that says the sum is wrong without showing its working gets argued with."""
    text = _GOOD.replace("| **Total** | **11.5-17.5** |", "| **Total** | **99-99** |")
    code, msgs = check(text)
    assert code == 1
    joined = "\n".join(msgs)
    assert "Rows counted:" in joined
    assert "redaction boundary" in joined and "W1 Risk step" in joined


# ---------------------------------------------------------------------------
# main() -- the entry point CI actually runs.
# ---------------------------------------------------------------------------
#
# `tests/unit/test_audit_evidence_gate.py` records this exact gap as a defect it
# once had: "`main` -- including the exit-1 that makes this a gate at all -- had
# NO coverage: inverting `return 1` to `return 0` left the whole suite green
# while the gate passed on every PR." This file shipped with the same hole and
# the adversarial review found it. Testing `check()` alone verifies the helper
# and never the thing wired into `ci.yml`.


def _write(tmp_path: Path, text: str) -> Path:
    target = tmp_path / "DELIVERY_PLAN.md"
    target.write_text(text, encoding="utf-8")
    return target


@pytest.mark.unit
def test_main_returns_0_on_a_correct_plan(tmp_path: Path) -> None:
    assert main(["check_plan_totals", str(_write(tmp_path, _GOOD))]) == 0


@pytest.mark.unit
def test_main_returns_1_when_the_parts_do_not_sum(tmp_path: Path) -> None:
    """The exit code that makes this a gate at all.

    Inverting `return code` to `return 0` in main() passes every other test in
    this file; only this one goes red.
    """
    bad = _GOOD.replace("| **Total** | **11.5-17.5** |", "| **Total** | **12-18.5** |")
    assert main(["check_plan_totals", str(_write(tmp_path, bad))]) == 1


@pytest.mark.unit
def test_main_returns_2_on_an_unparseable_plan(tmp_path: Path) -> None:
    plan = "# no totals here\n"
    assert main(["check_plan_totals", str(_write(tmp_path, plan))]) == 2


@pytest.mark.unit
def test_main_returns_2_on_a_missing_file(tmp_path: Path) -> None:
    """Could-not-read is distinct from found-a-problem, and neither is a pass."""
    assert main(["check_plan_totals", str(tmp_path / "does-not-exist.md")]) == 2


@pytest.mark.unit
def test_main_prints_a_distinct_message_per_outcome(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A green sentence must not be reachable from a red or unreadable input."""
    main(["check_plan_totals", str(_write(tmp_path, _GOOD))])
    ok = capsys.readouterr().out
    bad = _GOOD.replace("| **Total** | **11.5-17.5** |", "| **Total** | **12-18.5** |")
    main(["check_plan_totals", str(_write(tmp_path, bad))])
    failed = capsys.readouterr().out
    main(["check_plan_totals", str(tmp_path / "nope.md")])
    unreadable = capsys.readouterr().out

    assert "plan totals:" in ok and "FAILED" not in ok
    assert "FAILED" in failed
    assert "cannot read" in unreadable
    assert len({ok, failed, unreadable}) == 3


@pytest.mark.unit
def test_a_row_whose_estimate_does_not_parse_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The silent-drop defect, found by review.

    DELIVERY_PLAN's own house style annotates estimates one table up
    ("**4-6 sessions** (re-sized ...)"), so this is a formatting choice away.
    Dropped silently, the sum covers fewer items than the table displays and the
    cheapest way to green is to change the Total to the short sum -- the gate
    steering the author into the very defect it exists to catch.
    """
    text = _GOOD.replace(
        "| **Total** | **11.5-17.5** |",
        "| 11 - live-AI regression | 2-3 (needs-David) |\n| **Total** | **11.5-17.5** |",
    )
    assert main(["check_plan_totals", str(_write(tmp_path, text))]) == 2
    out = capsys.readouterr().out
    assert "cannot parse" in out and "live-AI regression" in out
