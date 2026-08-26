r"""The separator-class gate must catch both real instances, and be able to fail.

Written with the gate, per the CLAUDE.md rule about shipping a checker without
one. Both historical defects are regression cells: D-058's `[ \t\xa0]` and item
10's `_PHONE_SEP = [ .\-]`.
"""

from __future__ import annotations

import pytest
from scripts.check_separator_classes import check, main

B = chr(92)


@pytest.mark.unit
def test_the_two_real_instances_are_caught() -> None:
    for src in (
        '_PHONE_SEP = r"[ .' + B + '-]"',
        '_STREET_SEP = r"[ ' + B + "t" + B + 'xa0]"',
        '_SUITE_SEP = r"[ ' + B + "t#" + B + "xa0" + B + '-]"',
    ):
        code, findings = check(src)
        assert code == 1, f"missed: {src}"
        assert findings


@pytest.mark.unit
@pytest.mark.parametrize(
    "src",
    [
        pytest.param('_SEP = r"(?:" + _HSPACE + r"|[.-])"', id="composed from _HSPACE"),
        pytest.param('_CAGE = r"[' + B + 's:#.,-]"', id="uses backslash-s"),
        pytest.param('_TAIL = r"[A-Za-z0-9' + B + '-]"', id="no space in class"),
        pytest.param('MODES = ["strict", "standard", "off"]', id="python list literal"),
        pytest.param("def f() -> tuple[str, int]: ...", id="type annotation"),
        pytest.param("xs = [h for h in hints if h]", id="comprehension"),
        pytest.param('_X = r"[ .-]"  # separator-class: ASCII on purpose, see #NNN', id="marked"),
    ],
)
def test_legitimate_shapes_pass(src: str) -> None:
    code, findings = check(src)
    assert code == 0, f"false positive: {findings}"


@pytest.mark.unit
def test_python_syntax_is_not_scanned() -> None:
    """The first draft scanned every bracket expression and reported twelve
    findings on redact.py, all Python. Claimed 1:1, measured 1 in 13 -- the same
    error the rule itself is about, made while building the rule."""
    src = "\n".join(
        [
            'MODES = ["strict", "standard", "off"]',
            "def g(a: tuple[str, int]) -> dict[str, int]: ...",
            "ys = [n for n in xs if n > 2]",
        ]
    )
    assert check(src)[0] == 0


@pytest.mark.unit
def test_an_empty_marker_is_not_a_reason() -> None:
    code, _ = check('_X = r"[ .-]"  # separator-class:')
    assert code == 1, "an empty exemption marker was accepted as a reason"


@pytest.mark.unit
def test_the_live_redactor_is_clean() -> None:
    """The gate runs against the real file in CI; this is the same assertion."""
    from pathlib import Path

    target = Path(__file__).resolve().parents[2] / "app" / "ai" / "redact.py"
    assert main(["check_separator_classes", str(target)]) == 0


@pytest.mark.unit
def test_a_missing_file_fails_closed_with_2(tmp_path) -> None:
    assert main(["check_separator_classes", str(tmp_path / "nope.py")]) == 2


@pytest.mark.unit
def test_an_empty_file_fails_closed_with_2(tmp_path) -> None:
    target = tmp_path / "empty.py"
    target.write_text("", encoding="utf-8")
    assert main(["check_separator_classes", str(target)]) == 2


@pytest.mark.unit
def test_main_returns_1_on_a_real_finding(tmp_path) -> None:
    """The exit code that makes this a gate at all."""
    target = tmp_path / "bad.py"
    target.write_text('_PHONE_SEP = r"[ .' + B + '-]"' + chr(10), encoding="utf-8")
    assert main(["check_separator_classes", str(target)]) == 1


@pytest.mark.unit
def test_main_returns_2_when_the_file_cannot_be_tokenized() -> None:
    """The "I could not look" branch must not report as a violation.

    `check()` has always returned 2 for a tokenize failure; `main()` never read
    it, so the code fell through to the findings print and exited **1**. The
    docstring promised an exit code that was unreachable -- a gate citing D-051
    while failing it. This pins the branch rather than the sentence.

    Distinct from the missing-file and empty-file cases already covered: those
    fail before `check()` is ever called, so they could never have caught this.
    """
    unterminated = '_PHONE_SEP = r"[ .-]' + chr(10)
    code, findings = check(unterminated)
    assert code == 2, "check() must report unreadable input as 2, not 0 or 1"
    assert findings, "an unreadable input must say why, not fail silently"


@pytest.mark.unit
def test_main_propagates_the_2_rather_than_collapsing_it_to_1(tmp_path) -> None:
    """The half that was actually broken: main() discarding check()'s 2."""
    target = tmp_path / "untokenizable.py"
    target.write_text('_PHONE_SEP = r"[ .-]' + chr(10), encoding="utf-8")

    result = main(["check_separator_classes", str(target)])
    assert result == 2, (
        f"main() returned {result} for input it could not parse; 1 means "
        "'violation found' and would send a reader hunting a defect that was "
        "never read, while 0 would be a silent pass"
    )


@pytest.mark.unit
def test_a_literal_space_beside_hspace_is_not_silently_excused() -> None:
    """The exemption was line-scoped, unbounded and SILENT.

    `if "_HSPACE" in line: continue` excused every character class on any line
    mentioning `_HSPACE` anywhere, so the exact form this gate exists to catch
    passed when written as a concatenation:

        _PHONE_SEP = r"(?:" + _HSPACE + r"|[ .-])"

    It cannot be fixed by testing adjacency -- the raw-string prefix sits
    between the two, so any proximity rule either admits unrelated classes or
    rejects the legitimate form. So the exemption is documented rather than
    silent, and this pins that it is no longer free.
    """
    src = (
        '_HSPACE = r"[^'
        + B
        + "S"
        + B
        + 'n]"'
        + chr(10)
        + '_PHONE_SEP = r"(?:" + _HSPACE + r"|[ .-])"'
        + chr(10)
    )
    code, findings = check(src)

    assert code == 1, "a literal-space class beside `_HSPACE` must not pass silently"
    assert any("_HSPACE" in f for f in findings), (
        "the finding must say WHY it fired, or the next reader deletes the space " "at random"
    )


@pytest.mark.unit
def test_the_hspace_exemption_can_still_be_taken_with_a_written_reason() -> None:
    """The other half: a documented exemption is still an exemption.

    Without this the fix above would be a one-way ratchet -- the gate would
    have no way to say yes, and the cheapest route to green would be deleting
    the check. Same shape as `check_test_integrity`'s markers.
    """
    src = (
        '_HSPACE = r"[^'
        + B
        + "S"
        + B
        + 'n]"'
        + chr(10)
        + '_PHONE_SEP = r"(?:" + _HSPACE + r"|[ .-])"'
        + "  # separator-class: redundant with _HSPACE, kept for readability"
        + chr(10)
    )

    assert check(src)[0] == 0
