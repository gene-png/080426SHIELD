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
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))

from check_decision_numbers import (  # noqa: E402
    inconsistent,
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
