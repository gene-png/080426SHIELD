"""W8a tier 2: the mutation sweep's operators (#72).

Tier 1 is static and blind to the two instances that cost the most. This tier
asks the question directly — change the code, does a test go red — and its
operators are chosen from defect shapes this repo has actually shipped rather
than from a textbook list.

`DropKeyword` is the one that earns its keep. Instance 9 was `targets=` being
deletable from `finalize_zt_deliverable` with the entire suite green: a missing
ARGUMENT, not a wrong operator, which is why an off-the-shelf mutation tool
would not have caught it either.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.mutation_sweep import collect


def _write(tmp_path: Path, src: str) -> Path:
    p = tmp_path / "subject.py"
    p.write_text(src, encoding="utf-8")
    return p


# --- DropKeyword -----------------------------------------------------------


@pytest.mark.unit
def test_drop_keyword_generates_one_mutant_per_keyword_argument(tmp_path) -> None:
    """Instance 9's shape, reduced."""
    path = _write(tmp_path, "def f():\n    return analyze(fw, stage_map, targets=t, notes=n)\n")
    dropped = {m.description for m in collect(path) if m.operator == "DropKeyword"}
    assert dropped == {"drop `targets=` from the call", "drop `notes=` from the call"}


@pytest.mark.unit
def test_the_dropped_keyword_is_actually_gone_from_the_mutant_source(tmp_path) -> None:
    """The mutant must be the real change, not a label describing one."""
    path = _write(tmp_path, "def f():\n    return analyze(fw, targets=t)\n")
    m = next(m for m in collect(path) if m.operator == "DropKeyword")
    assert "targets=" not in m.source
    assert "analyze(fw)" in m.source


@pytest.mark.unit
def test_star_star_kwargs_is_not_dropped(tmp_path) -> None:
    """`**{...}` is how the target fixes pass an optional argument.

    Dropping it changes arity in a way that is often a TypeError rather than a
    silent behaviour change, so it produces noise instead of signal.
    """
    path = _write(tmp_path, "def f():\n    return analyze(fw, **({'target': x} if x else {}))\n")
    assert [m for m in collect(path) if m.operator == "DropKeyword"] == []


# --- FlipCompare -----------------------------------------------------------


@pytest.mark.unit
def test_flip_compare_covers_the_boundary_operators(tmp_path) -> None:
    path = _write(tmp_path, "def f(a, b):\n    return a < b\n")
    flips = [m for m in collect(path) if m.operator == "FlipCompare"]
    assert [m.description for m in flips] == ["Lt -> LtE"]
    assert "a <= b" in flips[0].source


@pytest.mark.unit
def test_a_mutant_that_would_not_change_the_source_is_not_emitted(tmp_path) -> None:
    path = _write(tmp_path, "x = 1\n")
    assert collect(path) == []


# --- safety ----------------------------------------------------------------


@pytest.mark.unit
def test_collect_never_writes_to_the_subject(tmp_path) -> None:
    """Generating mutants must not touch the tree; only `run` does, and it
    restores in a `finally`. A crashed sweep leaving mutated sources behind
    would be a far worse defect than anything it detects."""
    src = "def f():\n    return analyze(fw, targets=t)\n"
    path = _write(tmp_path, src)
    collect(path)
    assert path.read_text(encoding="utf-8") == src


@pytest.mark.unit
def test_every_mutant_is_valid_python(tmp_path) -> None:
    import ast

    path = _write(
        tmp_path,
        "def f(a, b):\n"
        "    if a < b:\n"
        "        return analyze(a, targets=b, notes=None)\n"
        "    return a == b\n",
    )
    mutants = collect(path)
    assert mutants, "fixture must produce mutants or this proves nothing"
    for m in mutants:
        ast.parse(m.source)  # raises if a mutant is unparseable


# --- node targeting on chained calls ----------------------------------------
#
# Found by an adversarial retro-audit of #93. `_find_same` resolved a node by
# (type, lineno, col_offset), which is NOT unique: in CPython a Call's position
# is the position of its FUNC expression, so every Call in a fluent chain shares
# one position. `ast.walk` is breadth-first, so the outermost always won — the
# mutation was applied to the wrong node, changed nothing, and was reported as
# SURVIVED. A reader then goes hunting for a missing test on a line that is
# fine, while the real mutant for that line was never built at all.


@pytest.mark.unit
def test_a_keyword_on_a_chained_call_is_actually_dropped(tmp_path) -> None:
    """The exact shape from `routes/attack.py`'s discard, reduced."""
    path = _write(
        tmp_path,
        "def f(db, X, S):\n"
        "    return db.execute(\n"
        "        update(X)\n"
        "        .where(X.id == 1)\n"
        "        .values(status=S.DISCARDED)\n"
        "        .execution_options(synchronize_session=False)\n"
        "    )\n",
    )
    dropped = [
        m for m in collect(path) if m.operator == "DropKeyword" and "status=" in m.description
    ]
    assert dropped, "no mutant generated for the keyword under test"
    assert "status=" not in dropped[0].source, (
        "the mutation was applied to a different Call in the chain — it changed "
        "nothing, and a no-op mutant reports as SURVIVED"
    )
    assert "synchronize_session=False" in dropped[0].source, "mutated the wrong keyword"


@pytest.mark.unit
def test_each_chained_call_gets_its_own_distinct_mutant(tmp_path) -> None:
    path = _write(
        tmp_path,
        "def f(db, X):\n    return db.execute(update(X).values(a=1).execution_options(b=2))\n",
    )
    mutants = [m for m in collect(path) if m.operator == "DropKeyword"]
    # Assert each mutant REALLY dropped its own keyword. Counting distinct
    # sources was not enough: with the bug, one mutant was a no-op and one was
    # real, which still gave two distinct strings — this test passed for the
    # wrong reason before the fix, which is the shape it exists to catch.
    dropped_a = [m for m in mutants if "a=1" not in m.source]
    dropped_b = [m for m in mutants if "b=2" not in m.source]
    assert len(dropped_a) == 1 and "b=2" in dropped_a[0].source
    assert len(dropped_b) == 1 and "a=1" in dropped_b[0].source


@pytest.mark.unit
def test_the_no_op_guard_compares_against_the_normalised_original(tmp_path) -> None:
    """The guard read `ast.unparse(tree) == raw_file_text`, which can never be
    true for a real file — comments are stripped and formatting normalised. It
    was dead, which is why the no-op mutants above sailed through it."""
    from scripts.mutation_sweep import _normalised

    src = "# a comment\ndef f(x):\n    return  g(a=1)\n"
    assert _normalised(src) == _normalised("def f(x):\n    return g(a=1)\n")


@pytest.mark.unit
def test_a_file_with_no_mutable_constructs_yields_no_mutants(tmp_path) -> None:
    """Renamed. This was called `test_a_mutant_that_would_not_change_the_source_
    is_not_emitted` and used `x = 1`, which contains no Call and no Compare — so
    `collect` returned [] before the no-op guard was ever reached. It passed for
    a reason unrelated to its name and would have passed with the guard deleted.
    Instance ten of the #72 pattern, inside the tool built to find #72.
    """
    assert collect(_write(tmp_path, "x = 1\n")) == []
