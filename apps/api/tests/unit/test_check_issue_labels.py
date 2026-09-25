"""The issue-labels gate: every OPEN issue carries `mvp-blocking` plus exactly one
tier, or `unowned-with-reason`, or `post-mvp`.

CLAUDE.md (the filing rule): every new issue carries `mvp-blocking` plus one of
`tier-1` / `tier-2` / `tier-3`, OR `unowned-with-reason` with the reason in the
body, OR `post-mvp`. An issue without `mvp-blocking` is not on the board; one with it and no
tier "has no place in the ordering". Nothing enforced that, so both happened.
The gate checks LABELS only -- it does not read the body.

The table was written BEFORE the predicate, from the rule's text. The rows
mixing `unowned-with-reason` with `mvp-blocking` were added after review found
the first predicate let that pair skip the tier check, which is the one
combination the order of the `if`s decides.

The `post-mvp` rows changed on 2026-09-24, when the rule named `post-mvp` as a
third legitimate state (D-086). They were written as `off_board` from the
rule's text as it then stood, and they flip because the rule did.
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
    # Deliberately off the board.
    ({"unowned-with-reason"}, None),
    ({"unowned-with-reason", "tier-3", "post-mvp"}, None),
    # On the board with no place in the ordering.
    ({"mvp-blocking"}, "no_tier"),
    ({"mvp-blocking", "client-reaching"}, "no_tier"),
    # ...and `unowned-with-reason` does not excuse it: the board query still
    # returns the issue, so it still needs a place in the ordering.
    ({"mvp-blocking", "unowned-with-reason"}, "no_tier"),
    ({"mvp-blocking", "unowned-with-reason", "tier-1", "tier-2"}, "several_tiers"),
    ({"mvp-blocking", "unowned-with-reason", "tier-2"}, None),
    # Two places in the ordering.
    ({"mvp-blocking", "tier-1", "tier-2"}, "several_tiers"),
    # Not on the board, and not unowned -- invisible.
    (set(), "off_board"),
    ({"tier-3"}, "off_board"),
    ({"bug"}, "off_board"),
    # Deliberately deferred past the MVP: the third state (D-086). A tier is
    # allowed and not required -- the deferral is the decision.
    ({"post-mvp"}, None),
    ({"tier-3", "post-mvp"}, None),
    # ...and NOT together with `mvp-blocking`: "on the board" and "deferred
    # past it" contradict each other, whatever the tiers. Unlike
    # `unowned-with-reason` + `mvp-blocking` above, which is a coherent state
    # (a blocker nobody owns). The live instance this guards against is a
    # half-done move to `post-mvp` that forgot to remove `mvp-blocking`.
    ({"mvp-blocking", "post-mvp", "tier-3"}, "deferred_on_board"),
    ({"mvp-blocking", "post-mvp"}, "deferred_on_board"),
    ({"mvp-blocking", "post-mvp", "tier-2", "tier-3"}, "deferred_on_board"),
    # A label that merely CONTAINS the word is not the state.
    ({"not-post-mvp"}, "off_board"),
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


def _run(monkeypatch, capsys, pages, *args: str, repo: str | None = "o/r"):
    if repo is None:
        monkeypatch.delenv("REPO", raising=False)
    else:
        monkeypatch.setenv("REPO", repo)

    def fake_gh(*_gh_args: str) -> str:
        if isinstance(pages, Exception):
            raise pages
        return json.dumps(pages)  # `gh api --paginate --slurp`: a list of pages

    monkeypatch.setattr(gate, "_gh", fake_gh)
    code = gate.main(["check_issue_labels.py", *args])
    return code, capsys.readouterr().out


@pytest.mark.unit
def test_a_clean_board_exits_zero_and_says_how_many_it_read(monkeypatch, capsys) -> None:
    code, out = _run(
        monkeypatch,
        capsys,
        [[_issue(1, "mvp-blocking", "tier-1"), _issue(2, "unowned-with-reason")]],
    )
    assert code == 0
    assert "clean -- 2 open issue(s), each on the board, unowned-with-reason, or post-mvp" in out


@pytest.mark.unit
def test_a_violation_exits_one_and_names_the_issue_and_the_fault(monkeypatch, capsys) -> None:
    code, out = _run(
        monkeypatch, capsys, [[_issue(7, "mvp-blocking", "tier-1"), _issue(9, "mvp-blocking")]]
    )
    assert code == 1
    assert "#9: carries `mvp-blocking` but no tier" in out
    assert "#7" not in out


@pytest.mark.unit
def test_a_post_mvp_issue_is_clean_and_the_off_board_message_names_all_three_states(
    monkeypatch, capsys
) -> None:
    code, out = _run(monkeypatch, capsys, [[_issue(1, "post-mvp", "tier-3"), _issue(2, "tier-3")]])
    assert code == 1
    assert "#1" not in out
    assert (
        "#2: carries neither `mvp-blocking` + a tier, nor `unowned-with-reason`, "
        "nor `post-mvp`, so it is not on the board" in out
    )


@pytest.mark.unit
def test_a_deferred_issue_still_on_the_board_names_both_labels(monkeypatch, capsys) -> None:
    code, out = _run(monkeypatch, capsys, [[_issue(4, "mvp-blocking", "post-mvp", "tier-2")]])
    assert code == 1
    assert "#4: carries both `mvp-blocking` and `post-mvp`" in out


@pytest.mark.unit
def test_pull_requests_are_not_issues(monkeypatch, capsys) -> None:
    code, out = _run(
        monkeypatch, capsys, [[_issue(1, "mvp-blocking", "tier-2"), _issue(2, pr=True)]]
    )
    assert code == 0
    assert "clean -- 1 open issue(s)" in out


@pytest.mark.unit
def test_every_page_is_read(monkeypatch, capsys) -> None:
    # The sibling trigger script caps its fetch at 100; page two must count.
    page1 = [_issue(n, "mvp-blocking", "tier-3") for n in range(1, 101)]
    code, out = _run(monkeypatch, capsys, [page1, [_issue(101)]])
    assert code == 1
    assert "1 of 101 open issue(s)" in out
    assert "#101:" in out


@pytest.mark.unit
def test_a_gh_failure_is_could_not_look(monkeypatch, capsys) -> None:
    code, out = _run(monkeypatch, capsys, RuntimeError("gh api failed: HTTP 401"))
    assert code == 2
    assert "could not read the open issues: gh api failed: HTTP 401" in out


@pytest.mark.unit
def test_zero_issues_read_is_could_not_look(monkeypatch, capsys) -> None:
    code, out = _run(monkeypatch, capsys, [[]])
    assert code == 2
    assert "read ZERO open issues" in out


@pytest.mark.unit
def test_no_repo_and_no_file_is_could_not_look(monkeypatch, capsys) -> None:
    code, out = _run(monkeypatch, capsys, [[_issue(1, "mvp-blocking", "tier-1")]], repo=None)
    assert code == 2
    assert "REPO is not set and no --issues-file was given" in out


# --- EVENT mode: the triggering issue decides the result -------------------


@pytest.mark.unit
def test_event_mode_is_red_for_the_new_unlabelled_issue_alone(monkeypatch, capsys) -> None:
    # A standing backlog must not hide a newly filed issue: the full check is
    # red either way, so only the event's own issue can carry the signal.
    board = [[_issue(1, "mvp-blocking", "tier-1"), _issue(2), _issue(3)]]
    code, out = _run(monkeypatch, capsys, board, "--issue", "3")
    assert code == 1
    assert "issue #3 breaks the filing rule" in out
    assert "standing total, for information: 2 of 3" in out


@pytest.mark.unit
def test_event_mode_is_green_for_a_correct_issue_despite_a_backlog(monkeypatch, capsys) -> None:
    board = [[_issue(1, "mvp-blocking", "tier-1"), _issue(2), _issue(3)]]
    code, out = _run(monkeypatch, capsys, board, "--issue", "1")
    assert code == 0
    assert "issue #1 satisfies the filing rule" in out


@pytest.mark.unit
def test_event_mode_for_an_issue_it_did_not_read_is_could_not_look(monkeypatch, capsys) -> None:
    code, out = _run(monkeypatch, capsys, [[_issue(1, "mvp-blocking", "tier-1")]], "--issue", "99")
    assert code == 2
    assert "issue #99 is not among the 1 open issues read" in out


# --- the file input the fixture harness uses --------------------------------


@pytest.mark.unit
def test_issues_file_needs_no_repo_and_accepts_a_flat_list(tmp_path, monkeypatch, capsys) -> None:
    f = tmp_path / "issues.json"
    f.write_text(json.dumps([_issue(1, "mvp-blocking", "tier-2")]), encoding="utf-8")
    code, out = _run(
        monkeypatch, capsys, RuntimeError("must not call gh"), "--issues-file", str(f), repo=None
    )
    assert code == 0
    assert "clean -- 1 open issue(s)" in out


@pytest.mark.unit
def test_an_unreadable_issues_file_is_could_not_look(tmp_path, monkeypatch, capsys) -> None:
    code, out = _run(
        monkeypatch, capsys, [[]], "--issues-file", str(tmp_path / "absent.json"), repo=None
    )
    assert code == 2
    assert "could not read the open issues" in out


@pytest.mark.unit
def test_an_unknown_argument_is_could_not_look_not_a_clean_run(monkeypatch, capsys) -> None:
    code, out = _run(monkeypatch, capsys, [[_issue(1, "mvp-blocking", "tier-1")]], "--isue", "1")
    assert code == 2
    assert "bad argument, nothing was read: unknown or incomplete argument: '--isue'" in out


@pytest.mark.unit
@pytest.mark.parametrize("value", ["abc", "#123"])
def test_a_non_integer_issue_is_a_bad_argument_not_a_failed_read(
    monkeypatch, capsys, value: str
) -> None:
    code, out = _run(monkeypatch, capsys, [[_issue(1, "mvp-blocking", "tier-1")]], "--issue", value)
    assert code == 2
    assert "bad argument, nothing was read" in out
    assert "could not read the open issues" not in out


@pytest.mark.unit
def test_issue_with_no_value_is_a_bad_argument(monkeypatch, capsys) -> None:
    code, out = _run(monkeypatch, capsys, [[_issue(1, "mvp-blocking", "tier-1")]], "--issue")
    assert code == 2
    assert "bad argument, nothing was read: unknown or incomplete argument: '--issue'" in out
