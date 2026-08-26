"""The LEAVE-row oracle's registry gate must be able to fail.

Written with the gate, per the CLAUDE.md rule about shipping a checker without
one -- and this gate exists BECAUSE of that rule's other half: the oracle is a
tool, not a gate, and exactly one of its properties can fail honestly on input
nobody configured. That property is what these tests pin.

The oracle itself is deliberately not tested here. Scoring a LEAVE row
pass/fail needs judgement about what the row was written to exercise, so the
oracle reports and a human decides. A test asserting the oracle's verdicts would
be asserting my reading of 104 rows, which is the thing the oracle exists to
replace.
"""

from __future__ import annotations

import pytest
from scripts import leave_row_oracle as O


@pytest.mark.unit
def test_a_table_with_no_registered_guards_fails_the_gate(monkeypatch) -> None:
    """The rot case: someone adds a LEAVE table and wires up nothing.

    Without this the oracle reports clean over it, because a table with no
    guards has no mutation that could kill its rows -- "I could not look"
    wearing the output of "nothing to complain about".
    """
    rows = [("A_BRAND_NEW_TABLE", "some row", "text")]
    monkeypatch.setitem(O.TABLE_GUARDS, "A_BRAND_NEW_TABLE", [])

    assert O.check_registry(rows) == 1


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
    real = O.discover_tables()
    monkeypatch.setattr(O, "discover_tables", lambda: {**real, "NEVER_REGISTERED": 3})
    assert "NEVER_REGISTERED" not in O.TABLE_GUARDS
    assert "NEVER_REGISTERED" not in O.NOT_LEAVE_TABLES

    assert O.check_registry(O.leave_rows()) == 1


@pytest.mark.unit
def test_the_real_registry_is_currently_complete() -> None:
    """Every LEAVE table in the two truth-table files has guards registered.

    Derived from the tables themselves rather than from a hardcoded count, so
    adding a table to either matrix file turns this red until it is registered
    -- which is the whole point of the gate and would not be true of an
    assertion against a fixed number.
    """
    rows = O.leave_rows()
    tables = {t for t, _, _ in rows}
    assert tables, "no LEAVE tables discovered -- the collector is broken, not clean"

    unregistered = sorted(t for t in tables if not O.TABLE_GUARDS.get(t))
    assert not unregistered, f"LEAVE tables with no registered guards: {unregistered}"
    assert O.check_registry(rows) == 0
