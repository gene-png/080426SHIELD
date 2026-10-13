"""#1120: derive every route handler that can write a row of a record table or
one of its children (the design note rev 10, section 5).

Step 1, the tables: the ForeignKey closure of the four record tables over
`Base.metadata`, followed recursively, plus the loose (FK-less) children a
revision copies (`evidence_links`). Step 2, the writers: a static walk of every
module under `app/`, from every `@router.<anything>(...)` handler (GET
included), following calls by name and functions passed as values
(`functools.partial(work, ...)`, `Depends(fn)`), transitively. Over-matching on
purpose; every hit is classified by hand in the ratchet's `WRITER_VERDICTS`.

Write shapes, for a closure model M, per function:
  W1  <x>.add(M(...)) / add_all
  W2  update(M) / insert(M) / delete(M); W2g on a non-name table expression
  W3  <x>.delete(obj) in a function that names M
  W4  <name>.<attr> = ... (Tuple, List and Starred targets unpacked) in a
      function that names M or a name starting with M (its status enum)
  W5  M(...) constructed
  W6  setattr(...) in a function that names M

Where a writer can still hide (stated in the ratchet's docstring): raw SQL text,
an attribute write in a helper that names neither M nor its enum, a relationship
cascade, and any writer that is not a route handler.
"""

from __future__ import annotations

import ast
import os
from collections import defaultdict
from pathlib import Path

RECORD_TABLES = ("attack_assessments", "csf_assessments", "zt_assessments", "capability_lists")
#: Children with no ForeignKey (polymorphic), which a revision copies.
LOOSE_CHILD_TABLES = ("evidence_links",)


def closure_tables() -> set[str]:
    import app.models  # noqa: F401  (registers every model)
    from app.db.base import Base

    closure = set(RECORD_TABLES)
    changed = True
    while changed:
        changed = False
        for t in Base.metadata.tables.values():
            if t.name in closure:
                continue
            if any(fk.column.table.name in closure for fk in t.foreign_keys):
                closure.add(t.name)
                changed = True
    return closure | set(LOOSE_CHILD_TABLES)


def closure_models() -> set[str]:
    from app.db.base import Base

    tables = closure_tables()
    return {m.class_.__name__ for m in Base.registry.mappers if m.local_table.name in tables}


def _names_in(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _flatten(targets: list[ast.expr]) -> list[ast.expr]:
    flat, todo = [], list(targets)
    while todo:
        t = todo.pop()
        if isinstance(t, ast.Tuple | ast.List):
            todo.extend(t.elts)
        elif isinstance(t, ast.Starred):
            todo.append(t.value)
        else:
            flat.append(t)
    return flat


def _direct_writes(fn: ast.AST, models: set[str]) -> set[str]:
    out: set[str] = set()
    named = {m for m in models for n in _names_in(fn) if n.startswith(m)}
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in models:
                out.add(f.id)
            if isinstance(f, ast.Name) and f.id == "setattr":
                out |= named
            if isinstance(f, ast.Attribute) and f.attr in ("add", "add_all"):
                for a in n.args:
                    for c in ast.walk(a):
                        if (
                            isinstance(c, ast.Call)
                            and isinstance(c.func, ast.Name)
                            and c.func.id in models
                        ):
                            out.add(c.func.id)
            if isinstance(f, ast.Name) and f.id in ("update", "insert", "delete") and n.args:
                a0 = n.args[0]
                if isinstance(a0, ast.Name) and a0.id in models:
                    out.add(a0.id)
                elif not isinstance(a0, ast.Name):
                    out.add("<generic>")
            if isinstance(f, ast.Attribute) and f.attr == "delete" and n.args:
                out |= named
        if isinstance(n, ast.Assign | ast.AugAssign) and named:
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in _flatten(targets):
                if (
                    isinstance(t, ast.Attribute)
                    and isinstance(t.value, ast.Name)
                    and t.value.id not in ("self", "cls", "resp", "response")
                ):
                    out |= named
    return out


def writers(api_root: Path) -> dict[str, set[str]]:
    """{"app/routes/<file>.py::<handler>": {models it can write}} for every
    route handler from which a closure write is reachable."""
    models = closure_models()
    root = api_root / "app"
    defs: dict[str, list[tuple[str, ast.AST]]] = defaultdict(list)
    handlers: list[tuple[str, ast.AST]] = []
    for dp, _dirs, files in os.walk(root):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = Path(dp) / f
            mod = str(path.relative_to(api_root))
            tree = ast.parse(path.read_text(), str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    defs[node.name].append((mod, node))
                    for d in node.decorator_list:
                        if (
                            isinstance(d, ast.Call)
                            and isinstance(d.func, ast.Attribute)
                            and isinstance(d.func.value, ast.Name)
                            and d.func.value.id == "router"
                        ):
                            handlers.append((mod, node))
    cache = {(m, fn.lineno): _direct_writes(fn, models) for lst in defs.values() for m, fn in lst}

    def calls(fn: ast.AST) -> set[str]:
        out = set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in defs:
                out.add(n.id)
            if isinstance(n, ast.Call):
                if isinstance(n.func, ast.Name):
                    out.add(n.func.id)
                elif isinstance(n.func, ast.Attribute):
                    out.add(n.func.attr)
        return out

    result: dict[str, set[str]] = {}
    for mod, h in handlers:
        seen: set[tuple[str, int]] = set()
        stack = [(mod, h)]
        found: set[str] = set()
        while stack:
            m, fn = stack.pop()
            key = (m, fn.lineno)
            if key in seen:
                continue
            seen.add(key)
            found |= cache.get(key, set())
            for c in calls(fn):
                stack.extend(defs.get(c, ()))
        if found:
            result[f"{mod}::{h.name}"] = found
    return result
