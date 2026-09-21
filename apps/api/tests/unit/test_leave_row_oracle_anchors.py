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

# THE DOTTED FORM, deliberately, and not a blank line above a bare one.
#
# `pyproject.toml` records why: ruff resolves first-party by asking
# whether the DOTTED MODULE PATH exists under `src`, which defaults to
# the directory holding the config. This repo has a top-level `scripts/`
# unrelated to `apps/api/scripts/`, so the BARE form
# `from scripts import leave_row_oracle` resolves against it in a full
# checkout -- FIRST-party in CI, THIRD-party in the api container, which
# mounts apps/api at /app and has neither path. I001 on the runner, clean
# in the container, and the loop gate structurally cannot see it (PR #155).
#
# MEASURED, both layouts, both variants -- because `ruff --fix` proposes the
# blank line and it is the obvious answer:
#
#   bare + blank line   CI layout: PASS    container layout: I001
#   dotted (this file)  CI layout: PASS    container layout: PASS
#
# So taking the `--fix` would have moved the red from the runner to the
# loop gate rather than removing it. The dotted form is stable because it
# fails to resolve in BOTH environments -- they agree by accident, as
# `pyproject.toml` says -- and the nine other test files here use it.
import scripts.leave_row_oracle as oracle


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


@pytest.mark.unit
def test_the_flag_table_is_the_dispatch_AND_the_allow_list() -> None:
    """One structure serving both roles, which is what makes the order not matter.

    #343 adds an unknown-argument guard to `main`, refusing anything outside an
    allow-list. It was written against a tree with ONE flag, so its allow-list
    was that one literal; this branch adds a second flag and wires it into
    `ci.yml`. The two touch different hunks of `main`, so a first draft of both
    MERGED CLEAN and `main` went red -- measured on a combined tree,
    `--check-anchors` exited 2, refused by a guard that did not know the flag
    existed, on the step whose job is to report whether the oracle can measure.

    `_FLAGS` is the dispatch, so a key cannot exist without a handler, and any
    guard reading its keys accepts a flag if and only if this tree implements
    it. Registering a flag is adding its entry here, in either branch, in
    either merge order.

    Asserting the VALUES are callable is the half that matters: a key with no
    working handler is precisely the state the other branch's allow-list would
    have created -- a flag accepted and then not dispatched, falling through to
    the full oracle, which WRITES `redact.py`.
    """
    assert set(oracle._FLAGS) == {"--check-registry", "--check-anchors"}
    for flag, handler in oracle._FLAGS.items():
        assert callable(handler), f"{flag} is registered with no handler"


@pytest.mark.unit
def test_BOTH_flags_together_run_BOTH_checks(monkeypatch, capsys) -> None:
    """Passing both flags must not silently skip one.

    The dispatch was two `if <flag> in argv: ... return` blocks in sequence,
    which is a priority list wearing a dispatch's clothes: `--check-registry
    --check-anchors` returned from the registry block having never called
    `build_mutations`. That reinstates the exact #299 blind spot this flag
    exists to close -- stale anchors, exit 0, and an output that truthfully
    reports the registry is complete.

    Driven by breaking the ANCHORS only. If the anchor check runs, the combined
    invocation must be 2; if it is skipped, the registry check passes and the
    run is 0. Asserting the code alone would be satisfied by a gate that ran
    neither and crashed, so the anchor message is asserted too.
    """
    original = oracle._original()
    _name, old, _new = oracle.build_mutations(original)[0]
    monkeypatch.setattr(oracle, "_original", lambda: original.replace(old, "# gone"))

    assert oracle.main(["x", "--check-registry", "--check-anchors"]) == 2
    out = capsys.readouterr().out
    assert "ANCHORS STALE" in out
    # And the registry check ran as well -- this is not the anchor check having
    # pre-empted it, which would be the same defect facing the other way.
    assert "registry" in out
