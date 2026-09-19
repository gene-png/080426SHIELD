"""The D-number gate catches a mismatch and does not catch a squash merge.

Both states, because a guard observed only firing is half-tested — and this one
sits on every PR, so a false positive blocks the queue.

## Why CONSISTENCY and not completeness

Measured against real commits before the boundary was chosen:

    57877e7  subject "D-072 ..."  adds D-078   -> must FAIL
    ed4f48b  subject names none   adds D-076, D-077 -> must PASS

`ed4f48b` is an ordinary squash merge, and every merge on `main` is one — the
subject is the PR title. A completeness rule would have failed the entire
history to catch the single real defect. The harm was never the omission: a
subject naming no number causes no false clash on a rebase. A subject naming
the WRONG one is what made every positional append look like a collision.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))

from check_decision_numbers import (  # noqa: E402
    inconsistent,
    main,
    subject_decisions,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject, expected",
    [
        ("docs(decisions): D-072 — the instrument exits 0", ["D-072"]),
        ("docs: record D-059a as an amendment", ["D-059a"]),
        ("docs: two at once, D-080 and D-081", ["D-080", "D-081"]),
        ("docs: record the false-remedy class (#249)", []),
        ("fix(zt): a bool is not a stage", []),
    ],
)
def test_it_reads_the_numbers_a_subject_claims(subject, expected) -> None:
    assert subject_decisions(subject) == expected


@pytest.mark.unit
def test_the_suffix_is_not_truncated() -> None:
    """`D-059a` is a different entry from `D-059`.

    A pattern that stops at the digits reports the pair as a duplicate. That
    false positive was produced, believed and reported before being caught, so
    it is pinned in both directions here.
    """
    assert subject_decisions("docs: D-059a amends D-059") == ["D-059a", "D-059"]
    assert inconsistent("docs: D-059a", ["D-059"]) == ["D-059a"]
    assert inconsistent("docs: D-059", ["D-059a"]) == ["D-059"]


@pytest.mark.unit
def test_a_subject_naming_what_it_adds_is_consistent() -> None:
    assert inconsistent("docs(decisions): D-078 — the instrument", ["D-078"]) == []
    assert inconsistent("docs: D-080 and D-081", ["D-080", "D-081"]) == []


@pytest.mark.unit
def test_a_subject_naming_something_else_is_not() -> None:
    """THE FIRING STATE — the real commit, transcribed."""
    assert inconsistent(
        "docs(decisions): D-072 — the instrument exits 0 with failures on record",
        ["D-078"],
    ) == ["D-072"]


@pytest.mark.unit
def test_a_squash_merge_is_not_flagged() -> None:
    """THE PASSING STATE, and the one that decides the design.

    Naming no decision means there is nothing to be inconsistent with. Without
    this, the gate fails every merge in the repo's history.
    """
    assert (
        inconsistent(
            "docs: record the false-remedy class, and fix twins and prose by shape (#249)",
            ["D-076", "D-077"],
        )
        == []
    )


@pytest.mark.unit
def test_it_reads_only_ADDED_headings() -> None:
    """A pattern matching context lines would return every heading in the file.

    Fed a diff fragment in the shape `git show --unified=0` really produces --
    a `+` heading, a context heading, and a removed one -- rather than calling
    git. The container mounts the worktree without a resolvable `.git`, so the
    end-to-end path runs in CI, where `audit-gate.yml` already checks out full
    history. Verified there against two real commits before this was written:
    `57877e7` (subject D-072, adds D-078) fails, `ed4f48b` (subject names none,
    adds D-076 and D-077) passes.
    """
    from check_decision_numbers import _HEADING

    # A real `git show --unified=0` shape: an added heading, a context heading
    # that was already present, and a removed one.
    diff = """@@ -4515,0 +4516,3 @@
+## D-076 - A user-facing string that names an action must exist
+
+**Date:** 2026-09-09.
 ## D-075 - an untouched neighbour
-## D-070 - a removed heading
+## D-077 - a second addition in the same commit
"""

    assert _HEADING.findall(diff) == ["D-076", "D-077"], (
        "only ADDED headings count: a context line is a decision that was "
        "already there, and a removed one is not being added"
    )


# ---------------------------------------------------------------------------
# `main()` — which had NO test at all (#318).
#
# Everything above exercises the helpers. Three mutations to `main` left the
# whole suite green, and one of them re-opens the exact defect
# `test_audit_gate_collects_only_this_branch.py` exists for, one step below
# where it was fixed: changing `{base}..{head}` to three dots makes the range a
# symmetric difference, so commits on `main` that the branch never touched are
# attributed to it.
#
# These drive `main` against a REAL git repository built in a tmp dir, because
# the range resolution is the thing under test and a mocked `_git` would prove
# only that the argument parser works.
# ---------------------------------------------------------------------------


#: `git` resolved ONCE, by absolute path. The gate under test shells out to
#: git, so these cannot run where git is absent -- and the api container is
#: exactly that: `docker compose exec -T api git --version` answers
#: `sh: 1: git: not found`. CI runs pytest on the runner, which has it.
#:
#: SKIPPED WITH A REASON rather than silently passing, and the reason names
#: where they DO run. A gate test that evaporates where its dependency is
#: missing, quietly, is the shape #314 was about.
_GIT = shutil.which("git")

requires_git = pytest.mark.skipif(
    _GIT is None,
    reason=(
        "no git on PATH -- expected inside the api container, which does not "
        "ship it. `main()` shells out to git, so these would exercise nothing "
        "here. They run on a full checkout, which is what CI uses."
    ),
)


def _git_run(cwd: pathlib.Path, *args: str) -> None:
    """One git invocation, by ABSOLUTE path and a fixed argument list.

    `# noqa: S603` -- ruff flags every `subprocess.run` as untrusted input.
    The arguments are literals and a `tmp_path` this test created. S607 (a
    partial executable path) is answered rather than suppressed: `_GIT` comes
    from `shutil.which`, which is that rule's actual remedy.
    """
    assert _GIT is not None
    subprocess.run([_GIT, *args], cwd=cwd, check=True, capture_output=True, text=True)  # noqa: S603


def _repo(tmp_path: pathlib.Path) -> pathlib.Path:
    r = tmp_path / "r"
    r.mkdir()
    _git_run(r, "init", "-q", "-b", "main")
    _git_run(r, "config", "user.email", "t@example.com")
    _git_run(r, "config", "user.name", "T")
    (r / "DECISIONS.md").write_text("# Decisions" + chr(10), encoding="utf-8")
    _git_run(r, "add", "-A")
    _git_run(r, "commit", "-q", "-m", "chore: base")
    return r


def _commit(repo: pathlib.Path, subject: str, added: str) -> None:
    p = repo / "DECISIONS.md"
    p.write_text(p.read_text(encoding="utf-8") + added, encoding="utf-8")
    _git_run(repo, "add", "-A")
    _git_run(repo, "commit", "-q", "-m", subject)


def _run(repo: pathlib.Path, *extra: str) -> int:
    import os

    cwd = os.getcwd()
    os.chdir(repo)
    try:
        return main(["--base", "main", "--head", "HEAD", *extra])
    finally:
        os.chdir(cwd)


@pytest.mark.unit
@requires_git
def test_main_passes_a_consistent_subject(tmp_path: pathlib.Path) -> None:
    """THE PASSING STATE. Without it the refusals could all be one broken path."""
    repo = _repo(tmp_path)
    _git_run(repo, "checkout", "-q", "-b", "f")
    _commit(repo, "docs(decisions): D-090 -- a thing", "\n## D-090 -- a thing\n")
    assert _run(repo) == 0


@pytest.mark.unit
@requires_git
def test_main_flags_a_subject_naming_a_different_decision(tmp_path: pathlib.Path) -> None:
    """THE NEGATIVE CONTROL, and the defect the gate was written for."""
    repo = _repo(tmp_path)
    _git_run(repo, "checkout", "-q", "-b", "f")
    _commit(repo, "docs(decisions): D-072 -- a thing", "\n## D-078 -- a thing\n")
    assert _run(repo) == 1


@pytest.mark.unit
@requires_git
def test_main_refuses_a_range_it_cannot_resolve(tmp_path: pathlib.Path) -> None:
    """Exit 2, not 0. An unresolvable range makes every branch look clean, so
    reporting it as a pass is the silent-success shape this gate is part of the
    answer to."""
    import os

    repo = _repo(tmp_path)
    cwd = os.getcwd()
    os.chdir(repo)
    try:
        assert main(["--base", "no/such/ref", "--head", "HEAD"]) == 2
    finally:
        os.chdir(cwd)


@pytest.mark.unit
@requires_git
def test_main_uses_TWO_dots_not_three(tmp_path: pathlib.Path) -> None:
    """THE MUTATION NOTHING CAUGHT.

    `{base}..{head}` is the commits on head and not on base. `{base}...{head}`
    is the SYMMETRIC DIFFERENCE, so commits made on `main` after the branch
    diverged are attributed to the branch. That re-opens the defect
    `test_audit_gate_collects_only_this_branch.py` exists for, one step below
    where it was fixed — and with three dots the whole suite stayed green.

    Built so the two spellings disagree: `main` gains an INCONSISTENT commit
    AFTER the branch diverged, and the branch itself is clean. Two dots see
    only the branch and pass; three dots pull in main's commit and fail.
    """
    repo = _repo(tmp_path)
    _git_run(repo, "checkout", "-q", "-b", "f")
    _commit(repo, "docs(decisions): D-090 -- fine", "\n## D-090 -- fine\n")
    _git_run(repo, "checkout", "-q", "main")
    _commit(repo, "docs(decisions): D-001 -- mismatched", "\n## D-099 -- mismatched\n")
    _git_run(repo, "checkout", "-q", "f")

    assert _run(repo) == 0, (
        "the branch's own commit is consistent, so this must pass -- if it "
        "fails, the range is a symmetric difference and is attributing main's "
        "commits to the branch"
    )
