"""The LEAVE-row oracle never writes `redact.py` (#161).

It used to write each mutation into `redact.py` -- the file the api container
bind-mounts and `uvicorn --reload` serves live -- and restore it in a
`finally`. Three early exits skipped the report of a failed restore, and a
restore that RAISED was never reported at all. The fix removes the write:
every variant is compiled in memory as its own module, so there is nothing to
restore.

These tests replace `REDACT` with a read-only proxy whose `write_text` raises,
so any write fails the test, and they hash the real file before and after.
"""

from __future__ import annotations

import hashlib
import sys

import pytest

# The DOTTED form: see test_leave_row_oracle_anchors.py for why.
import scripts.leave_row_oracle as oracle

#: Captured at import, before any test swaps `oracle.REDACT`.
_REAL_REDACT = oracle.REDACT


def _digest() -> str:
    return hashlib.sha256(_REAL_REDACT.read_bytes()).hexdigest()


@pytest.fixture
def real_redact_untouched():
    before = _digest()
    yield
    assert _digest() == before, "the REAL redact.py changed during a test"


class _ReadOnlyRedact:
    """Reads the real file; refuses every write, and remembers the attempt."""

    def __init__(self) -> None:
        self.writes = 0

    def read_text(self, encoding: str = "utf-8") -> str:
        return _REAL_REDACT.read_text(encoding=encoding)

    def read_bytes(self) -> bytes:
        return _REAL_REDACT.read_bytes()

    def __str__(self) -> str:
        return str(_REAL_REDACT)

    def write_text(self, *args, **kwargs):
        self.writes += 1
        raise AssertionError("the oracle tried to WRITE redact.py")


@pytest.mark.unit
def test_the_default_path_never_writes_redact_py(
    monkeypatch, capsys, real_redact_untouched
) -> None:
    """The whole default path -- baseline, every guard, all-off, all-but-one --
    over a slice of the real LEAVE rows, with real mutations and the real
    evaluator. Red on the file-writing version: its first act was a write."""
    proxy = _ReadOnlyRedact()
    monkeypatch.setattr(oracle, "REDACT", proxy)
    rows = oracle.leave_rows()[:12]
    monkeypatch.setattr(oracle, "leave_rows", lambda: rows)
    assert oracle.main(["leave_row_oracle"]) == 0, capsys.readouterr().out
    assert proxy.writes == 0
    assert "ALL GUARDS OFF AT ONCE" in capsys.readouterr().out


@pytest.mark.unit
def test_a_variant_never_touches_the_real_module(real_redact_untouched) -> None:
    """A mutated variant must be what gets evaluated, and the module the API
    imports must be the same object, behaving the same, afterwards."""
    import app.ai.redact as real

    before = real.redact_for_ai
    source = oracle._original()
    rows = oracle.leave_rows()
    mutated = source
    for _name, old, new in oracle.build_mutations(source):
        mutated = mutated.replace(old, new)

    assert oracle._evaluate(rows, source) == set(), "the unmutated source must leave every row"
    flipped = oracle._evaluate(rows, mutated)
    assert flipped, "the all-guards-off variant flipped nothing -- it was not the one evaluated"

    assert real.redact_for_ai is before
    assert oracle._VARIANT not in sys.modules
    table, rid = next(iter(flipped))
    text = next(t for tb, r, t in rows if (tb, r) == (table, rid))
    out, _ = real.redact_for_ai(text, mode="strict")
    assert out == text, "the REAL redactor changed behaviour after a variant was evaluated"


@pytest.mark.unit
def test_a_mutation_that_does_not_compile_is_2_and_writes_nothing(
    monkeypatch, capsys, real_redact_untouched
) -> None:
    proxy = _ReadOnlyRedact()
    monkeypatch.setattr(oracle, "REDACT", proxy)
    rows = oracle.leave_rows()[:3]
    monkeypatch.setattr(oracle, "leave_rows", lambda: rows)
    source = oracle._original()
    first_line = source.splitlines(keepends=True)[0]
    monkeypatch.setattr(oracle, "build_mutations", lambda src: [("broken", first_line, "def (\n")])
    assert oracle.main(["leave_row_oracle"]) == 2
    assert "broken did not compile" in capsys.readouterr().out
    assert proxy.writes == 0
    assert oracle._VARIANT not in sys.modules
