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


def _find_workflow() -> pathlib.Path | None:
    """The workflow, found by SEARCHING UPWARD for the repo marker.

    This was `parents[4]`, which is correct for the host checkout --
    `apps/api/tests/unit/x.py` puts the repo root four up -- and raises
    `IndexError` inside the api container, where `./apps/api` is mounted at
    `/app` and this file has three parents in total.

    At MODULE SCOPE that is a collection error, not a test failure: pytest
    imports a module to collect it, so the exception aborts the whole session
    and the documented command

        docker compose exec -T api pytest -m unit -q

    evaluated not one assertion. CI stayed green because it runs on the runner
    from a full checkout, where the arithmetic holds -- the correctness lived
    in a `working-directory:` line in a different file, which is the shape
    `CLAUDE.md` already records for `check_test_integrity` (#314).

    A count is a claim about where this file sits in a tree. The marker is a
    property of the tree, so this cannot silently resolve to the WRONG
    directory -- only fail to find one, which the caller reports.
    """
    for candidate in pathlib.Path(__file__).resolve().parents:
        workflow = candidate / ".github" / "workflows" / "audit-gate.yml"
        if workflow.is_file():
            return workflow
    return None


WORKFLOW = _find_workflow()

# Skipped, not raised, and the distinction is the whole fix. "The workflow is
# not reachable from here" and "the workflow is wrong" are different outcomes,
# and only the second should be able to fail this file. Taking the entire suite
# down because one gate test cannot find its input is the fail-closed rule
# applied in the wrong direction: it stops everything ELSE being checked, which
# is not the same as refusing to certify itself.
#
# The skip is AUDIBLE -- `pytest -rs` names it and the reason says where to run
# it instead. A silent skip here would be the silent-success shape one level up.
if WORKFLOW is None:
    pytest.skip(
        "no .github/workflows/audit-gate.yml above this file -- expected inside "
        "the api container, which mounts apps/api at /app and cannot see the "
        "repo root (#314). This test is exercised on a full checkout, which is "
        "what CI runs.",
        allow_module_level=True,
    )


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
