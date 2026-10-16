"""The queued PR's head must be what the merge group merges (#659, #736 item C).

The resolver reads PR N's CURRENT body. That body is only evidence about the
change being merged if the PR's current head is the head the group was built
from. A push after the PR was queued, or a group carrying content beyond
`base_sha` plus this PR, breaks that link, and the body checks would then judge
one head and wave through another.

So, given the group's `base_sha` and `head_sha` from the event, the resolver
requires

    tree(merge_group.head_sha) == git merge-tree --write-tree base_sha <PR head.sha>

which holds for a squash, a merge commit or a rebase alike: each method gives
the group's head the tree of "base plus this PR". Anything else is exit 2 --
could not establish which head the body describes -- with no output written.

`git` is replaced in-process here, answering from a table of commits; the same
states run against REAL git in `tests/gates/merge_group_head.sh`, which is the
half that proves `merge-tree` agrees with a squash.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import scripts.merge_group_pr as resolver

_REPO = "owner/repo"
_BASE = "b" * 40
_PR_HEAD = "c" * 40
_GROUP = "d" * 40
_REF = f"refs/heads/gh-readonly-queue/main/pr-42-{'a' * 40}"
_TREE = "e" * 40
_OTHER_TREE = "f" * 40

_PR = {
    "number": 42,
    "title": "A queued change",
    "body": "## Adversarial audit\nFindings: none\nDisposition: n/a\nScope: at cccccccc\n",
    "user": {"login": "someone"},
    "head": {"sha": _PR_HEAD},
    "changed_files": 1,
    "commits": 1,
}


def _fake_gh(pr: dict):
    calls: list[tuple[str, ...]] = []

    def gh(*args: str) -> str:
        calls.append(args)
        path = args[-1]
        if "/files" in path:
            return json.dumps([[{"filename": "apps/api/app/x.py"}]])
        if "/commits" in path:
            return json.dumps([[{"commit": {"message": "one"}}]])
        return json.dumps(pr)

    return gh, calls


class _FakeGit:
    """Answers the four git questions the resolver asks, from a table.

    `present` is the set of commits in the clone; `fetchable` are those a
    `git fetch origin <sha>` would bring in. `merge_tree` maps (base, head) to
    (exit code, tree); `trees` maps a commit to its tree."""

    def __init__(self, *, present, fetchable=(), merge_tree=None, trees=None):
        self.present = set(present)
        self.fetchable = set(fetchable)
        self.merge_tree = merge_tree or {}
        self.trees = trees or {}
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> tuple[int, str]:
        self.calls.append(args)
        if args[:2] == ("cat-file", "-e"):
            return (0, "") if args[2].removesuffix("^{commit}") in self.present else (128, "")
        if args[0] == "fetch":
            sha = args[-1]
            if sha in self.fetchable:
                self.present.add(sha)
                return 0, ""
            return 128, "fatal: remote error: upload-pack: not our ref"
        if args[:2] == ("merge-tree", "--write-tree"):
            code, tree = self.merge_tree.get((args[2], args[3]), (128, ""))
            return code, f"{tree}\n" if tree else "fatal: refusing to merge unrelated histories"
        if args[0] == "rev-parse":
            sha = args[-1].removesuffix("^{tree}")
            return (0, f"{self.trees[sha]}\n") if sha in self.trees else (128, "")
        raise AssertionError(f"unexpected git call: {args}")


def _matching_git(**overrides) -> _FakeGit:
    kwargs = {
        "present": {_BASE, _PR_HEAD, _GROUP},
        "merge_tree": {(_BASE, _PR_HEAD): (0, _TREE)},
        "trees": {_GROUP: _TREE},
    }
    kwargs.update(overrides)
    return _FakeGit(**kwargs)


def _argv(tmp_path: Path, *, base: str | None = _BASE, group: str | None = _GROUP):
    outs = {name: tmp_path / f"{name}.txt" for name in ("body", "head_sha")}
    argv = ["merge_group_pr.py", "--head-ref", _REF, "--repo", _REPO]
    if base is not None:
        argv += ["--base-sha", base]
    if group is not None:
        argv += ["--group-head-sha", group]
    argv += ["--body-out", str(outs["body"]), "--head-sha-out", str(outs["head_sha"])]
    return argv, outs


def _run(tmp_path, monkeypatch, git, pr=_PR, **argv_kw):
    gh, _ = _fake_gh(pr)
    monkeypatch.setattr(resolver, "_gh", gh)
    monkeypatch.setattr(resolver, "_git", git)
    argv, outs = _argv(tmp_path, **argv_kw)
    for path in outs.values():
        path.write_text("STALE\n", encoding="utf-8")
    return resolver.main(argv), outs


@pytest.mark.unit
def test_a_group_holding_exactly_base_plus_this_pr_passes(tmp_path, monkeypatch, capsys) -> None:
    git = _matching_git()
    code, outs = _run(tmp_path, monkeypatch, git)
    assert code == 0, capsys.readouterr().err
    assert outs["head_sha"].read_text(encoding="utf-8") == f"{_PR_HEAD}\n"
    assert outs["body"].read_text(encoding="utf-8") == _PR["body"]
    out = capsys.readouterr().out
    assert f"head {_PR_HEAD} is what group {_GROUP} merges onto {_BASE}" in out, out
    assert ("merge-tree", "--write-tree", _BASE, _PR_HEAD) in git.calls


@pytest.mark.unit
def test_a_pr_pushed_after_it_was_queued_is_could_not_look(tmp_path, monkeypatch, capsys) -> None:
    """The group was built from an earlier head; the PR's head now merges to a
    different tree. The body read is about a head the queue is not merging."""
    git = _matching_git(trees={_GROUP: _OTHER_TREE})
    code, outs = _run(tmp_path, monkeypatch, git)
    assert code == 2
    err = capsys.readouterr().err
    assert "is NOT what merge group" in err, err
    assert not any(p.exists() for p in outs.values()), "an output survived a mismatch"


@pytest.mark.unit
def test_a_pr_head_that_conflicts_with_the_base_is_could_not_look(
    tmp_path, monkeypatch, capsys
) -> None:
    """merge-tree exits 1 on a conflict and still prints a tree. That tree is
    NOT a merge result, so it must never be compared as one."""
    git = _matching_git(merge_tree={(_BASE, _PR_HEAD): (1, _TREE)})
    code, outs = _run(tmp_path, monkeypatch, git)
    assert code == 2
    assert "conflict" in capsys.readouterr().err
    assert not any(p.exists() for p in outs.values())


@pytest.mark.unit
def test_merge_tree_failing_outright_is_could_not_look(tmp_path, monkeypatch, capsys) -> None:
    git = _matching_git(merge_tree={})
    code, _ = _run(tmp_path, monkeypatch, git)
    assert code == 2
    assert "merge-tree" in capsys.readouterr().err


@pytest.mark.unit
def test_a_pr_head_missing_from_the_clone_is_fetched(tmp_path, monkeypatch) -> None:
    """A fork's head is not under refs/heads, so the checkout lacks it."""
    git = _matching_git(present={_BASE, _GROUP}, fetchable={_PR_HEAD})
    code, _ = _run(tmp_path, monkeypatch, git)
    assert code == 0
    assert ("fetch", "--no-tags", "--quiet", "origin", _PR_HEAD) in git.calls


@pytest.mark.unit
def test_a_commit_that_cannot_be_fetched_is_could_not_look(tmp_path, monkeypatch, capsys) -> None:
    git = _matching_git(present={_BASE, _GROUP})
    code, outs = _run(tmp_path, monkeypatch, git)
    assert code == 2
    assert _PR_HEAD in capsys.readouterr().err
    assert not any(p.exists() for p in outs.values())


@pytest.mark.unit
@pytest.mark.parametrize(
    ("base", "group"),
    [
        (None, _GROUP),
        (_BASE, None),
        ("", _GROUP),
        (_BASE, ""),
        (_BASE[:39], _GROUP),
        (_BASE, _GROUP.upper()),
        (_BASE, _GROUP + "0"),
        (_BASE, "not-a-sha"),
    ],
)
def test_a_missing_or_malformed_group_sha_is_could_not_look(
    tmp_path, monkeypatch, base, group
) -> None:
    """One sha without the other, or either one empty or malformed, is not a
    group the resolver can check: 2, before any fetch."""
    git = _matching_git()
    gh, gh_calls = _fake_gh(_PR)
    monkeypatch.setattr(resolver, "_gh", gh)
    monkeypatch.setattr(resolver, "_git", git)
    argv, _ = _argv(tmp_path, base=base, group=group)
    assert resolver.main(argv) == 2
    assert gh_calls == [] and git.calls == []


@pytest.mark.unit
@pytest.mark.parametrize("head", [None, "", "c" * 39, "C" * 40, 7])
def test_a_pr_with_an_unreadable_head_sha_is_could_not_look(tmp_path, monkeypatch, head) -> None:
    git = _matching_git()
    code, outs = _run(tmp_path, monkeypatch, git, pr={**_PR, "head": {"sha": head}})
    assert code == 2
    assert not any(p.exists() for p in outs.values())


@pytest.mark.unit
def test_without_the_group_shas_the_head_is_said_to_be_unchecked(
    tmp_path, monkeypatch, capsys
) -> None:
    """The pair is optional so the resolver's older callers still run; the
    workflows always pass it (test_merge_group_event_reads.py). Unchecked must
    be SAID, never implied by a clean line."""
    git = _matching_git()
    code, _ = _run(tmp_path, monkeypatch, git, base=None, group=None)
    assert code == 0
    assert "head NOT checked against a merge group" in capsys.readouterr().out
    assert git.calls == []
