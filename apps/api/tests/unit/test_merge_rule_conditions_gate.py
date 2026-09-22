"""Conditions 4 and 5 of the merge rule, computed rather than remembered.

The rule says a PR tripping 4, 5 or 6 comes back to the human, and calls
condition 5 "mostly a path match". A path match with an exact answer, decided
from memory by whoever wants to merge, is the shape this gate replaces.

## What these cases are about

The gate does not refuse a PR for tripping a condition -- see its docstring for
why a permanently red required check is the wrong design. It refuses a PR body
that names FEWER conditions than the diff carries. So the cases split three
ways: the computation is right, the comparison is right, and every
could-not-look branch is 2 rather than 0.

The last group is the one worth having. `check_audit_evidence.py` shipped with
`is_code_change([])` returning False, so an empty changed-file list printed
"documentation-only change, exempt" and exited 0 -- a green gate with an
encouraging sentence over input supporting neither reading. Every equivalent
branch here is asserted.
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

SILENT_BODY = "## Merge rule\n\nTrips nothing.\n"


def _run(tmp_path: pathlib.Path, changed: str | None, body: str | None, *extra: str):
    """Run the gate as a PROCESS, so the `__main__` block is exercised.

    Importing `main` would skip the crash handler entirely, and the crash
    handler is the difference between exit 2 and exit 1 on an unhandled
    exception -- the distinction this repo reserves for "could not look".
    """
    args = [sys.executable, str(SCRIPT)]
    if changed is not None:
        path = tmp_path / "changed.txt"
        path.write_text(changed, encoding="utf-8")
        args += ["--changed-files", str(path)]
    if body is not None:
        path = tmp_path / "body.md"
        path.write_text(body, encoding="utf-8")
        args += ["--body", str(path)]
    args += list(extra)
    # noqa justified: every argument is built here from `sys.executable` and
    # `tmp_path`. There is no untrusted input, and running the gate as a real
    # process is the point.
    return subprocess.run(  # noqa: S603
        args, capture_output=True, text=True, encoding="utf-8", timeout=120
    )


# --------------------------------------------------------------------------
# The computation
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_a_docs_only_diff_trips_nothing() -> None:
    """The one legitimate green, and it must print what it looked at.

    A gate whose clean message says only "clean" cannot be told from one that
    read nothing. This asserts the message carries the counts, which is what
    distinguishes it from the exit-2 branches below.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result = _run(pathlib.Path(tmp), "README.md\ndocs/security.md\n", "## Summary\n\nDocs.\n")
    assert result.returncode == EXIT_OK, result.stderr
    assert "clean" in result.stdout
    assert "2 changed path(s)" in result.stdout, (
        "the clean message must state how many paths it read; a bare 'clean' "
        f"cannot be told from a gate that read nothing. Got: {result.stdout!r}"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "why"),
    [
        ("apps/api/app/config.py", "the redactor switch -- #142 lived here"),
        ("apps/api/app/ai/llm.py", "the single egress path"),
        ("apps/api/app/risk/engine.py", "a deterministic scoring engine"),
        ("apps/api/app/models/client.py", "stored behaviour without a migration"),
        ("apps/api/tests/unit/test_x.py", "weakening a test satisfies condition 1"),
        ("e2e/smoke/s1.spec.ts", "weakening a test satisfies condition 1"),
        ("apps/web/src/lib/x.test.ts", "the vitest suite"),
        ("docker-compose.yml", "the mounts every containerised gate reads"),
        (".github/workflows/ci.yml", "satisfies condition 1 by construction"),
        ("apps/api/scripts/check_plan_totals.py", "a gate"),
        ("tests/gates/prettier_hook.sh", "a gate written in shell"),
        ("apps/api/scripts/seed_demo.py", "clean seed data hid #130 for months"),
    ],
)
def test_each_gated_path_trips_condition_5(path: str, why: str) -> None:
    """One case per class, because a single representative proves one glob.

    The parameters are the classes `CLAUDE.md`'s condition 5 names, not a
    sample of them -- a table drawn from what its author happened to think of
    is the enumeration defect this repo records. Where the rule names a class,
    there is a row.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result = _run(pathlib.Path(tmp), f"{path}\n", SILENT_BODY)
    assert result.returncode == EXIT_VIOLATION, (
        f"{path} ({why}) did not trip condition 5.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert path in result.stdout, "the failure must name the path a human is being sent to"


@pytest.mark.unit
def test_a_new_alembic_revision_trips_condition_4() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result = _run(pathlib.Path(tmp), "apps/api/alembic/versions/0099_x.py\n", SILENT_BODY)
    assert result.returncode == EXIT_VIOLATION
    assert "condition 4" in result.stdout


@pytest.mark.unit
def test_alembic_env_is_condition_5_and_NOT_a_migration() -> None:
    """The distinction the merge rule draws: "no migration" is not "nothing
    under alembic/". A cascade rule or a column default changes stored
    behaviour without adding a revision, so `env.py` must trip 5 and not 4 --
    getting that backwards would let an `env.py` change read as a migration and
    be handled under the wrong condition.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result = _run(pathlib.Path(tmp), "apps/api/alembic/env.py\n", SILENT_BODY)
    assert result.returncode == EXIT_VIOLATION
    assert "condition 5" in result.stdout
    assert "condition 4" not in result.stdout


@pytest.mark.unit
def test_a_gate_script_trips_5_even_when_the_explicit_table_does_not_name_it() -> None:
    """The DERIVED half, which is the half that survives a new gate.

    `CLAUDE.md`: derive the set, do not extend the list. A gate wired into a
    workflow in a spelling this file has never heard of still counts, because
    the membership test is "does any workflow execute it".
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result = _run(
            pathlib.Path(tmp), "apps/api/scripts/check_decision_numbers.py\n", SILENT_BODY
        )
    assert result.returncode == EXIT_VIOLATION
    assert "check_decision_numbers.py" in result.stdout


@pytest.mark.unit
def test_THIS_GATE_trips_its_own_condition_5() -> None:
    """Self-application, and it is here because it found a real hole.

    The first version of `EXPLICIT_CONDITION_5` omitted
    `apps/api/scripts/check_*.py`, on the belief that `derived_gate_paths`
    subsumed it. It does not: the derived set answers "is this EXECUTED as a
    gate today", and a gate not yet wired into a workflow is not. Run against
    its own one-file diff, the gate reported "clean -- none of 1 changed path(s)
    trips condition 4 or 5" over a new gate script.

    So this case is the mechanism that caught it, kept.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result = _run(pathlib.Path(tmp), f"apps/api/scripts/{SCRIPT.name}\n", SILENT_BODY)
    assert result.returncode == EXIT_VIOLATION, (
        "this gate does not trip its own condition 5, which is how the first "
        "version shipped. See the comment on EXPLICIT_CONDITION_5."
    )


# --------------------------------------------------------------------------
# The comparison against the body
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_a_body_that_NAMES_the_condition_passes() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result = _run(
            pathlib.Path(tmp),
            "apps/api/app/config.py\n",
            "## Merge rule\n\nTrips condition 5 (the redactor switch).\n",
        )
    assert result.returncode == EXIT_OK, result.stderr


@pytest.mark.unit
def test_a_number_OUTSIDE_the_merge_rule_section_does_not_satisfy_it() -> None:
    """The scoping, without which any PR mentioning a 5 anywhere passes.

    A body carrying "prettier@3.9.5" or "fixes 5 sites" would otherwise
    acknowledge condition 5 by accident -- a gate satisfied by an unrelated
    digit is the containment-assertion defect (#72) in a different costume.
    """
    import tempfile

    body = "## Summary\n\nThis fixes 5 separate sites.\n\n## Merge rule\n\nTrips nothing.\n"
    with tempfile.TemporaryDirectory() as tmp:
        result = _run(pathlib.Path(tmp), "apps/api/app/config.py\n", body)
    assert result.returncode == EXIT_VIOLATION, (
        "a '5' in the Summary satisfied condition 5. The check must read only "
        "the merge-rule region when one exists."
    )


@pytest.mark.unit
def test_a_body_with_NO_merge_rule_heading_falls_back_to_the_whole_body() -> None:
    """Deliberate, and stated so it is not read as a bug.

    A PR that discusses the conditions in prose without a heading is being
    honest, and failing it would teach people to add a heading rather than to
    think about the paths. The scoping above applies only when a heading exists.
    """
    import tempfile

    body = "## Summary\n\nThis trips condition 5 because it edits the redactor switch.\n"
    with tempfile.TemporaryDirectory() as tmp:
        result = _run(pathlib.Path(tmp), "apps/api/app/config.py\n", body)
    assert result.returncode == EXIT_OK, result.stderr


@pytest.mark.unit
def test_15_does_not_satisfy_condition_5() -> None:
    """The lookarounds, pinned. `15` contains `5`."""
    import tempfile

    body = "## Merge rule\n\nSee the 15 findings; trips nothing.\n"
    with tempfile.TemporaryDirectory() as tmp:
        result = _run(pathlib.Path(tmp), "apps/api/app/config.py\n", body)
    assert result.returncode == EXIT_VIOLATION


@pytest.mark.unit
def test_BOTH_conditions_must_be_named_when_both_are_tripped() -> None:
    """Naming one of two is the partial-honesty case, and it must fail.

    Without this, a body saying "trips condition 5" over a diff that also adds
    a migration would pass -- and condition 4 is the one the human most needs
    to see.
    """
    import tempfile

    changed = "apps/api/alembic/versions/0099_x.py\napps/api/app/config.py\n"
    body = "## Merge rule\n\nTrips condition 5.\n"
    with tempfile.TemporaryDirectory() as tmp:
        result = _run(pathlib.Path(tmp), changed, body)
    assert result.returncode == EXIT_VIOLATION
    assert "condition(s) 4" in result.stderr, result.stderr


# --------------------------------------------------------------------------
# Could not look. Every one of these is 2, never 0.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_an_EMPTY_changed_file_list_is_2_not_0() -> None:
    """The `is_code_change([])` shape, refused explicitly.

    An empty diff is not a clean diff -- it is a checkout that did not fetch
    enough history. Reading it as "no gated paths" is the false green this gate
    exists to avoid.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result = _run(pathlib.Path(tmp), "", SILENT_BODY)
    assert result.returncode == EXIT_COULD_NOT_LOOK, result.stdout
    assert "EMPTY" in result.stderr


@pytest.mark.unit
@pytest.mark.parametrize(
    ("changed", "body", "extra", "label"),
    [
        (None, SILENT_BODY, (), "no --changed-files"),
        ("x\n", None, (), "no --body"),
        ("x\n", SILENT_BODY, ("--bogus",), "an unknown flag"),
        (None, None, (), "no arguments at all"),
    ],
)
def test_unreadable_or_unparseable_input_is_2(changed, body, extra, label) -> None:
    """An ignored flag is how a gate reports clean having read nothing (#343)."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result = _run(pathlib.Path(tmp), changed, body, *extra)
    assert result.returncode == EXIT_COULD_NOT_LOOK, f"{label}: {result.stdout} {result.stderr}"


@pytest.mark.unit
def test_a_missing_input_FILE_is_2() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        args = [
            sys.executable,
            str(SCRIPT),
            "--changed-files",
            str(pathlib.Path(tmp) / "nope.txt"),
            "--body",
            str(pathlib.Path(tmp) / "also-nope.md"),
        ]
        result = subprocess.run(  # noqa: S603
            args, capture_output=True, text=True, encoding="utf-8", timeout=120
        )
    assert result.returncode == EXIT_COULD_NOT_LOOK, result.stdout
