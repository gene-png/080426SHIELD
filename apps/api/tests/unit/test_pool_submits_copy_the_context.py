"""Every executor `submit` under `app/` runs in a COPY of the caller's context.

A Run-AI knows a batch called the provider only through `invoke_mark_var`
(#1219), and tags each `llm_calls` row with its run through `ai_run_id_var`
(#645); both reach a pool thread only if the work is submitted as
`contextvars.copy_context().run`. A pool thread starts with an EMPTY context,
so a bare `pool.submit(fn, ...)` would call the provider with no mark: the
run would record "not charged" over a real call (advisor, #736 6225076633).

The rule is read from the source with `ast`, so a new pool anywhere under
`app/` is checked without being listed. The count of submits found is part of
the result: a scan that finds none proves nothing.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_APP = Path(__file__).resolve().parents[2] / "app"


def _is_copy_context_run(node: ast.expr) -> bool:
    """`contextvars.copy_context().run` (or `copy_context().run`)."""
    if not (isinstance(node, ast.Attribute) and node.attr == "run"):
        return False
    call = node.value
    if not isinstance(call, ast.Call):
        return False
    f = call.func
    return (isinstance(f, ast.Attribute) and f.attr == "copy_context") or (
        isinstance(f, ast.Name) and f.id == "copy_context"
    )


def _submits() -> list[tuple[str, int, ast.Call]]:
    found = []
    for path in sorted(_APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "submit"
            ):
                found.append((path.relative_to(_APP.parent).as_posix(), node.lineno, node))
    return found


def test_every_pool_submit_runs_in_a_copied_context() -> None:
    submits = _submits()
    # The two known pools (batching.run_batches, routes/risk.py): fewer means
    # the scan stopped seeing them, not that they went away.
    assert len(submits) >= 2, submits
    bare = [
        f"{where}:{line}"
        for where, line, call in submits
        if not (call.args and _is_copy_context_run(call.args[0]))
    ]
    assert bare == [], f"submit without contextvars.copy_context().run: {bare}"


def test_the_check_rejects_a_bare_submit() -> None:
    """The predicate itself can fail: a bare submit and a submit of some other
    `.run` are both refused, the copied form is accepted."""
    bare = ast.parse("pool.submit(work, x)").body[0].value
    other = ast.parse("pool.submit(thing.run, x)").body[0].value
    copied = ast.parse("pool.submit(contextvars.copy_context().run, work, x)").body[0].value
    assert not _is_copy_context_run(bare.args[0])
    assert not _is_copy_context_run(other.args[0])
    assert _is_copy_context_run(copied.args[0])
