"""The LEAVE-row oracle's registry gate must be able to fail.

Written with the gate, per the CLAUDE.md rule about shipping a checker without
one -- and this gate exists BECAUSE of that rule's other half: the oracle is a
tool, not a gate, and SOME of its properties can fail honestly on input nobody
configured. This file pins the registry one: a LEAVE table with no registered
guards.

It said "exactly one" until #221 added a second -- the label check, which
verifies that a table declared not-LEAVE really holds no LEAVE rows. That one is
pinned in `test_leave_row_oracle_labels.py`, and the count is deliberately not
restated here: a number in a docstring describing a population that grows is how
this one went stale.

The oracle itself is deliberately not tested here. Scoring a LEAVE row
pass/fail needs judgement about what the row was written to exercise, so the
oracle reports and a human decides. A test asserting the oracle's verdicts would
be asserting my reading of 104 rows, which is the thing the oracle exists to
replace.
"""

from __future__ import annotations

import pytest
from scripts.leave_row_oracle import (
    NOT_LEAVE_TABLES,
    TABLE_GUARDS,
    check_registry,
    discover_tables,
    leave_rows,
)


@pytest.mark.unit
def test_a_table_with_no_registered_guards_fails_the_gate(monkeypatch) -> None:
    """The rot case: someone adds a LEAVE table and wires up nothing.

    Without this the oracle reports clean over it, because a table with no
    guards has no mutation that could kill its rows -- "I could not look"
    wearing the output of "nothing to complain about".
    """
    rows = [("A_BRAND_NEW_TABLE", "some row", "text")]
    monkeypatch.setitem(TABLE_GUARDS, "A_BRAND_NEW_TABLE", [])

    assert check_registry(rows) == 1


@pytest.mark.unit
def test_a_table_absent_from_the_registry_entirely_also_fails(monkeypatch) -> None:
    """Absent and empty must land in the SAME branch.

    An empty list is a decision someone recorded; a missing key is a table
    nobody thought about. The second is the more likely and the more dangerous.

    Note what this test had to change to keep meaning something. It used to
    pass a fake ROW list, because `check_registry` derived its universe from
    the rows -- i.e. from the same hand list it was gating, so a table nobody
    enumerated was invisible to both. The universe is now DISCOVERED from the
    matrix modules, so the fake has to be injected there instead. The test
    going red on that change was the gate's own hole surfacing.
    """
    real = discover_tables()
    monkeypatch.setattr(
        "scripts.leave_row_oracle.discover_tables",
        lambda: {**real, "NEVER_REGISTERED": 3},
    )
    assert "NEVER_REGISTERED" not in TABLE_GUARDS
    assert "NEVER_REGISTERED" not in NOT_LEAVE_TABLES

    assert check_registry(leave_rows()) == 1


@pytest.mark.unit
def test_the_real_registry_is_currently_complete() -> None:
    """Every LEAVE table in the two truth-table files has guards registered.

    Derived from the tables themselves rather than from a hardcoded count, so
    adding a table to either matrix file turns this red until it is registered
    -- which is the whole point of the gate and would not be true of an
    assertion against a fixed number.
    """
    rows = leave_rows()
    tables = {t for t, _, _ in rows}
    assert tables, "no LEAVE tables discovered -- the collector is broken, not clean"

    unregistered = sorted(t for t in tables if not TABLE_GUARDS.get(t))
    assert not unregistered, f"LEAVE tables with no registered guards: {unregistered}"
    assert check_registry(rows) == 0


@pytest.mark.unit
def test_a_missing_anchor_is_cannot_measure_and_not_a_system_exit() -> None:
    """The oracle's two escapes used to raise `SystemExit(str)`, which exits 1.

    Both are "cannot measure" conditions -- a mutation anchor that no longer
    matches `redact.py`, and a mutation that turns out to be a no-op -- and
    every other such branch in the file returns 2. Raising `SystemExit` put them
    on the code this repo reserves for "violations found", and `SystemExit` is
    also the one exception the `__main__` crash handler re-raises untouched by
    design, so the handler could never have caught them.

    `_line_containing` is exercised directly because the end-to-end route runs
    the whole LEAVE corpus twice before it reaches `build_mutations`.
    """
    from scripts.leave_row_oracle import CannotMeasure, _line_containing

    assert not issubclass(CannotMeasure, SystemExit), (
        "CannotMeasure must not be a SystemExit: the crash handler re-raises"
        " SystemExit untouched, so the exit code would be 1 again"
    )

    source = "alpha = 1\nbeta = 2\n"
    assert _line_containing(source, "beta") == "beta = 2"

    with pytest.raises(CannotMeasure, match="anchor not found"):
        _line_containing(source, "gamma")


@pytest.mark.unit
@pytest.mark.parametrize(
    "argv",
    [
        ["leave_row_oracle.py", "--check-registy"],
        ["leave_row_oracle.py", "--check-registry", "--extra"],
        ["leave_row_oracle.py", "tests"],
    ],
    ids=["typo", "trailing-unknown", "bare-word"],
)
def test_an_unrecognised_argument_cannot_look(argv) -> None:
    """A flag this script does not implement must not SUCCEED.

    `main` selected its mode with `if "--check-registry" in argv` -- a
    MEMBERSHIP test, so every other argument fell through to the report path
    and returned 0. A typo in `ci.yml`'s "LEAVE-row oracle registry and
    labels" step would have run the REPORT and passed the step, with the
    registry check that step exists for never executing and nothing to see.

    Exit 2 rather than 1, deliberately: an argument the script cannot
    interpret means it did not look, which is a fact about the instrument and
    not about the code.

    The `--check-registry --extra` case is the one a single membership test
    cannot catch at all, and the bare word is the shape that reads most like a
    path argument the script might accept.
    """
    from scripts.leave_row_oracle import main

    assert main(argv) == 2


@pytest.mark.unit
@pytest.mark.parametrize(
    "argv",
    [["leave_row_oracle.py"], ["leave_row_oracle.py", "--check-registry"]],
    ids=["report", "check-registry"],
)
def test_both_real_modes_reach_the_work(argv, monkeypatch) -> None:
    """THE PASSING HALF. A guard observed only firing is not observed.

    Proves the argument is RECOGNISED without letting either mode run: the
    first thing `main` does after the dispatch is call `leave_rows()`, so
    stubbing that to raise a sentinel means reaching it proves the dispatch
    let the argument through, and a `2` would prove it did not.

    THE STUB IS NOT A CONVENIENCE. A first draft called `main` for real and
    turned three tests in `test_leave_row_oracle_labels.py` red -- measured,
    and only when the two files ran TOGETHER, which is why running this file
    alone looked clean. The report path does
    `REDACT.write_text(original, ...)`: it REWRITES `redact.py` on disk, and
    the labels tests read what it wrote. A test that rewrites a source file
    mid-suite is the escaped-listener shape `test_a_row_dropped_between_add_
    and_flush_is_recorded` guards against in the risk suite, arriving from the
    other direction.

    Asserting recognition rather than the exit code also keeps this test out
    of the business of whether the registry currently passes, which is
    `test_the_real_registry_is_currently_complete`'s job.
    """
    import scripts.leave_row_oracle as oracle

    class _Reached(Exception):
        pass

    def _boom():
        raise _Reached

    monkeypatch.setattr(oracle, "leave_rows", _boom)
    with pytest.raises(_Reached):
        oracle.main(argv)
