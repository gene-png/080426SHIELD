"""The oracle reports a failed restore on EVERY exit from its mutation loop (#161).

The default path writes mutated copies of `redact.py` -- the single LLM egress
path -- and restores it in a `finally`. The restore is read back, and a
mismatch prints RESTORE FAILED. But three `return 2` sites sat INSIDE the
`try`: an anchor-count mismatch, a mutation that will not compile, and the
all-guards-off variant not compiling. A `return` runs the `finally`, computes
`restore_failed`, and then leaves -- skipping the block that reports it. So a
restore that did not take (an editor or antivirus holding the file) exited 2
with "did not compile" and no word that the redactor was left mutated.

These tests NEVER touch the real `redact.py`. `REDACT` is replaced by an
in-memory fake that can be told to ignore the restore write, and every test
asserts the real file's bytes are unchanged afterwards.
"""

from __future__ import annotations

import hashlib

import pytest

# The DOTTED form: see test_leave_row_oracle_anchors.py for why.
import scripts.leave_row_oracle as oracle

ORIGINAL = "RULE_A = 1\nRULE_B = 2\n"


class _FakeRedact:
    """Stands in for `REDACT`. With `stuck`, a write that would RESTORE the
    original after a mutation is silently dropped -- the failure #161 is about."""

    def __init__(self, stuck: bool) -> None:
        self.text = ORIGINAL
        self.stuck = stuck

    def read_text(self, encoding: str = "utf-8") -> str:
        return self.text

    def write_text(self, text: str, encoding: str = "utf-8") -> int:
        if self.stuck and text == ORIGINAL and self.text != ORIGINAL:
            return 0
        self.text = text
        return len(text)


#: Captured at import, before any test swaps `oracle.REDACT` for the fake:
#: the fixture's teardown runs while that swap is still in place.
_REAL_REDACT = oracle.REDACT


def _real_redact_digest() -> str:
    return hashlib.sha256(_REAL_REDACT.read_bytes()).hexdigest()


@pytest.fixture
def real_redact_untouched():
    """The coordinator's constraint, as an assertion: whatever these tests do,
    the real redactor is byte-identical before and after."""
    before = _real_redact_digest()
    yield
    assert _real_redact_digest() == before, "the REAL redact.py changed during a test"


def _wire(monkeypatch, *, stuck: bool, muts, evaluate) -> _FakeRedact:
    fake = _FakeRedact(stuck)
    monkeypatch.setattr(oracle, "REDACT", fake)
    monkeypatch.setattr(oracle, "leave_rows", lambda: [("T", "r1", "text")])
    monkeypatch.setattr(oracle, "build_mutations", lambda source: muts)
    monkeypatch.setattr(oracle, "_evaluate", evaluate)
    return fake


def _compile_fails_after_baseline():
    calls = {"n": 0}

    def evaluate(rows):
        calls["n"] += 1
        if calls["n"] == 1:
            return set()  # the baseline, on the unmutated file
        raise SyntaxError("mutation did not compile")

    return evaluate


def _all_off_fails():
    calls = {"n": 0}

    def evaluate(rows):
        calls["n"] += 1
        if calls["n"] <= 2:
            return set()  # baseline, then the single guard's mutation
        raise SyntaxError("all-guards-off did not compile")

    return evaluate


_EARLY_EXITS = {
    "a mutation does not compile": (
        [("guard_a", "RULE_A = 1", "RULE_A = 0")],
        _compile_fails_after_baseline,
        "guard_a did not compile",
    ),
    "the all-guards-off variant does not compile": (
        [("guard_a", "RULE_A = 1", "RULE_A = 0")],
        _all_off_fails,
        "all-guards-off variant did not compile",
    ),
    "an anchor appears twice": (
        # The anchor is present at build time and then counts 2 against the
        # file -- reached after the FIRST guard has already written a mutation.
        [("guard_a", "RULE_A = 1", "RULE_A = 0"), ("guard_b", "= ", "== ")],
        lambda: (lambda rows: set()),
        "guard_b: anchor appears 2 times",
    ),
}


@pytest.mark.unit
@pytest.mark.parametrize("case", list(_EARLY_EXITS), ids=list(_EARLY_EXITS))
def test_a_failed_restore_is_reported_on_every_early_exit(
    case, monkeypatch, capsys, real_redact_untouched
) -> None:
    muts, make_eval, cause = _EARLY_EXITS[case]
    fake = _wire(monkeypatch, stuck=True, muts=muts, evaluate=make_eval())
    assert oracle.main(["leave_row_oracle"]) == 2
    out = capsys.readouterr().out
    assert fake.text != ORIGINAL, "setup: the fake was meant to stay mutated"
    assert cause in out, out
    assert "RESTORE FAILED" in out, (
        "the restore did not take and the run said nothing about it -- the "
        f"verdict was computed in `finally` and discarded (#161). Output:\n{out}"
    )


@pytest.mark.unit
@pytest.mark.parametrize("case", list(_EARLY_EXITS), ids=list(_EARLY_EXITS))
def test_a_successful_restore_on_an_early_exit_says_only_the_cause(
    case, monkeypatch, capsys, real_redact_untouched
) -> None:
    # The passing half: a restore that worked must not be reported as failed,
    # and the early exit still names its own cause and exits 2.
    muts, make_eval, cause = _EARLY_EXITS[case]
    fake = _wire(monkeypatch, stuck=False, muts=muts, evaluate=make_eval())
    assert oracle.main(["leave_row_oracle"]) == 2
    out = capsys.readouterr().out
    assert fake.text == ORIGINAL
    assert cause in out, out
    assert "RESTORE FAILED" not in out, out
