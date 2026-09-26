"""Resolving a merge-queue entry back to its pull request, for the body checks.

On a `merge_group` event there is no `github.event.pull_request`: the two
required body checks ("Adversarial audit recorded", "No accidental issue
closes") would read an empty body. The queue names the PR only in its ref,
`gh-readonly-queue/main/pr-<N>-<sha>`, so the workflow parses N and fetches PR
N's CURRENT body. It never reuses the earlier pull_request pass, because the body
can be edited after that pass and before the queue merges it.

The table of refs was written from the documented ref shape before the parser.
A ref the parser cannot read, and a fetch that fails, must each exit 2 -- red,
"could not look" (D-090) -- and must leave no body file behind for a later step
to read as if it were current.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py for why a
# bare `from scripts import ...` sorts differently in the container and in CI.
import scripts.merge_group_pr as resolver

_SHA = "0123456789abcdef0123456789abcdef01234567"
_REPO = "owner/repo"

_PR = {
    "number": 42,
    "title": "A queued change",
    "body": "## Adversarial audit\nFindings: none found\nDisposition: nothing to act on\n",
    "user": {"login": "someone"},
    "base": {"ref": "main"},
}


# --- parsing the queue ref ---------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("ref", "number"),
    [
        (f"refs/heads/gh-readonly-queue/main/pr-42-{_SHA}", 42),
        (f"gh-readonly-queue/main/pr-42-{_SHA}", 42),
        (f"refs/heads/gh-readonly-queue/main/pr-7-{_SHA}", 7),
        (f"refs/heads/gh-readonly-queue/main/pr-1234-{_SHA}", 1234),
    ],
)
def test_a_queue_ref_names_its_pr(ref: str, number: int) -> None:
    assert resolver.parse_pr_number(ref) == number


@pytest.mark.unit
@pytest.mark.parametrize(
    "ref",
    [
        "",
        "refs/heads/main",
        f"refs/heads/gh-readonly-queue/main/pr--{_SHA}",
        f"refs/heads/gh-readonly-queue/main/pr-abc-{_SHA}",
        f"refs/heads/gh-readonly-queue/main/pr-0-{_SHA}",
        f"refs/heads/gh-readonly-queue/main/pr-042-{_SHA}",
        "refs/heads/gh-readonly-queue/main/pr-42",
        "refs/heads/gh-readonly-queue/main/pr-42-",
        "refs/heads/gh-readonly-queue/main/pr-42-nothex",
        f"refs/heads/gh-readonly-queue/main/pr-42-{_SHA[:39]}",
        f"refs/heads/gh-readonly-queue/main/pr-42-{_SHA}0",
        f"refs/heads/gh-readonly-queue/release/pr-42-{_SHA}",
        f"refs/heads/gh-readonly-queue/main/pr-42-{_SHA}/extra",
        f"refs/heads/x/gh-readonly-queue/main/pr-42-{_SHA}",
        f"refs/heads/gh-readonly-queue/main/pr-42-{_SHA}\n",
        f" refs/heads/gh-readonly-queue/main/pr-42-{_SHA}",
    ],
)
def test_an_unreadable_queue_ref_is_refused(ref: str) -> None:
    with pytest.raises(resolver.UnreadableRef):
        resolver.parse_pr_number(ref)


# --- the command, end to end with `gh` replaced ------------------------------


def _fake_gh(pr: dict, *, fail_on: str | None = None):
    """Answer the `gh` calls the resolver makes from one PR's data. The PR
    number is read back from the argv, so a resolver that fetched the WRONG PR
    gets a different body and the test can see it."""

    calls: list[tuple[str, ...]] = []

    def gh(*args: str) -> str:
        calls.append(args)
        joined = " ".join(args)
        if fail_on is not None and fail_on in joined:
            raise RuntimeError(f"gh {joined} failed: HTTP 502")
        if args[0] == "pr" and args[1] == "view":
            return "17\n"
        path = args[-1]
        number = int(path.split("/pulls/")[1].split("/")[0].split("?")[0])
        this = {**pr, "number": number, "body": f"{pr['body']}(pr {number})"}
        if "/files" in path:
            return json.dumps([[{"filename": "apps/api/app/x.py"}, {"filename": "README.md"}]])
        if "/commits" in path:
            return json.dumps(
                [[{"commit": {"message": "first\n\nbody"}}, {"commit": {"message": "second"}}]]
            )
        if "application/vnd.github.diff" in joined:
            return "diff --git a/x b/x\n"
        return json.dumps(this)

    return gh, calls


def _argv(tmp_path: Path, ref: str) -> tuple[list[str], dict[str, Path]]:
    outs = {
        name: tmp_path / f"{name}.txt"
        for name in ("title", "body", "author", "files", "commits", "linked", "diff")
    }
    argv = ["merge_group_pr.py", "--head-ref", ref, "--repo", _REPO]
    for name, path in outs.items():
        argv += [f"--{name}-out", str(path)]
    return argv, outs


@pytest.mark.unit
def test_a_valid_ref_writes_that_prs_current_body(tmp_path: Path, monkeypatch) -> None:
    gh, calls = _fake_gh(_PR)
    monkeypatch.setattr(resolver, "_gh", gh)
    argv, outs = _argv(tmp_path, f"refs/heads/gh-readonly-queue/main/pr-42-{_SHA}")

    assert resolver.main(argv) == 0

    assert outs["body"].read_text(encoding="utf-8") == f"{_PR['body']}(pr 42)"
    assert outs["title"].read_text(encoding="utf-8") == "A queued change"
    assert outs["author"].read_text(encoding="utf-8") == "someone"
    assert outs["files"].read_text(encoding="utf-8") == "apps/api/app/x.py\nREADME.md\n"
    assert outs["commits"].read_text(encoding="utf-8") == "first\n\nbody\n\nsecond\n"
    assert outs["linked"].read_text(encoding="utf-8") == "17\n"
    assert outs["diff"].read_text(encoding="utf-8") == "diff --git a/x b/x\n"
    fetched = {a[-1] for a in calls if a[0] == "api"}
    assert f"repos/{_REPO}/pulls/42" in fetched, calls


@pytest.mark.unit
def test_a_pr_with_no_description_writes_an_empty_body(tmp_path: Path, monkeypatch) -> None:
    """The API sends `null` for an empty description. The pull_request path
    writes "" for it, so the queue path must too -- not the string "None"."""
    gh, _ = _fake_gh({**_PR, "body": ""})

    def null_body(*args: str) -> str:
        out = gh(*args)
        if args == ("api", f"repos/{_REPO}/pulls/42"):
            return json.dumps({**json.loads(out), "body": None})
        return out

    monkeypatch.setattr(resolver, "_gh", null_body)
    argv, outs = _argv(tmp_path, f"refs/heads/gh-readonly-queue/main/pr-42-{_SHA}")

    assert resolver.main(argv) == 0
    assert outs["body"].read_text(encoding="utf-8") == ""


@pytest.mark.unit
@pytest.mark.parametrize(
    "ref",
    [
        "",
        "refs/heads/main",
        f"refs/heads/gh-readonly-queue/main/pr-abc-{_SHA}",
        "refs/heads/gh-readonly-queue/main/pr-42",
    ],
)
def test_an_unreadable_ref_exits_2_and_fetches_nothing(
    tmp_path: Path, monkeypatch, ref: str
) -> None:
    gh, calls = _fake_gh(_PR)
    monkeypatch.setattr(resolver, "_gh", gh)
    argv, outs = _argv(tmp_path, ref)

    assert resolver.main(argv) == 2
    assert calls == [], "a ref it could not read still reached GitHub"
    assert not any(p.exists() for p in outs.values())


@pytest.mark.unit
@pytest.mark.parametrize(
    "fail_on",
    [
        # The PR itself: every call names it, so the FIRST call fails.
        "pulls/42",
        "pulls/42/files",
        "pulls/42/commits",
        "pr view",
        "vnd.github.diff",
    ],
)
def test_a_failed_fetch_exits_2_and_leaves_no_body(
    tmp_path: Path, monkeypatch, fail_on: str
) -> None:
    """Any one fetch failing leaves NO output at all -- including a body file an
    earlier step or an earlier run wrote, which a later check step would
    otherwise read as the current body."""
    gh, _ = _fake_gh(_PR, fail_on=fail_on)
    monkeypatch.setattr(resolver, "_gh", gh)
    argv, outs = _argv(tmp_path, f"refs/heads/gh-readonly-queue/main/pr-42-{_SHA}")
    for path in outs.values():
        path.write_text("STALE from an earlier step\n", encoding="utf-8")

    assert resolver.main(argv) == 2
    left = [p.name for p in outs.values() if p.exists()]
    assert left == [], f"stale outputs survived a failed fetch: {left}"


@pytest.mark.unit
def test_a_fetched_pr_that_is_not_the_named_one_exits_2(tmp_path: Path, monkeypatch) -> None:
    """If the API answered with a different PR than the ref names, the body is
    somebody else's. Refuse rather than check the wrong description."""
    gh, _ = _fake_gh(_PR)

    def wrong_pr(*args: str) -> str:
        out = gh(*args)
        if args == ("api", f"repos/{_REPO}/pulls/42"):
            return json.dumps({**json.loads(out), "number": 43})
        return out

    monkeypatch.setattr(resolver, "_gh", wrong_pr)
    argv, outs = _argv(tmp_path, f"refs/heads/gh-readonly-queue/main/pr-42-{_SHA}")

    assert resolver.main(argv) == 2
    assert not outs["body"].exists()


@pytest.mark.unit
@pytest.mark.parametrize(
    "argv",
    [
        ["merge_group_pr.py"],
        ["merge_group_pr.py", "--head-ref", f"gh-readonly-queue/main/pr-42-{_SHA}"],
        ["merge_group_pr.py", "--repo", _REPO, "--body-out", "x"],
        [
            "merge_group_pr.py",
            "--head-ref",
            f"gh-readonly-queue/main/pr-42-{_SHA}",
            "--repo",
            _REPO,
        ],
        [
            "merge_group_pr.py",
            "--head-ref",
            f"gh-readonly-queue/main/pr-42-{_SHA}",
            "--repo",
            _REPO,
            "--bogus-out",
            "x",
        ],
    ],
)
def test_incomplete_or_unknown_arguments_exit_2(monkeypatch, argv: list[str]) -> None:
    """No ref, no repo, nothing asked for, or a flag it does not implement:
    each is "could not look", never a clean run that wrote nothing (#343)."""
    gh, calls = _fake_gh(_PR)
    monkeypatch.setattr(resolver, "_gh", gh)
    assert resolver.main(argv) == 2
    assert calls == []
