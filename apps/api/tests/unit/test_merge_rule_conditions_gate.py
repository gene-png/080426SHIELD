"""Merge-rule condition 4, computed from the diff and declared in the body.

## THIS FILE LOST MOST OF ITS CASES, AND THE DELETION IS THE POINT

The gate covered condition 5 as well. Adversarial review found the derivation
could not see a PR whose only change is `scripts/web-install-if-stale.sh` -- a
condition-5 path by the merge rule's own reasoning -- because it opened only
`.github/workflows/`, matched only `bash|python` as the verb, and could not map
the container path `/app/web-install-if-stale.sh` back to a repo path. Each of
those is a way the enumeration was narrower than the thing it enumerated.

Worse, the test NAMED for the derived half did not exercise it: its input
`apps/api/scripts/check_decision_numbers.py` matched the EXPLICIT glob
`apps/api/scripts/check_*.py`, and the lookup tried the table first and `break`ed.
Replacing `_as_path`'s body with `return raw` would have left the suite green.

So condition 5 is withdrawn rather than patched, and filed. What is left is
condition 4: one glob with an exact answer.

## AND THE ACKNOWLEDGMENT IS A MARKER NOW, SO THESE CASES TEST A DIFFERENT
## PROPERTY THAN THEY DID

The old matcher looked for a bare digit in a `## Merge rule` region. It accepted
a DENIAL ("This does not trip condition 5.") and it accepted the PR template's
own commented `the 4 files in this diff`, which appears in every body in the
repo. Both are pinned below as cases that must now FAIL -- a suite exercising
only the happy path would have caught neither.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_merge_rule_conditions.py"

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_COULD_NOT_LOOK = 2

MIGRATION = "apps/api/alembic/versions/0051_x.py"
MARKER = "Merge-rule-condition-4: adds two nullable columns to deliverables"


def _run(tmp_path: pathlib.Path, changed: str | None, body: str | None, *extra: str):
    """Run it as a PROCESS, so the `__main__` crash handler is exercised."""
    args = [sys.executable, str(SCRIPT), *extra]
    if changed is not None:
        p = tmp_path / "changed.txt"
        p.write_text(changed, encoding="utf-8")
        args += ["--changed-files", str(p)]
    if body is not None:
        b = tmp_path / "body.md"
        b.write_text(body, encoding="utf-8")
        args += ["--body", str(b)]
    # noqa justified: every argument is built here from `sys.executable` and
    # `tmp_path`; there is no untrusted input.
    return subprocess.run(  # noqa: S603
        args, capture_output=True, text=True, encoding="utf-8", timeout=120
    )


# --------------------------------------------------------------- computing it


@pytest.mark.unit
def test_a_diff_with_no_migration_passes(tmp_path: pathlib.Path) -> None:
    result = _run(tmp_path, "README.md\napps/api/app/config.py\n", "Nothing to declare.\n")
    assert result.returncode == EXIT_OK, f"{result.stdout}\n{result.stderr}"
    assert "condition 4 is not tripped" in result.stdout


@pytest.mark.unit
def test_alembic_env_is_NOT_condition_4(tmp_path: pathlib.Path) -> None:
    """The merge rule puts `env.py` under condition 5, in as many words.

    Asserted because the obvious glob -- anything under `alembic/` -- would catch
    it and then demand a migration declaration for a change that adds no
    revision. Condition 5 is not computed here, so `env.py` is unenforced by this
    gate; the docstring says so rather than leaving it silently true.
    """
    result = _run(tmp_path, "apps/api/alembic/env.py\n", "No declaration here.\n")
    assert result.returncode == EXIT_OK, f"{result.stdout}\n{result.stderr}"


@pytest.mark.unit
def test_a_migration_without_the_marker_FAILS(tmp_path: pathlib.Path) -> None:
    result = _run(tmp_path, f"{MIGRATION}\n", "A tidy body that mentions nothing.\n")
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}\n{result.stderr}"
    assert MIGRATION in result.stdout, "the failure must NAME the path that tripped it"


@pytest.mark.unit
def test_a_migration_WITH_the_marker_passes(tmp_path: pathlib.Path) -> None:
    result = _run(tmp_path, f"{MIGRATION}\n", f"## Summary\n\nWork.\n\n{MARKER}\n")
    assert result.returncode == EXIT_OK, f"{result.stdout}\n{result.stderr}"
    assert "adds two nullable columns" in result.stdout, (
        "the clean line must echo the REASON, or the marker degrades into a "
        "ritual token nobody reads"
    )


# ------------------------------------------- what the digit matcher accepted


@pytest.mark.unit
def test_a_DENIAL_does_not_satisfy_it(tmp_path: pathlib.Path) -> None:
    """THE DEFECT THE MARKER EXISTS FOR.

    The first version matched a bare digit inside a `## Merge rule` region, so
    this body passed over a diff adding a revision. `CLAUDE.md`'s closing-keyword
    shape -- "THE NEGATION IS INVISIBLE TO THE MATCHER" -- rebuilt inside the gate
    whose subject is honesty, and the more carefully someone writes their scope
    statement the likelier the pass.
    """
    body = "## Merge rule\n\nThis does not trip condition 4. No migration here.\n"
    result = _run(tmp_path, f"{MIGRATION}\n", body)
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}\n{result.stderr}"


@pytest.mark.unit
def test_the_PR_TEMPLATES_OWN_BOILERPLATE_does_not_satisfy_it(tmp_path: pathlib.Path) -> None:
    """`.github/pull_request_template.md` carries `the 4 files in this diff`.

    It has no `## Merge rule` heading, so the old region fell back to the WHOLE
    body and that bare `4` acknowledged condition 4 for every author who left the
    comment block in place -- which the template tells them to do. The sibling
    gate in the same workflow has a dedicated step for exactly this hazard; this
    one had neither a step nor a test.
    """
    body = "<!-- Scope -> the 4 files in this diff, at <sha> -->\n\nA real summary.\n"
    result = _run(tmp_path, f"{MIGRATION}\n", body)
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}\n{result.stderr}"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("body", "label"),
    [
        ("Reviewed at a3137d5.\n", "a sha with an isolated 4"),
        ("Pinned to prettier@3.9.4 today.\n", "a version"),
        ("4. Added the fixtures\n", "an ordered-list item"),
        ("Touches e2e/smoke/s4-login.spec.ts only.\n", "a path with an isolated digit"),
        ("Quoting the rule: any PR tripping 4, 5 or 6 comes back.\n", "a quoted merge rule"),
    ],
)
def test_a_stray_digit_does_not_satisfy_it(tmp_path, body, label) -> None:
    """Five shapes the digit matcher accepted, none of which declares anything.

    Parametrised because the failure is a CLASS -- "a 4 appears somewhere" -- and
    one example would leave the rest untested while looking covered.
    """
    result = _run(tmp_path, f"{MIGRATION}\n", body)
    assert result.returncode == EXIT_VIOLATION, f"{label}: {result.stdout} {result.stderr}"


@pytest.mark.unit
def test_an_EMPTY_reason_is_not_a_reason(tmp_path: pathlib.Path) -> None:
    """The rule `check_test_integrity` applies to `# test-integrity:`.

    A marker with nothing after the colon is the ritual-satisfaction outcome the
    marker was chosen to avoid, so it is refused rather than counted.
    """
    result = _run(tmp_path, f"{MIGRATION}\n", "Merge-rule-condition-4:   \n")
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}\n{result.stderr}"


@pytest.mark.unit
def test_the_marker_in_PROSE_does_not_satisfy_it(tmp_path: pathlib.Path) -> None:
    """The colon is required, so a mention of the rule is not a declaration."""
    body = "I read the Merge-rule-condition-4 rule and it does not apply.\n"
    result = _run(tmp_path, f"{MIGRATION}\n", body)
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}\n{result.stderr}"


# ------------------------------------------------- could-not-look is not clean


@pytest.mark.unit
@pytest.mark.parametrize(
    ("changed", "body", "extra", "label"),
    [
        ("", "x\n", (), "an empty changed-file list"),
        (None, "x\n", (), "no --changed-files"),
        (f"{MIGRATION}\n", None, (), "no --body"),
        (f"{MIGRATION}\n", "x\n", ("--bogus",), "an unknown flag"),
    ],
)
def test_could_not_look_branches_are_2(tmp_path, changed, body, extra, label) -> None:
    """Each must be 2, never 0. An empty list would otherwise read as "no
    migration", which is `check_audit_evidence.py`'s `is_code_change([])`."""
    result = _run(tmp_path, changed, body, *extra)
    assert result.returncode == EXIT_COULD_NOT_LOOK, f"{label}: {result.stdout} {result.stderr}"


@pytest.mark.unit
def test_a_migration_in_a_SUBDIRECTORY_is_still_caught(tmp_path: pathlib.Path) -> None:
    """`fnmatch`'s `*` crosses `/`, which is load-bearing rather than a quirk to
    work around: a revision filed in a subdirectory is still a revision."""
    result = _run(tmp_path, "apps/api/alembic/versions/legacy/0002_x.py\n", "No marker.\n")
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}\n{result.stderr}"


# ---------------------------------------------------------------------------
# ROUND 2. The marker's own escape hatches, every one measured at exit 0 before
# these existed.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_GATES_OWN_FAILURE_MESSAGE_does_not_satisfy_it(tmp_path: pathlib.Path) -> None:
    """The failure text prints a line that used to pass the gate.

    `check_merge_rule_conditions.py`'s own instruction reads
    `      Merge-rule-condition-4: <what the migration does>`, and `_MARKER`
    allows leading whitespace — so pasting the CI output into the body, or
    copying the suggested line without filling it in, satisfied the gate with
    `why = "<what the migration does>"`.

    That is the PR-template-boilerplate defect this narrowing was built to close,
    rebuilt out of the gate's own instruction text. A placeholder in angle
    brackets is refused.
    """
    body = "      Merge-rule-condition-4: <what the migration does>\n"
    result = _run(tmp_path, f"{MIGRATION}\n", body)
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}\n{result.stderr}"


@pytest.mark.unit
@pytest.mark.parametrize("why", ["n/a", "none", "no", "nil", "-", "TBD", "None."])
def test_a_MARKER_SHAPED_denial_does_not_satisfy_it(tmp_path, why) -> None:
    """Refusing "" and accepting "n/a" is the same outcome one character away.

    The prose said "a denial cannot produce it" in three places, and the original
    denial test covered only the PROSE form, so this was untested. `_NOT_A_REASON`
    is a DENYLIST and is named as one — a floor over the phrasings someone reaches
    for when they have nothing to declare, not a proof that a denial is impossible.
    """
    result = _run(tmp_path, f"{MIGRATION}\n", f"Merge-rule-condition-4: {why}\n")
    assert result.returncode == EXIT_VIOLATION, f"{why!r}: {result.stdout} {result.stderr}"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("body", "label"),
    [
        ("<!--\nMerge-rule-condition-4: x\n-->\n", "inside an HTML comment"),
        ("```\nMerge-rule-condition-4: x\n```\n", "inside a code fence"),
        ("> Merge-rule-condition-4: x\n", "inside a blockquote"),
    ],
)
def test_a_marker_that_is_not_really_in_the_body(tmp_path, body, label) -> None:
    """`.github/pull_request_template.md` records this hazard for the SIBLING gate:
    "this checker does not strip HTML comments -- restore the colon and every PR
    passes having recorded nothing". This gate reproduced it.

    The blockquote case was already excluded by `_MARKER`'s `^[ \t]*` anchor and
    is asserted rather than assumed, because "already safe" is a claim.
    """
    result = _run(tmp_path, f"{MIGRATION}\n", body)
    assert result.returncode == EXIT_VIOLATION, f"{label}: {result.stdout} {result.stderr}"


@pytest.mark.unit
def test_a_REAL_declaration_after_a_commented_one_still_passes(tmp_path: pathlib.Path) -> None:
    """Stripping must not make a genuine declaration unreachable.

    The direction that decides whether the stripping survives: a body that quotes
    the instruction in a comment AND then declares properly is honest, and failing
    it would teach people to delete the comment rather than to declare.
    """
    body = "<!-- Merge-rule-condition-4: <what the migration does> -->\n\nMerge-rule-condition-4: adds 0051\n"
    result = _run(tmp_path, f"{MIGRATION}\n", body)
    assert result.returncode == EXIT_OK, f"{result.stdout}\n{result.stderr}"
    assert "adds 0051" in result.stdout
