"""The issue-labels gate: every OPEN issue is on the board or says why not.

CLAUDE.md (the filing rule): every new issue carries `mvp-blocking` plus one of
`tier-1` / `tier-2` / `tier-3`, OR `unowned-with-reason` with the reason in the
body. An issue without `mvp-blocking` is not on the board; one with it and no
tier "has no place in the ordering". Nothing enforced that, so both happened.

The table below was written BEFORE the predicate, from the rule's text, so it
is a specification of the rule rather than a transcript of the code.
"""

from __future__ import annotations

import json

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py for why a
# bare `from scripts import ...` sorts differently in the container and in CI.
import scripts.check_issue_labels as gate

# (labels, expected) -- None means the issue satisfies the rule.
_TABLE = [
    # On the board, correctly.
    ({"mvp-blocking", "tier-1"}, None),
    ({"mvp-blocking", "tier-2", "client-reaching"}, None),
    ({"mvp-blocking", "tier-3", "not-client-reaching"}, None),
    # Deliberately off the board, with the reason on the issue.
    ({"unowned-with-reason"}, None),
    ({"unowned-with-reason", "tier-3", "post-mvp"}, None),
    # On the board with no place in the ordering.
    ({"mvp-blocking"}, "no_tier"),
    ({"mvp-blocking", "client-reaching"}, "no_tier"),
    # Two places in the ordering.
    ({"mvp-blocking", "tier-1", "tier-2"}, "several_tiers"),
    # Not on the board, and not saying why -- invisible to the only view used
    # to decide what to work on.
    (set(), "off_board"),
    ({"tier-3"}, "off_board"),
    ({"bug"}, "off_board"),
    # post-mvp is a state the rule does not name. Until it does, an issue that
    # carries it and nothing else is off the board without a stated reason.
    ({"tier-3", "post-mvp"}, "off_board"),
]


@pytest.mark.unit
@pytest.mark.parametrize(("labels", "expected"), _TABLE)
def test_classify_matches_the_filing_rule(labels: set[str], expected: str | None) -> None:
    assert gate.classify(labels) == expected


def _issue(number: int, *labels: str, pr: bool = False) -> dict:
    issue: dict = {"number": number, "title": f"t{number}", "labels": [{"name": n} for n in labels]}
    if pr:
        issue["pull_request"] = {"url": "x"}
    return issue


def _run(monkeypatch, capsys, pages: list[list[dict]] | Exception, repo: str | None = "o/r"):
    if repo is None:
        monkeypatch.delenv("REPO", raising=False)
    else:
        monkeypatch.setenv("REPO", repo)

    def fake_gh(*args: str) -> str:
        if isinstance(pages, Exception):
            raise pages
        # `gh api --paginate --slurp` returns one JSON array of pages.
        return json.dumps(pages)

    monkeypatch.setattr(gate, "_gh", fake_gh)
    code = gate.main()
    return code, capsys.readouterr()


@pytest.mark.unit
def test_a_clean_board_exits_zero_and_says_how_many_it_read(monkeypatch, capsys) -> None:
    code, out = _run(
        monkeypatch,
        capsys,
        [[_issue(1, "mvp-blocking", "tier-1"), _issue(2, "unowned-with-reason")]],
    )
    assert code == 0
    assert "2 open issue(s)" in out.out


@pytest.mark.unit
def test_a_violation_exits_one_and_names_the_issue_and_the_fault(monkeypatch, capsys) -> None:
    code, out = _run(
        monkeypatch, capsys, [[_issue(7, "mvp-blocking", "tier-1"), _issue(9, "mvp-blocking")]]
    )
    assert code == 1
    assert "#9" in out.out and "no tier" in out.out
    assert "#7" not in out.out


@pytest.mark.unit
def test_pull_requests_are_not_issues(monkeypatch, capsys) -> None:
    # The REST issues endpoint returns PRs too; a PR carries no board labels and
    # must not be reported as an invisible issue.
    code, out = _run(
        monkeypatch, capsys, [[_issue(1, "mvp-blocking", "tier-2"), _issue(2, pr=True)]]
    )
    assert code == 0
    assert "1 open issue(s)" in out.out


@pytest.mark.unit
def test_every_page_is_read(monkeypatch, capsys) -> None:
    # The sibling script caps its fetch at 100; an issue on page two must count.
    page1 = [_issue(n, "mvp-blocking", "tier-3") for n in range(1, 101)]
    page2 = [_issue(101)]
    code, out = _run(monkeypatch, capsys, [page1, page2])
    assert code == 1
    assert "#101" in out.out
    assert "101 open issue(s)" in out.out


@pytest.mark.unit
def test_could_not_look_is_exit_two_not_a_clean_board(monkeypatch, capsys) -> None:
    code, out = _run(monkeypatch, capsys, RuntimeError("gh api failed: HTTP 401"))
    assert code == 2
    assert "could not" in out.err.lower()


@pytest.mark.unit
def test_zero_issues_read_is_exit_two(monkeypatch, capsys) -> None:
    # This repo has open issues; reading none means the read failed, not that
    # the board is clean. "Nothing to complain about" and "I could not look"
    # must not share a branch.
    code, out = _run(monkeypatch, capsys, [[]])
    assert code == 2


@pytest.mark.unit
def test_no_repo_is_exit_two(monkeypatch, capsys) -> None:
    code, out = _run(monkeypatch, capsys, [[_issue(1, "mvp-blocking", "tier-1")]], repo=None)
    assert code == 2
