"""`llm_calls.redaction_mode` must record what actually happened (#144).

The audit row's stated job is proving the redactor ran. Before 0046 it could not:
with `SHIELD_REDACTION_MODE=off` the redactor returns the input unchanged and
`redacted_counts` stores NULL, byte-identical to a run that executed and found
nothing to remove. `llm_calls.mode` is fixture-vs-live, a different axis.

Two properties, and the second is the one that is easy to lose later:

  1. The mode is recorded, for every mode.
  2. NULL means NOT RECORDED and is never coerced to a default. A pre-0046 row
     has an unknown mode; writing "strict" onto it would fabricate a record in
     the table whose purpose is proving what happened.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

from app.models.llm_call import LLMCall


@pytest.mark.unit
def test_the_column_is_nullable_with_no_server_default() -> None:
    """A DB default would manufacture exactly the value 0046 declines to.

    It would also apply to every future writer that forgets to set the field,
    which is the silent half: the row would look recorded and be a guess.
    """
    col = inspect(LLMCall).columns["redaction_mode"]
    assert col.nullable is True
    assert col.server_default is None, (
        "a server default fabricates the mode for pre-0046 rows and for any "
        "writer that forgets to set it"
    )
    assert col.default is None, "a client-side default has the same effect"


@pytest.mark.unit
def test_nothing_updates_the_column_after_insert() -> None:
    """Write-once, unlike `status` / tokens / `duration_ms` on the same row.

    The mode is known before the provider is called and the row is inserted with
    it, so a call that fails or is killed still records what was egressed --
    which is exactly when that matters. A later assignment would mean a failed
    call could carry a mode it never ran under.

    Asserted over the SOURCE because the property is "no code path does this",
    which no single execution can demonstrate.
    """
    from pathlib import Path

    llm_source = (Path(__file__).resolve().parents[2] / "app" / "ai" / "llm.py").read_text(
        encoding="utf-8"
    )
    assignments = [
        line.strip()
        for line in llm_source.split("\n")
        if "redaction_mode" in line and "=" in line and "==" not in line
    ]
    mutations = [
        line
        for line in assignments
        if line.startswith("row.redaction_mode") or line.startswith("call.redaction_mode")
    ]
    assert not mutations, f"redaction_mode is written after insert: {mutations}"


@pytest.mark.unit
def test_the_mode_is_written_at_insert_not_at_finalisation() -> None:
    """`redaction_mode=mode` must appear in the LLMCall(...) constructor call.

    Setting it during finalisation would leave a failed or killed call NULL --
    and the failure path is exactly when "what was egressed" matters most. This
    asserts the property structurally, because a passing happy-path test cannot
    distinguish "written at insert" from "written at finalise".
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "app" / "ai" / "llm.py").read_text(
        encoding="utf-8"
    )
    start = source.index("row = LLMCall(")
    end = source.index("db.add(row)", start)
    constructor = source[start:end]
    assert "redaction_mode=mode" in constructor, (
        "redaction_mode is not set in the LLMCall constructor -- a call that "
        "fails before finalising would record no mode"
    )
    assert "status=LLMCallStatus.RUNNING" in constructor, (
        "the insert no longer looks the way this test assumes; re-check that "
        "redaction_mode is still written before the provider call"
    )
