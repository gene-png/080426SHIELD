"""Every executor `submit` under `app/` runs in a COPY of the caller's context.

A Run-AI knows a batch called the provider only through `invoke_mark_var`
(#1219), and tags each `llm_calls` row with its run through `ai_run_id_var`
(#645); both reach a pool thread only if the work is submitted as
`contextvars.copy_context().run`. A pool thread starts with an EMPTY context,
so a bare `pool.submit(fn, ...)` would call the provider with no mark: the
run would record "not charged" over a real call (advisor, #736 6225076633).

The rule is read from the source with `ast`, so a new pool anywhere under
`app/` is checked without being listed. The count of submits found is part of
the result: a scan that finds none proves nothing. The other ways to run code
on another thread -- an executor's `.map`, `threading.Thread`,
`run_in_executor`, `asyncio.to_thread` -- have no copied form here at all, so
none may appear until one is written and this test is taught to accept it.
Those are matched by NAME (the callee's, and for `.map` a receiver named like
a pool or executor), so a renamed import or an unusual receiver is a gap.
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


def _thread_starts_in(tree: ast.AST, where: str) -> list[str]:
    """Calls that run code on another thread without going through `submit`,
    matched by NAME: the callee's last name, and for `.map` the receiver's."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
        receiver = ""
        if isinstance(f, ast.Attribute):
            v = f.value
            receiver = (
                v.id if isinstance(v, ast.Name) else v.attr if isinstance(v, ast.Attribute) else ""
            )
        if name in ("Thread", "Timer", "run_in_executor", "to_thread") or (
            name == "map" and ("pool" in receiver.lower() or "executor" in receiver.lower())
        ):
            found.append(f"{where}:{node.lineno} {name}")
    return found


def _other_thread_starts() -> list[str]:
    found = []
    for path in sorted(_APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found += _thread_starts_in(tree, path.relative_to(_APP.parent).as_posix())
    return found


def test_nothing_starts_a_thread_without_the_copied_context() -> None:
    assert _other_thread_starts() == []


@pytest.mark.parametrize(
    "src",
    [
        "threading.Thread(target=f)",
        "Thread(target=f)",
        "threading.Timer(1, f)",
        "loop.run_in_executor(None, f)",
        "asyncio.to_thread(f)",
        "pool.map(f, xs)",
        "self._executor.map(f, xs)",
    ],
)
def test_the_thread_scan_finds_each_form(src: str) -> None:
    """The positive control: each form the scan exists to refuse is found."""
    assert len(_thread_starts_in(ast.parse(src), "probe")) == 1, src


def test_the_thread_scan_leaves_an_ordinary_map_alone() -> None:
    assert _thread_starts_in(ast.parse("names.map(str.upper)"), "probe") == []


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
