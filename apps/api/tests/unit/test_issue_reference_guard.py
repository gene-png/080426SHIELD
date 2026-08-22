"""The accidental-close guard: a mechanism, after documentation failed four times.

#101 has been closed by accident **three times**, and the fourth incident was
written by someone documenting the third. The history is the argument for this
file existing:

1. A W2 commit body said `Filed, not fixed: #NNN`. The parser reads
   `fixed: #NNN` and does not read the word "not".
2. PR #NNN, whose entire purpose was to document that, re-closed the issue by
   QUOTING the offending sentence with the live number in it. Quotation marks
   and code fences are not exempt.
3. CLAUDE.md then said to use a placeholder number in examples.
4. The PR description for the work that finished the issue said
   `Closing keywords deliberately omitted -- this repo has closed #NNN twice by
   accident`. That sentence contains `closed #NNN`, which is a valid match on
   its own. Written while explaining the trap, again.

Three rounds of "document it better" produced a fourth incident, and #72's own
lesson is that discipline against a known shape has failed nine recorded times.
So this is a check, not a rule.

**Every example in this file uses `#NNN`.** That is not a stylistic choice: a
digits-free placeholder cannot match GitHub's parser, and it cannot become a
live issue later. See `test_a_placeholder_without_digits_is_always_safe`.
"""

from __future__ import annotations

import pytest
from scripts.check_issue_references import (
    approved_numbers,
    find_closing_references,
    main,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "fixes #12",
        "Fixes #12",
        "FIXES #12",
        "fix #12",
        "fixed #12",
        "close #12",
        "closes #12",
        "closed #12",
        "resolve #12",
        "resolves #12",
        "resolved #12",
        "fixes: #12",
        "fixes:  #12",
        "fixes\n#12",
    ],
    ids=lambda t: t.replace("\n", "\\n"),
)
def test_every_form_github_accepts_is_caught(text: str) -> None:
    """The keyword set and separators GitHub actually matches.

    Case-insensitive, optional colon, arbitrary whitespace including a newline.
    Getting this narrower than GitHub's parser is the only way this check can
    fail open, so it is enumerated rather than sampled.
    """
    assert find_closing_references(text) == [12], text


@pytest.mark.unit
def test_the_exact_sentence_that_closed_it_the_third_time() -> None:
    """Regression, verbatim in shape.

    The number is a placeholder; the surrounding words are the ones that shipped.
    Note the sentence is a WARNING about the trap and is itself an instance.
    """
    body = (
        "Addresses #NNN (the flags had nowhere to live) and #NNN (nothing read them). "
        "Closing keywords deliberately omitted — this repo has closed #12 twice by accident."
    )
    assert find_closing_references(body) == [12]


@pytest.mark.unit
def test_the_first_two_incidents_too() -> None:
    assert find_closing_references("Filed, not fixed: #12") == [12]
    assert find_closing_references("does not fix #12") == [12]
    assert find_closing_references("partially fixes #12") == [12]
    assert find_closing_references("not resolved: #12") == [12]


@pytest.mark.unit
def test_quotes_code_fences_and_html_comments_are_NOT_exempt() -> None:
    """The lesson from incident 2, and the one that makes this check strict.

    GitHub parses raw text. A backtick, a blockquote or an HTML comment does not
    stop it, so none of them may stop this check either.

    HTML comments are deliberately scanned even though it is unconfirmed whether
    GitHub acts on a keyword inside one. Scanning them can only over-report; NOT
    scanning them fails open, and this whole file exists because the failure mode
    that matters is the silent one.
    """
    assert find_closing_references("> Filed, not fixed: #12") == [12]
    assert find_closing_references("`fixed: #12`") == [12]
    assert find_closing_references("```\nfixes #12\n```") == [12]
    assert find_closing_references("<!-- fixes #12 -->") == [12]


@pytest.mark.unit
def test_the_safe_phrasings_this_repo_asks_for_are_not_flagged() -> None:
    """`filed as`, `see`, `tracked in` — CLAUDE.md's prescribed alternatives.

    A check that flagged these would push people back to the phrasings that
    close issues, which is the opposite of the point.
    """
    for safe in (
        "filed as #12",
        "see #12",
        "tracked in #12",
        "Related: #12",
        "the #12 pattern",
        "Addresses #12",
        "part of #12",
        "#12 is still open",
    ):
        assert find_closing_references(safe) == [], safe


@pytest.mark.unit
def test_a_placeholder_without_digits_is_always_safe() -> None:
    """Why CLAUDE.md must say `#NNN` and not "pick a number that isn't real".

    GitHub's parser needs digits. `#NNN` cannot match it, cannot match this
    check, and cannot become live later — which a "fake" number absolutely can,
    because issue numbers only ever go up. `closes #500` written today in a repo
    whose newest issue is #112 is a live closing reference the day the repo
    reaches 500.
    """
    assert find_closing_references("closes #NNN") == []
    assert find_closing_references("fixes #N") == []
    # And the trap it replaces IS caught, so the advice is enforceable.
    assert find_closing_references("closes #500") == [500]


@pytest.mark.unit
def test_a_deliberate_close_is_allowed_when_declared() -> None:
    """The escape hatch, and why it is spelled without a keyword.

    CLAUDE.md permits a closing keyword on the PR that genuinely closes the
    issue. So the check is not a prohibition — it is a demand that the intent be
    stated. The declaration carries BARE numbers and no `#`, because a marker
    containing `close` next to `#12` would be an instance of the very bug.
    """
    body = "Closes #12 at last.\n\nAuto-close-approved: 12\n"
    assert find_closing_references(body) == [12]
    assert approved_numbers(body) == {12}


@pytest.mark.unit
def test_declaring_one_number_does_not_approve_another() -> None:
    body = "Closes #12 and closes #34.\n\nAuto-close-approved: 12\n"
    assert find_closing_references(body) == [12, 34]
    assert approved_numbers(body) == {12}


@pytest.mark.unit
def test_main_fails_on_an_undeclared_close(tmp_path) -> None:
    title = tmp_path / "t"
    body = tmp_path / "b"
    commits = tmp_path / "c"
    title.write_text("feat: a change", encoding="utf-8")
    body.write_text("this repo has closed #12 twice by accident", encoding="utf-8")
    commits.write_text("", encoding="utf-8")
    rc = main(["--title", str(title), "--body", str(body), "--commits", str(commits)])
    assert rc == 1


@pytest.mark.unit
def test_main_scans_the_title_and_the_commits_not_only_the_body(tmp_path) -> None:
    """All three, because GitHub parses all three.

    Incident 4 was the BODY while every previous rule targeted commit messages.
    A check that inherited that blind spot would have missed the incident that
    prompted it.
    """
    for field in ("title", "body", "commits"):
        title = tmp_path / f"{field}-t"
        body = tmp_path / f"{field}-b"
        commits = tmp_path / f"{field}-c"
        title.write_text("fixes #12" if field == "title" else "ok", encoding="utf-8")
        body.write_text("fixes #12" if field == "body" else "ok", encoding="utf-8")
        commits.write_text("fixes #12" if field == "commits" else "ok", encoding="utf-8")
        rc = main(["--title", str(title), "--body", str(body), "--commits", str(commits)])
        assert rc == 1, f"{field} was not scanned"


@pytest.mark.unit
def test_main_passes_a_clean_pr(tmp_path) -> None:
    title = tmp_path / "t"
    body = tmp_path / "b"
    commits = tmp_path / "c"
    title.write_text("feat(attack): withhold unconfirmed support", encoding="utf-8")
    body.write_text("Addresses #12 and #34. Tracked in #56.", encoding="utf-8")
    commits.write_text("see #12\n\nfiled as #34", encoding="utf-8")
    assert main(["--title", str(title), "--body", str(body), "--commits", str(commits)]) == 0


@pytest.mark.unit
def test_main_passes_a_declared_close(tmp_path) -> None:
    title = tmp_path / "t"
    body = tmp_path / "b"
    commits = tmp_path / "c"
    title.write_text("fix: closes #12", encoding="utf-8")
    body.write_text("Auto-close-approved: 12", encoding="utf-8")
    commits.write_text("", encoding="utf-8")
    assert main(["--title", str(title), "--body", str(body), "--commits", str(commits)]) == 0


@pytest.mark.unit
def test_main_refuses_when_an_input_file_is_missing(tmp_path) -> None:
    """FAIL CLOSED. The audit gate learned this the hard way: an empty input made
    it print a positive-sounding message and exit 0. A guard that goes green when
    it cannot read its input is worse than no guard."""
    body = tmp_path / "b"
    body.write_text("ok", encoding="utf-8")
    rc = main(
        [
            "--title",
            str(tmp_path / "does-not-exist"),
            "--body",
            str(body),
            "--commits",
            str(body),
        ]
    )
    assert rc == 2
