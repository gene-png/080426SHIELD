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
def test_the_guard_reads_the_FLAGS_TUPLE_and_not_a_literal(monkeypatch, capsys) -> None:
    """Registering a flag must be ONE edit, and this is what makes that true.

    The guard was `a != _CHECK_REGISTRY`: correct, and correct only while there
    is exactly one flag. The next flag has to be added in two places, and the
    failure when it is added in one is not a syntax error -- the guard rejects
    a flag the script implements, with a confident message naming the only flag
    it believes in.

    #382 is that next flag. It adds `--check-anchors` and wires it into
    `ci.yml`, and the two branches merge clean because they touch different
    hunks of `main`, so git cannot see the collision. `main` would go
    permanently red on the step whose job is to report whether the oracle can
    still measure.

    Emptying `_FLAGS` must make the one flag that exists today be REFUSED. If
    it is not, the guard is reading a literal and the tuple is decoration.

    Safe to run: every assertion here lands on the exit-2 path, which returns
    before `leave_rows()` and therefore before the report path that REWRITES
    `redact.py` on disk -- the hazard the test above documents.
    """
    import scripts.leave_row_oracle as oracle

    monkeypatch.setattr(oracle, "_FLAGS", ())
    assert oracle.main(["leave_row_oracle.py", oracle._CHECK_REGISTRY]) == 2

    # And the message enumerates from the same tuple, so it cannot advertise a
    # set the guard is not enforcing.
    monkeypatch.setattr(oracle, "_FLAGS", ("--alpha", "--beta"))
    assert oracle.main(["leave_row_oracle.py", "--gamma"]) == 2
    err = capsys.readouterr().err
    assert "--alpha, --beta" in err
    assert "--gamma" in err


@pytest.mark.unit
@pytest.mark.parametrize(
    "argv",
    [["leave_row_oracle.py"], ["leave_row_oracle.py", "--check-registry"]],
    ids=["report", "check-registry"],
)
def test_both_real_arguments_are_accepted(argv, monkeypatch) -> None:
    """THE PASSING HALF. A guard observed only firing is not observed.

    RENAMED from "both real modes reach the work", which was wider than what
    this establishes. The two modes diverge at the dispatch, which is AFTER
    `leave_rows()` -- so the stub raises before the branch is evaluated and
    the two parametrizations execute byte-identical code. Two names over one
    path. What it proves is ACCEPTANCE; routing is the next test's job.

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


@pytest.mark.unit
def test_the_registry_argument_actually_routes_to_the_registry_checks(monkeypatch) -> None:
    """THE ROUTING, which nothing covered.

    `test_the_real_registry_is_currently_complete` calls `check_registry(rows)`
    DIRECTLY and never touches `main`, so no test asserted that
    `--check-registry` reaches it. `CLAUDE.md`: the tell is that a test imports
    the thing it is defending rather than calling what reaches it.

    Why it matters concretely: the flag was TWO independent literals for one
    round -- the guard's allow-list and the dispatch. Rename the dispatch alone
    and `--check-registry` is accepted by the guard, matches nothing, falls to
    the REPORT path and returns 0, with CI's registry step green having run
    neither check. Every other test in this file stays green through that.

    Both checks are asserted, not just one: `main` returns `max(registry,
    labels)`, so stubbing only the first would let the second be dropped.
    """
    import scripts.leave_row_oracle as oracle

    called = []
    monkeypatch.setattr(oracle, "leave_rows", lambda: ["a-row"])
    monkeypatch.setattr(
        oracle, "check_registry", lambda rows: called.append(("registry", rows)) or 0
    )
    monkeypatch.setattr(oracle, "check_labels", lambda: called.append(("labels",)) or 0)

    assert oracle.main(["leave_row_oracle.py", "--check-registry"]) == 0
    assert [c[0] for c in called] == ["registry", "labels"], (
        "the registry argument must route to BOTH checks; got " f"{called}"
    )
    assert called[0][1] == ["a-row"], "check_registry must receive the rows main read"
