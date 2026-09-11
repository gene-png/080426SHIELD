"""The NOT_LEAVE labels are checked, not trusted (#221).

`NOT_LEAVE_TABLES` is a set of LABELS and nothing verified them. A table
mislabelled not-LEAVE is invisible to the oracle twice over: its rows are never
scored, and `--check-registry` reports the registry COMPLETE, because the name
is accounted for. The gate confirmed what somebody had written down.

## What the check found on its first run

Three rows inside `IDEMPOTENCE_CASES` -- a table declared not-LEAVE on the
reasonable ground that it is about idempotence rather than survival -- that the
redactor leaves byte-identical. They are LEAVE rows in substance, they were
never measured, and two of the three turned out to be in the risk class once
they were: one pinned by `addr/no-sep-branch-requires-digit` and one defended in
depth. That is coverage the corpus had and could not see.

They are now collected by `idempotence_noop_rows()`, which is the remedy the
check's own message names. Exempting them would have left them unmeasured with
a reason attached.

## Why these tests exist in this shape

Per #213 tier 1, a check ships with a fixture that makes it go RED. The
oracle is structurally unfixturable through `tests/gates/` -- `check_gate_fixtures.py`
records why: it takes no path, and `REPO_APP`/`TESTS` are derived from
`__file__`. So the red-making fixture is injected here, which is the same route
`test_leave_row_oracle_registry.py` uses for the registry gate.

Both states are exercised. Watching a guard fire proves it fires, not that it
passes, and a label check that fails on the real tree would block every run.
"""

from __future__ import annotations

import pytest
from scripts.leave_row_oracle import (
    NOOP_LABEL,
    NOT_LEAVE_TABLES,
    UNREADABLE_NOT_LEAVE,
    _matrix_modules,
    _module_context,
    check_labels,
    idempotence_noop_rows,
    leave_rows,
    not_leave_row_findings,
    survives,
)

#: Prose no rule in the redactor touches, under either call. Verified by running
#: it, not by looking at the patterns -- the corpus this repo keeps getting
#: wrong is the one written from what its author expects the rules to do.
INERT_PROSE = "Ordinary prose with no designator in it."


@pytest.mark.unit
def test_the_real_tables_are_all_accounted_for() -> None:
    """THE PASSING STATE, on the tree as it stands.

    Without this the check is only ever observed firing, and a predicate that
    halts unconditionally is indistinguishable from one that found something.
    """
    findings, unreadable, missing = not_leave_row_findings()
    assert missing == []
    assert findings == [], (
        "a table declared NOT_LEAVE holds rows the redactor leaves alone. Collect "
        "them as LEAVE rows -- see `idempotence_noop_rows()` for the shape -- "
        "rather than exempting them."
    )
    assert sorted(unreadable) == sorted(UNREADABLE_NOT_LEAVE)
    assert check_labels() == 0


@pytest.mark.unit
def test_a_not_leave_table_holding_a_leave_row_fails(monkeypatch) -> None:
    """THE RED-MAKING FIXTURE (#213 tier 1).

    A table declared not-LEAVE containing one obvious LEAVE row. This is the
    whole point of the check: before it, such a table was reported clean by
    `--check-registry` precisely BECAUSE somebody had declared it.
    """
    module, _ = _matrix_modules()
    monkeypatch.setattr(module, "A_MISLABELLED_TABLE", [("inert", INERT_PROSE)], raising=False)
    monkeypatch.setitem(NOT_LEAVE_TABLES, "A_MISLABELLED_TABLE", "fixture for #221")

    findings, _unreadable, _missing = not_leave_row_findings()
    assert ("A_MISLABELLED_TABLE", "inert", INERT_PROSE) in findings
    assert check_labels() == 1


@pytest.mark.unit
def test_a_redact_row_in_that_table_is_not_a_finding(monkeypatch) -> None:
    """The check must not fire on a table doing its job.

    The negative control for the fixture above: same injected table, a row the
    redactor actually rewrites, and nothing reported. A check that flagged both
    would be flagging the TABLE rather than the row.
    """
    module, _ = _matrix_modules()
    monkeypatch.setattr(module, "A_REAL_REDACT_TABLE", [("suite", "Suite 400")], raising=False)
    monkeypatch.setitem(NOT_LEAVE_TABLES, "A_REAL_REDACT_TABLE", "fixture for #221")

    findings, _unreadable, _missing = not_leave_row_findings()
    assert [f for f in findings if f[0] == "A_REAL_REDACT_TABLE"] == []
    assert check_labels() == 0


@pytest.mark.unit
def test_a_collected_leave_row_is_not_reported_twice(monkeypatch) -> None:
    """The remedy the message names actually clears the finding.

    A row whose text some LEAVE table already collects is measured, so it is not
    a finding wherever else it appears. Without this the only way to clear a
    report would be an exemption, and the check would teach the opposite of what
    it is for.
    """
    collected = next(text for _t, _r, text in leave_rows())
    module, _ = _matrix_modules()
    monkeypatch.setattr(module, "A_DUPLICATE_TABLE", [("dup", collected)], raising=False)
    monkeypatch.setitem(NOT_LEAVE_TABLES, "A_DUPLICATE_TABLE", "fixture for #221")

    findings, _unreadable, _missing = not_leave_row_findings()
    assert [f for f in findings if f[0] == "A_DUPLICATE_TABLE"] == []


@pytest.mark.unit
def test_an_undeclared_unreadable_table_is_cannot_look(monkeypatch) -> None:
    """`2`, not `0` and not `1`.

    A table whose rows carry no text cannot be classified at all. Reporting that
    as clean is "I could not look" wearing "nothing to complain about"; reporting
    it as a violation names rows that do not exist.
    """
    module, _ = _matrix_modules()
    monkeypatch.setattr(module, "A_SHAPELESS_TABLE", [("id", True, "why")], raising=False)
    monkeypatch.setitem(NOT_LEAVE_TABLES, "A_SHAPELESS_TABLE", "fixture for #221")

    _findings, unreadable, _missing = not_leave_row_findings()
    assert "A_SHAPELESS_TABLE" in unreadable
    assert check_labels() == 2


@pytest.mark.unit
def test_a_stale_unreadable_declaration_is_also_cannot_look(monkeypatch) -> None:
    """The OTHER direction, and it is the half that would have rotted.

    A one-directional list only ever suppresses reports: it keeps saying "cannot
    look" long after the table's shape changed and the classifier could have
    looked, and nothing would ever say so. Declaring a readable table unreadable
    must fail exactly as the reverse does.
    """
    readable = next(t for t in NOT_LEAVE_TABLES if t not in UNREADABLE_NOT_LEAVE)
    monkeypatch.setitem(
        UNREADABLE_NOT_LEAVE, readable, "a declaration that has outlived its reason"
    )

    assert check_labels() == 2


@pytest.mark.unit
def test_a_declared_table_that_no_longer_exists_is_cannot_look(monkeypatch) -> None:
    """A declaration pointing at nothing is not a clean result either."""
    monkeypatch.setitem(NOT_LEAVE_TABLES, "A_TABLE_THAT_WAS_DELETED", "fixture for #221")

    _findings, _unreadable, missing = not_leave_row_findings()
    assert missing == ["A_TABLE_THAT_WAS_DELETED"]
    assert check_labels() == 2


@pytest.mark.unit
def test_the_module_context_the_classifier_relies_on_still_exists() -> None:
    """A rename must go RED here rather than quietly weakening the classifier.

    `_module_context` reads `_ORG` and `_HINTS` off the address matrix, which is
    the context that module's own idempotence test passes. If either is renamed,
    `getattr` returns None, the informed call collapses into the bare one, and
    the check starts reporting rows that the table's own call redacts -- noise,
    which is how a check gets suppressed. Silent degradation, so it is pinned.
    """
    module, _ = _matrix_modules()
    context = _module_context(module)
    assert "client_org_name" in context, "`_ORG` is gone from the address matrix module"
    assert "name_hints" in context, "`_HINTS` is gone from the address matrix module"


@pytest.mark.unit
def test_the_informed_call_is_load_bearing() -> None:
    """Deleting the second call turns the check into a noise generator.

    `IDEMPOTENCE_CASES` holds rows that survive the BARE call and are redacted
    under the table's own call -- the org-name rows. Requiring survival under
    both is what keeps them out of the findings. Nothing else in this file would
    notice if that call were removed, because its effect is rows NOT reported.
    """
    module, _ = _matrix_modules()
    context = _module_context(module)

    # Derived, not listed: rows the BARE call leaves alone and the INFORMED
    # call rewrites. Those are exactly the rows the second call removes from the
    # findings, and naming them would go stale the next time the table grows.
    #
    # Note it is a SUBSET of the org rows, not all of them. `Northwind SOC
    # Platform, Suite 400` is redacted by the bare call as well, through the
    # suite rule -- so a test asserting the property of every org row fails on a
    # row that simply has a second reason to redact.
    discriminating = [
        (rid, text)
        for rid, text in module.IDEMPOTENCE_CASES
        if not rid.startswith(NOOP_LABEL) and survives(text, {}) and not survives(text, context)
    ]
    assert discriminating, (
        "no row survives the bare call and is redacted under the module's own "
        "context, so nothing here would notice if the informed call were "
        "deleted. Either the table changed or the second call is now dead code."
    )


@pytest.mark.unit
def test_the_noop_rows_are_selected_by_label_and_not_by_survival() -> None:
    """The collector and the check must not share a criterion.

    If `idempotence_noop_rows()` picked rows by running the redactor, the label
    check could never fail on this table: the collector would define exactly the
    set the check exempts, and the two would agree by construction. That is
    #72's shape, in the tool built to find it.

    So the label is one claim, the redactor is the other, and this test pins the
    provenance of the first.
    """
    rows = idempotence_noop_rows()
    assert rows, "no `no-op:` rows collected -- the label or the collector moved"
    assert all(rid.startswith(NOOP_LABEL) for rid, _text in rows)

    module, _ = _matrix_modules()
    labelled = {rid for rid, _t in module.IDEMPOTENCE_CASES if rid.startswith(NOOP_LABEL)}
    assert {rid for rid, _t in rows} == labelled

    # And the two claims agree TODAY. A `no-op:` row the redactor rewrites is a
    # finding in the other direction -- the label is wrong -- and it is worth
    # saying out loud rather than leaving to be inferred from a clean run.
    context = _module_context(module)
    mislabelled = [rid for rid, text in rows if not survives(text, context)]
    assert mislabelled == [], (
        f"rows labelled `{NOOP_LABEL}` that the redactor actually rewrites: "
        f"{mislabelled}. The label claims a no-op the code does not perform."
    )


@pytest.mark.unit
def test_the_noop_rows_are_now_measured_by_the_oracle() -> None:
    """The fix, not just the finding: the rows reach the mutation corpus.

    Collecting them is what makes the finding go away, so this asserts the thing
    that actually changed. Without it, the check could be cleared by editing the
    registry and nothing would notice.
    """
    tables = {table for table, _rid, _text in leave_rows()}
    assert "IDEMPOTENCE_NOOP" in tables

    texts = {text for table, _rid, text in leave_rows() if table == "IDEMPOTENCE_NOOP"}
    assert texts == {text for _rid, text in idempotence_noop_rows()}
