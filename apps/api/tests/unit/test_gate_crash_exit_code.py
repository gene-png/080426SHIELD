"""A gate that crashes must not report a verdict it never reached.

Every gate in this repo returns 1 for "violations found" and 2 for "I could not
look" (D-051). Python exits 1 on an unhandled exception, so an uncaught error
inside `main` was indistinguishable from a finding: the same exit code, the same
red X, and a log that reads like a verdict. Gene confirmed the shape by running
a patched copy of `check_plan_totals.py` -- exit 1, traceback on stderr.

The expected value comes from the CONVENTION rather than from the scripts: 2 is
what all eight already return for an anticipated failure to read their input.
Nothing here reads a constant out of the module under test.

Each gate is exercised twice. Once with its real `__main__` block, asserting 2;
once with that block reverted to the bare `raise SystemExit(main(...))` it used
to carry, asserting 1. The second half is what stops this from being a test that
cannot fail -- delete the handler and the first assertion has to break, because
the second one pins what the world looks like without it.

`CLAUDE.md` records that a revert which silently fails to apply reports the same
green as a test that cannot fail, so every mutation asserts its own anchor count
before the subprocess runs.

The mutant is written beside the original, never into a temp directory: these
scripts resolve their inputs from `Path(__file__).resolve().parents[N]`, so a
copy anywhere else is a different program.
"""

from __future__ import annotations

import signal
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
API_ROOT = SCRIPTS.parent

# (module stem, the argv expression its __main__ block passes to main)
GATES = [
    ("check_audit_evidence", ""),
    ("check_issue_references", ""),
    ("check_no_control_chars", "sys.argv"),
    ("check_plan_totals", "sys.argv"),
    ("check_recalled_counts", "sys.argv"),
    ("check_separator_classes", "sys.argv"),
    ("check_test_integrity", "sys.argv"),
    ("leave_row_oracle", "sys.argv"),
]

MARKER = 'if __name__ == "__main__":'
# The handler's own line, not the word "CRASHED" -- one gate's docstring
# narrates a real crash and contains that word in prose.
HANDLER = "crash != verdict"
CRASH = 'def main(*_args, **_kwargs):\n    raise RuntimeError("injected crash")\n\n\n'


def _mutate(source: str, argv: str, *, guarded: bool) -> str:
    """Replace `main` with a raiser, keeping or reverting the crash handler."""
    assert source.count(MARKER) == 1, f"expected one {MARKER!r}, found {source.count(MARKER)}"
    head, _sep, _tail = source.partition(MARKER)
    block = (
        source[source.index(MARKER) :]
        if guarded
        else f"{MARKER}\n    raise SystemExit(main({argv}))\n"
    )
    return head + CRASH + block


def _run(stem: str, source: str) -> subprocess.CompletedProcess[str]:
    mutant = SCRIPTS / f"_crashmutant_{stem}.py"
    mutant.write_text(source, encoding="utf-8")
    try:
        # noqa justified: every argument is built in this file from a
        # repo-relative path and `sys.executable`. There is no untrusted
        # input, and running the gate as a real process is the point --
        # importing it would not exercise the `__main__` block at all.
        return subprocess.run(  # noqa: S603
            [sys.executable, str(mutant)],
            capture_output=True,
            text=True,
            cwd=str(API_ROOT),
            timeout=120,
        )
    finally:
        mutant.unlink(missing_ok=True)


@pytest.mark.unit
@pytest.mark.parametrize(("stem", "argv"), GATES, ids=[g[0] for g in GATES])
def test_a_crash_exits_2_not_1(stem: str, argv: str) -> None:
    """An unhandled exception inside `main` must exit 2, never 1."""
    source = (SCRIPTS / f"{stem}.py").read_text(encoding="utf-8")
    mutated = _mutate(source, argv, guarded=True)
    assert mutated != source, f"{stem}: the crash injection did not apply"
    assert (
        HANDLER in mutated[mutated.index(MARKER) :]
    ), f"{stem}: the mutant lost the crash handler before it ran"

    result = _run(stem, mutated)

    assert result.returncode == 2, (
        f"{stem}: a crash exited {result.returncode}, not 2." f" stderr: {result.stderr[-400:]}"
    )
    assert (
        "CRASHED" in result.stderr
    ), f"{stem}: exit 2 without the crash notice: {result.stderr[-400:]}"
    assert "RuntimeError" in result.stderr, (
        f"{stem}: exit 2 did not come from the injected crash, so this case"
        f" proves nothing. stderr: {result.stderr[-400:]}"
    )


@pytest.mark.unit
@pytest.mark.parametrize(("stem", "argv"), GATES, ids=[g[0] for g in GATES])
def test_without_the_handler_the_same_crash_exits_1(stem: str, argv: str) -> None:
    """The revert, so the case above is discriminating rather than merely green.

    This is the defect as it stood: the identical crash, under the bare
    `raise SystemExit(main(...))`, reports the exit code this repo reserves for
    "violations found".
    """
    source = (SCRIPTS / f"{stem}.py").read_text(encoding="utf-8")
    reverted = _mutate(source, argv, guarded=False)
    assert reverted != source, f"{stem}: the revert did not apply"
    assert (
        HANDLER not in reverted[reverted.index(MARKER) :]
    ), f"{stem}: the revert left the handler in place"

    result = _run(stem, reverted)

    assert result.returncode == 1, (
        f"{stem}: the unguarded crash exited {result.returncode}, not 1 --"
        f" the revert may not have landed. stderr: {result.stderr[-400:]}"
    )
    assert "RuntimeError" in result.stderr, f"{stem}: no traceback from the injected crash"


INTERRUPT = "def main(*_args, **_kwargs):\n    raise KeyboardInterrupt\n\n\n"
DELIBERATE_EXIT = "def main(*_args, **_kwargs):\n    raise SystemExit(3)\n\n\n"


def _inject(source: str, replacement: str) -> str:
    """Swap `main` for `replacement`, keeping the gate's real `__main__` block."""
    assert source.count(MARKER) == 1, f"expected one {MARKER!r}, found {source.count(MARKER)}"
    head, _sep, _tail = source.partition(MARKER)
    return head + replacement + source[source.index(MARKER) :]


@pytest.mark.unit
@pytest.mark.parametrize(("stem", "argv"), GATES, ids=[g[0] for g in GATES])
def test_an_interrupt_propagates_and_is_not_reported_as_could_not_look(
    stem: str, argv: str
) -> None:
    """Ctrl-C is not a gate failing to read its input.

    The handler catches `BaseException`, which without an explicit re-raise
    would swallow `KeyboardInterrupt` into exit 2 and tell an operator who knows
    exactly what they did that the gate could not look. 130 is the convention
    that says otherwise.

    This is also what stops the next person simplifying `BaseException` to
    `Exception`: the two forms are behaviourally identical here BECAUSE of the
    re-raise, so the choice is about naming what the handler declines to
    swallow. Undo the re-raise and this case goes red rather than silently
    changing what an interrupt means.
    """
    source = (SCRIPTS / f"{stem}.py").read_text(encoding="utf-8")
    mutated = _inject(source, INTERRUPT)
    assert mutated != source, f"{stem}: the interrupt injection did not apply"

    result = _run(stem, mutated)

    assert result.returncode != 2, (
        f"{stem}: an interrupt was reported as 'could not look' (exit 2)."
        f" stderr: {result.stderr[-400:]}"
    )
    # Two encodings of one fact. CPython re-raises SIGINT rather than returning
    # a code, so the process DIES from the signal: `subprocess` reports that as
    # -SIGINT, a shell reports the same death as 128+SIGINT. Accepting both pins
    # the outcome without pinning the reporting convention of whatever runs it.
    assert result.returncode in (-signal.SIGINT, 128 + signal.SIGINT), (
        f"{stem}: an interrupt exited {result.returncode}, which is neither"
        f" -SIGINT nor 128+SIGINT. stderr: {result.stderr[-400:]}"
    )
    assert "CRASHED" not in result.stderr, f"{stem}: the crash handler claimed an interrupt"


@pytest.mark.unit
@pytest.mark.parametrize(("stem", "argv"), GATES, ids=[g[0] for g in GATES])
def test_a_deliberate_system_exit_keeps_its_own_code(stem: str, argv: str) -> None:
    """A `SystemExit` raised inside `main` is somebody's decision, not a crash.

    Pinned with 3 rather than 1 or 2 so the assertion cannot be satisfied by
    either of this repo's two real exit codes -- if the handler swallowed and
    relabelled it, the code would change and this case would say so.
    """
    source = (SCRIPTS / f"{stem}.py").read_text(encoding="utf-8")
    mutated = _inject(source, DELIBERATE_EXIT)
    assert mutated != source, f"{stem}: the SystemExit injection did not apply"

    result = _run(stem, mutated)

    assert result.returncode == 3, (
        f"{stem}: a deliberate SystemExit(3) became exit {result.returncode}."
        f" stderr: {result.stderr[-400:]}"
    )
    assert "CRASHED" not in result.stderr, f"{stem}: the crash handler claimed a deliberate exit"
