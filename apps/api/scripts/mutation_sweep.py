"""W8a tier 2: does the suite actually notice when the code changes? (#72)

Tier 1 (`check_test_integrity.py`) is a static pass that catches roughly a third
of the recorded instances. This is the tier that covers the class, because it
asks the question directly: change the code, does a test go red. It is the
automation of the revert-each-fix-individually practice that found instances 8
and 9 by hand.

**Why not mutmut.** Two reasons, the second decisive:

1. `pip install` is not available in the api container, and mutmut's cache
   directory would hit the same unwritable-path wall `CLAUDE.md` records for
   `/.ruff_cache`.
2. **mutmut mutates expressions, not call signatures.** Instance 9 was
   `targets=targets_map` being deletable from `finalize_zt_deliverable` with the
   entire suite green — a *missing argument*, not a wrong operator. mutmut would
   not have caught it either. `DropKeyword` below exists specifically for that
   shape, and it is the operator most likely to earn its keep here: this codebase
   has repeatedly lost values by not passing them.

**Scope it.** Every mutant costs a full run of the selected tests, so this is a
scheduled/on-demand tool, not a PR gate — the unit suite is 13-16 minutes and
50-150 mutants cannot sit in front of a merge. A non-blocking mechanism that
runs beats a blocking one that gets disabled.

A SURVIVING mutant means: this change to the code broke no test. That is not
automatically a defect — some mutants are semantically equivalent, and some
touch genuinely untested-by-design paths. It is a question worth answering,
which is the most this tool should ever claim.

**A survivor is only meaningful relative to `--tests`.** Narrowing the target
manufactures survivors that a wider run kills: the first dogfood run of this
tool reported `exporters.py:102 FlipCompare` as surviving against one test file,
and `--tests tests/unit/test_exporters.py -k savings` killed it immediately. So
a narrow sweep is for asking "do THESE tests pin this code", never for
concluding a line is untested. The scheduled workflow runs the whole unit suite
for that reason.

Usage:
    python -m scripts.mutation_sweep --paths app/routes/zt.py --tests tests/unit/test_export_targets.py
    python -m scripts.mutation_sweep --paths app/zt/exporters.py --tests tests/unit -k exporter --limit 20
"""

from __future__ import annotations

import argparse
import ast
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Mutant:
    path: Path
    line: int
    operator: str
    description: str
    source: str


class _Collector(ast.NodeVisitor):
    """Generates mutants by rewriting one node at a time.

    Deliberately small. Each operator maps to a defect shape this repo has
    actually shipped, rather than to a textbook list.
    """

    def __init__(self, path: Path, original: str) -> None:
        self.path = path
        self.original = original
        self.mutants: list[Mutant] = []

    # -- DropKeyword: instance 9's shape ------------------------------------
    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        for kw in node.keywords:
            if kw.arg is None:  # **kwargs — dropping changes arity unpredictably
                continue
            self._emit(
                node,
                remove_keyword=kw,
                operator="DropKeyword",
                description=f"drop `{kw.arg}=` from the call",
            )
        self.generic_visit(node)

    # -- FlipCompare: a boundary nobody asserts -----------------------------
    def visit_Compare(self, node: ast.Compare) -> None:  # noqa: N802
        swaps = {
            ast.Lt: ast.LtE,
            ast.LtE: ast.Lt,
            ast.Gt: ast.GtE,
            ast.GtE: ast.Gt,
            ast.Eq: ast.NotEq,
            ast.NotEq: ast.Eq,
        }
        for idx, op in enumerate(node.ops):
            replacement = swaps.get(type(op))
            if replacement is not None:
                self._emit(
                    node,
                    swap_op=(idx, replacement),
                    operator="FlipCompare",
                    description=f"{type(op).__name__} -> {replacement.__name__}",
                )
        self.generic_visit(node)

    def _emit(self, node: ast.AST, *, operator: str, description: str, **change) -> None:
        tree = ast.parse(self.original, filename=str(self.path))
        target = _find_same(tree, node)
        if target is None:
            return
        if "remove_keyword" in change:
            kw = change["remove_keyword"]
            target.keywords = [k for k in target.keywords if k.arg != kw.arg]
        if "swap_op" in change:
            idx, replacement = change["swap_op"]
            target.ops[idx] = replacement()
        try:
            source = ast.unparse(ast.fix_missing_locations(tree))
        except Exception:  # noqa: BLE001 - an unparseable mutant is simply skipped
            return
        if source == self.original:
            return
        self.mutants.append(
            Mutant(
                path=self.path,
                line=getattr(node, "lineno", 0),
                operator=operator,
                description=description,
                source=source,
            )
        )


def _find_same(tree: ast.AST, node: ast.AST) -> ast.AST | None:
    """Locate the node at the same position/type in a freshly parsed tree."""
    for candidate in ast.walk(tree):
        if (
            type(candidate) is type(node)
            and getattr(candidate, "lineno", None) == getattr(node, "lineno", None)
            and getattr(candidate, "col_offset", None) == getattr(node, "col_offset", None)
        ):
            return candidate
    return None


def collect(path: Path) -> list[Mutant]:
    original = path.read_text(encoding="utf-8")
    collector = _Collector(path, original)
    collector.visit(ast.parse(original, filename=str(path)))
    return collector.mutants


def _run_tests(tests: str, extra: list[str]) -> bool:
    """True if the selected tests PASS."""
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pytest", "-q", "-x", "--no-header", tests, *extra],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def run(paths: list[Path], tests: str, extra: list[str], limit: int | None) -> list[Mutant]:
    mutants: list[Mutant] = []
    for path in paths:
        mutants.extend(collect(path))
    if limit is not None:
        mutants = mutants[:limit]

    print(f"{len(mutants)} mutant(s) over {len(paths)} file(s); tests = {tests} {' '.join(extra)}")
    survivors: list[Mutant] = []
    for i, m in enumerate(mutants, 1):
        original = m.path.read_text(encoding="utf-8")
        # Write atomically and ALWAYS restore — a crashed sweep must not leave a
        # mutated source tree behind.
        try:
            _atomic_write(m.path, m.source)
            passed = _run_tests(tests, extra)
        finally:
            _atomic_write(m.path, original)
        status = "SURVIVED" if passed else "killed"
        print(f"  [{i}/{len(mutants)}] {status}  {m.path}:{m.line} {m.operator} — {m.description}")
        if passed:
            survivors.append(m)
    return survivors


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paths", nargs="+", required=True, help="source files to mutate")
    ap.add_argument("--tests", required=True, help="pytest target to run per mutant")
    ap.add_argument("--limit", type=int, default=None, help="cap the number of mutants")
    ap.add_argument("-k", dest="k", default=None, help="pytest -k expression")
    args = ap.parse_args(argv)

    extra = ["-k", args.k] if args.k else []
    paths = [Path(p) for p in args.paths]
    missing = [p for p in paths if not p.is_file()]
    if missing:
        print(f"no such file(s): {', '.join(str(p) for p in missing)}", file=sys.stderr)
        return 2

    survivors = run(paths, args.tests, extra, args.limit)
    print()
    if survivors:
        print(f"{len(survivors)} surviving mutant(s) — each is a change no test noticed:")
        for m in survivors:
            print(f"  {m.path}:{m.line} {m.operator} — {m.description}")
        print(
            "\nA survivor is a QUESTION, not a verdict: some mutants are semantically\n"
            "equivalent and some paths are untested by design. Answer each one."
        )
        return 1
    print("no surviving mutants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
