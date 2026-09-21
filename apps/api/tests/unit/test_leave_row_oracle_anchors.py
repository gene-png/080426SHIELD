"""The LEAVE-row oracle's can-it-measure gate must be able to fail (#299).

`--check-registry` asks whether every LEAVE table has registered guards. It
returns BEFORE `build_mutations` is ever called, so it cannot see the failure
that actually happened: two mutation anchors drifted out of `redact.py`, the
whole oracle had been exiting 2 for an unknown length of time, and CI stayed
green because the one property it watched was the one that could not look.

`--check-anchors` is the missing property, and this file is the half that
proves it can fail. Written with the gate, per the CLAUDE.md rule about
shipping a checker without one -- and pointedly so, since the defect being
closed IS a checker that nothing checked.

## Why `_original` is patched rather than `redact.py` edited

Breaking a real anchor in `redact.py` breaks the MODULE: renaming
`_STREET_SEP` raises `NameError` at import and the oracle's crash handler
exits 2 before the anchor check is reached. That fails closed, correctly, and
proves nothing about the branch under test -- a pass for the wrong reason.

Patching the source the checker reads isolates the one condition: a file that
imports fine and whose anchors have moved.
"""

from __future__ import annotations

import pytest
from scripts import leave_row_oracle as oracle


@pytest.mark.unit
def test_the_real_tree_can_measure() -> None:
    """THE PASSING STATE. Watching a guard fire proves it fires, not that it
    passes -- and a check that halts unconditionally is indistinguishable from
    the hazard it exists to catch."""
    assert oracle.main(["x", "--check-anchors"]) == 0


@pytest.mark.unit
def test_a_drifted_anchor_cannot_measure(monkeypatch, capsys) -> None:
    """The recorded incident: an anchor's line no longer exists.

    `+ r"){1,3}"` became `+ r"+){1,3}"`, and a `words` local was renamed
    `substantive`. Either is invisible to `--check-registry`.
    """
    real = oracle._original()
    needle = "_STREET_SEP = _HSPACE"
    assert needle in real, "the anchor this test drifts must exist to begin with"
    monkeypatch.setattr(
        oracle, "_original", lambda: real.replace(needle, "_STREET_SEPARATOR = _HSPACE")
    )

    assert oracle.main(["x", "--check-anchors"]) == 2

    out = capsys.readouterr().out
    assert "ANCHORS STALE" in out
    # Names the anchor, not just that something failed. A guard that fires for
    # a reason nobody would guess gets debugged in the wrong direction.
    assert "_STREET_SEP" in out


@pytest.mark.unit
def test_an_ambiguous_anchor_cannot_measure(monkeypatch, capsys) -> None:
    """An anchor matching TWO lines is equally unmeasurable, and is NOT caught
    by `build_mutations` -- `_line_containing` happily returns the first.

    `main` already refuses this per-mutation during a real run
    (`anchor appears {n} times, not 1`), so the check would have been a
    narrower rule than the reader assumes without it: "the anchors resolve"
    reads as "the oracle can measure", and a duplicated anchor breaks the
    second while satisfying the first.
    """
    real = oracle._original()
    needle = "_STREET_SEP = _HSPACE"
    line = next(ln for ln in real.split("\n") if needle in ln)
    monkeypatch.setattr(oracle, "_original", lambda: real.replace(line, line + "\n" + line, 1))

    assert oracle.main(["x", "--check-anchors"]) == 2

    out = capsys.readouterr().out
    assert "ANCHORS AMBIGUOUS" in out
    assert "not 1" in out


@pytest.mark.unit
def test_check_anchors_writes_nothing(monkeypatch) -> None:
    """It must not touch `redact.py`.

    The oracle's measuring path WRITES mutated copies of that file and restores
    it afterwards. A crash mid-run has left a mutated redactor on disk before.
    This mode reads only, and that is asserted rather than assumed, because
    "it only reads" is exactly the kind of claim that stops being true when
    someone adds a convenience.
    """
    before = oracle.REDACT.read_text(encoding="utf-8")

    def refuse(*_a, **_k):
        raise AssertionError("--check-anchors must not write redact.py")

    monkeypatch.setattr(type(oracle.REDACT), "write_text", refuse)
    assert oracle.main(["x", "--check-anchors"]) == 0
    assert oracle.REDACT.read_text(encoding="utf-8") == before
