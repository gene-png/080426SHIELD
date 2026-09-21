"""The close-keyword gate must judge THIS branch's commits, not the base's.

The guard itself was never wrong. Every test in
`test_issue_reference_guard.py` exercises the PARSER, and the parser is
correct. **Nothing tested the COLLECTION step**, and that is where the defect
lived:

    git log --format=%B "origin/${BASE}...HEAD"

For `git diff`, `A...B` means "changes since the merge base". For `git log` it
means the **symmetric difference** -- every commit on `A` that `B` lacks, as
well as `B`'s own. Same spelling, opposite meaning, which is exactly why it
read as correct to everyone who looked at it.

So the gate collected the BASE's commit messages whenever a branch was behind,
and then judged the PR on prose nobody on it had written.

## Why it stayed silent until it did not

It has behaved this way on every PR since it was written. It went unnoticed
because no commit message on `main` had ever carried a closing keyword beside a
number -- until #269's squash landed, whose subject ends `(#115)` and whose
body reads "The guard written to close #115 reproduced #115 on that input".

At that moment every open PR three commits behind `main` started failing on
someone else's sentence. Measured on `chore/verify-prints-its-bound`:

    git log --format=%B origin/main...HEAD | grep -c 115   -> non-zero
    git log --format=%B origin/main..HEAD  | grep -c 115   -> 0

The branch's own single commit contains no digits at all.

## Why this test is a file read rather than a git experiment

The defect was one character in a YAML file, so the guard against it is a check
that the character is still right. Running a temp-repo experiment here would
demonstrate git's range semantics -- which are not in dispute and are not this
repo's to pin -- while leaving the actual regression surface untested.

The second assertion is the one that keeps this from going vacuous: if the
`git log` line is ever renamed or moved out of this workflow, the check fails
loudly instead of passing over a file it can no longer find. "I could not look"
must not share an exit with "nothing to complain about".
"""

from __future__ import annotations

import pathlib
import re

import pytest

from tests._paths import find_workflows_dir

# The search lives in `tests/_paths.py` so its PASSING state is testable from a
# tmp tree -- see `test_root_discovery.py`. At module scope reading `__file__`
# it was not: a typo in the marker path would have skipped this module on the
# host and on CI alike, forever, green.
#
# The directory and not the FILE, and that distinction is the whole guard.
# This was `parents[4]`, correct for the host checkout and an `IndexError`
# inside the api container, where `./apps/api` is mounted at `/app` -- this
# file is then `/app/tests/unit/x.py`, which has four parents and not five. At
# module
# scope that aborts collection, so the documented `pytest -m unit` evaluated
# not one assertion (#314).
#
# THE FIRST FIX SEARCHED FOR THE WORKFLOW FILE AND SKIPPED WHEN IT WAS NOT
# FOUND, WHICH INVERTED THE GUARD. `main` reached `assert WORKFLOW.is_file()`
# and failed LOUDLY when the workflow was renamed, moved or deleted. Keying the
# skip on the file made that indistinguishable from "I am in the container" --
# so folding `audit-gate.yml` into `ci.yml`, a live proposal (#312), would have
# retired the `..`-versus-`...` guard this file exists for with a green
# `2 skipped`.
_WORKFLOWS_DIR = find_workflows_dir(pathlib.Path(__file__).resolve())

# Skipped ONLY when there is no `.github/workflows` above this file at all.
# That is the container, and it is the one case where skipping beats failing:
# taking 7000 unrelated tests down because one gate test cannot reach its
# artifact is the fail-closed rule applied in the wrong direction. The skip is
# audible -- `pytest -rs` names it and the reason says where the test does run.
#
# A checkout that HAS the directory and not the file is a different world, and
# it keeps the loud failure it had on `main`: `WORKFLOW` is set below and
# `_git_log_lines` asserts on it.
if _WORKFLOWS_DIR is None:
    pytest.skip(
        "no .github/workflows directory above this file -- expected inside the "
        "api container, which mounts apps/api at /app and cannot see the repo "
        "root (#314). This test is exercised on a full checkout, which is what "
        "CI runs.",
        allow_module_level=True,
    )

WORKFLOW = _WORKFLOWS_DIR / "audit-gate.yml"


def _git_log_lines() -> list[str]:
    assert WORKFLOW.is_file(), f"workflow not found at {WORKFLOW}"
    return [
        ln.strip()
        for ln in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if "git log" in ln and not ln.strip().startswith("#")
    ]


@pytest.mark.unit
def test_the_workflow_still_collects_commit_messages() -> None:
    """Fail loudly if there is nothing left to check.

    Without this, renaming the step or moving the collection elsewhere would
    make the assertion below pass over a file that no longer contains the thing
    it is guarding -- a green from a check that could not look.
    """
    lines = _git_log_lines()
    assert lines, (
        f"{WORKFLOW.name} contains no `git log` line. Either the collection "
        "moved and this test must follow it, or the gate stopped collecting "
        "commit messages at all. Both need a human."
    )


@pytest.mark.unit
def test_commit_collection_uses_two_dots_not_three() -> None:
    """`A..HEAD` is this branch's commits. `A...HEAD` is those plus the base's.

    A branch that falls behind a base whose recent commits carry a closing
    keyword must still pass. Under three dots it does not, and the failure
    names a sentence the PR author never wrote.
    """
    offenders = [ln for ln in _git_log_lines() if re.search(r"\.\.\.\s*HEAD", ln)]
    assert not offenders, (
        "the audit gate collects commit messages with a THREE-dot range: "
        f"{offenders!r}. For `git log` that is the symmetric difference, so it "
        "picks up every commit the base has and this branch does not -- and the "
        "gate then judges this PR on the base's prose. Use `..`."
    )


def _step_names_in_order() -> list[str]:
    """Step names from `audit-gate.yml`, in file order.

    Read from the file rather than parsed with a YAML library, to match the
    rest of this module and to avoid adding a dependency for one assertion.
    Folded scalars (`- name: >-`) put the text on the FOLLOWING lines, so the
    continuation is joined -- the D-number step uses exactly that form and a
    naive `- name:` scrape would record it as empty.
    """
    assert WORKFLOW.is_file(), f"workflow not found at {WORKFLOW}"
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    names: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("- name:"):
            value = stripped[len("- name:") :].strip()
            if value in (">-", ">", "|", "|-"):
                parts = []
                i += 1
                while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("#"):
                    nxt = lines[i].strip()
                    if nxt.startswith("- ") or nxt.endswith(":"):
                        break
                    parts.append(nxt)
                    i += 1
                names.append(" ".join(parts))
                continue
            names.append(value)
        i += 1
    return names


@pytest.mark.unit
def test_the_dnumber_step_runs_after_the_close_guard() -> None:
    """#318's assurance was held up by ORDER and by nothing else.

    The D-number step's comment says "Running last makes the assurance true by
    construction rather than by wording: if this step is reached, the close
    guard has already passed." That is correct, and until this test it rested
    entirely on the step's ordinal position in a file nobody diffs for order.

    Neither later step carries an `if:` or `continue-on-error`, so a D-number
    failure ABOVE the close guard aborts the job before the close guard runs --
    and the banner then tells the reader their closing keywords are fine about
    a check that never executed. "I could not look" wearing "nothing to
    complain about", emitted by the fix for a reporting defect.

    A fail-fast reorder, or a new step inserted between them, reopens that
    silently. This turns the reopening into a red.

    Asserted as an ORDER relation rather than "is last", deliberately: a step
    appended after the D-number one is harmless, and a test demanding lastness
    would fail on a change that breaks nothing. What must hold is that the
    close guard precedes it.
    """
    names = _step_names_in_order()
    assert names, (
        f"{WORKFLOW.name} yielded no step names. The scrape broke or the file "
        "moved; either way this test cannot look and must not report clean."
    )

    close_guard = [i for i, n in enumerate(names) if n.startswith("Reject undeclared issue closes")]
    dnumber = [i for i, n in enumerate(names) if n.startswith("D-NUMBERS:")]

    assert close_guard, (
        "no step named 'Reject undeclared issue closes' in "
        f"{WORKFLOW.name}. It was renamed or removed -- if renamed, this test "
        "must follow it, because the ordering guarantee is about that step."
    )
    assert dnumber, (
        f"no step whose name starts 'D-NUMBERS:' in {WORKFLOW.name}. Same "
        "reasoning: the guarantee is about this step's position."
    )
    assert close_guard[0] < dnumber[0], (
        "the D-number step now runs BEFORE 'Reject undeclared issue closes'. "
        "Its own comment claims the close guard has already passed by the time "
        "it is reached, and that is false as ordered: a D-number failure "
        "aborts the job and the close guard never runs, while the banner tells "
        "the reader their closing keywords are fine. Move it back below, or "
        "give the close guard `if: always()` and rewrite the comment."
    )
