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
        self._normalised_original = _normalised(original)
        # Identity by walk index, not by source position — see `_node_at`.
        # Populated by `collect` from the SAME tree this visitor walks: `id()` is
        # only meaningful within a single parse.
        self._index: dict[int, int] = {}

    def index_tree(self, tree: ast.AST) -> None:
        self._index = {id(n): i for i, n in enumerate(ast.walk(tree))}

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
        index = self._index.get(id(node))
        if index is None:  # pragma: no cover - every visited node is indexed
            return
        tree = ast.parse(self.original, filename=str(self.path))
        target = _node_at(tree, index, type(node))
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
        # Compare STRUCTURE against structure. Against raw file text this could
        # never be true, so every no-op mutant was emitted and then scored.
        if source == self._normalised_original:
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


def _normalised(source: str) -> str:
    """Round-trip through the AST so two sources compare on STRUCTURE.

    The no-op guard used to read `ast.unparse(tree) == self.original`, comparing
    generated output against raw file text — different comments, different
    whitespace, never equal. It was dead, which is why the no-op mutants below
    sailed through it.
    """
    return ast.unparse(ast.parse(source))


def _node_at(tree: ast.AST, index: int, expected: type) -> ast.AST | None:
    """The node at `index` in this tree's walk order.

    Position is NOT a usable identity. In CPython a `Call`'s `lineno`/`col_offset`
    are those of its FUNC expression and an `Attribute`'s are those of its VALUE,
    so every call in `update(X).where(...).values(...).execution_options(...)`
    reports the same position. The old matcher compared (type, lineno, col_offset)
    and `ast.walk` is breadth-first, so the OUTERMOST call always won: the
    mutation landed on the wrong node, changed nothing, and the resulting no-op
    mutant was reported as SURVIVED — sending a reader hunting for a missing test
    on a line that was fine, while the real mutant for it was never built.

    `ast.walk` is deterministic for a given tree, and both trees here are parses
    of the same source, so the walk index IS a stable identity.
    """
    for i, candidate in enumerate(ast.walk(tree)):
        if i == index:
            return candidate if type(candidate) is expected else None
    return None


def collect(path: Path) -> list[Mutant]:
    original = path.read_text(encoding="utf-8")
    tree = ast.parse(original, filename=str(path))
    collector = _Collector(path, original)
    collector.index_tree(tree)
    collector.visit(tree)
    return collector.mutants


def _run_tests(tests: str, extra: list[str]) -> bool:
    """True if the selected tests PASS."""
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pytest", "-q", "-x", "--no-header", tests, *extra],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


class BaselineNotGreen(RuntimeError):
    """The selected tests do not pass BEFORE any mutation is applied."""


def run(paths: list[Path], tests: str, extra: list[str], limit: int | None) -> list[Mutant]:
    # Establish a green baseline FIRST. `_run_tests` reports "killed" for any
    # non-zero exit, and pytest exits non-zero for collection errors, import
    # errors and no-tests-collected alike — so a suite that never ran an
    # assertion scored every mutant as killed and printed "no surviving
    # mutants". A tool whose whole purpose is certifying that tests CAN fail had
    # no way to notice that it could not itself fail.
    print("baseline: running the selected tests unmutated...")
    if not _run_tests(tests, extra):
        raise BaselineNotGreen(
            f"the selected tests do not pass before any mutation: {tests} {' '.join(extra)}. "
            "Every mutant would score as 'killed' and the sweep would report a "
            "perfect result for a suite that never ran."
        )

    mutants: list[Mutant] = []
    for path in paths:
        mutants.extend(collect(path))
    if limit is not None:
        mutants = mutants[:limit]

    print(f"{len(mutants)} mutant(s) over {len(paths)} file(s); tests = {tests} {' '.join(extra)}")
    survivors: list[Mutant] = []
    for i, m in enumerate(mutants, 1):
        original = m.path.read_text(encoding="utf-8")
        # Restore in a `finally`, and leave a recovery copy while mutated.
        #
        # "ALWAYS restore" was overstated: `finally` runs for KeyboardInterrupt
        # but NOT for SIGTERM (which is what a cancelled CI job sends), SIGKILL,
        # or a hard crash. And the file written meanwhile is `ast.unparse`
        # output — every comment stripped and all formatting normalised, which
        # in this codebase means losing the record of every prior finding.
        # The sidecar makes that state detectable and recoverable instead of
        # silent; `main` refuses to start if one is already present.
        sidecar = m.path.with_suffix(m.path.suffix + ".sweep-orig")
        _atomic_write(sidecar, original)
        try:
            _atomic_write(m.path, m.source)
            passed = _run_tests(tests, extra)
        finally:
            _atomic_write(m.path, original)
            sidecar.unlink(missing_ok=True)
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
    stale = [p for p in paths if p.with_suffix(p.suffix + ".sweep-orig").is_file()]
    if stale:
        names = ", ".join(str(p) for p in stale)
        print(
            f"a previous sweep did not finish and left a recovery copy for: {names}. "
            "Those files may be comment-stripped `ast.unparse` output. Restore each "
            "from its .sweep-orig sidecar (or git) and delete the sidecar before "
            "running again.",
            file=sys.stderr,
        )
        return 2
    missing = [p for p in paths if not p.is_file()]
    if missing:
        print(f"no such file(s): {', '.join(str(p) for p in missing)}", file=sys.stderr)
        return 2

    try:
        survivors = run(paths, args.tests, extra, args.limit)
    except BaselineNotGreen as exc:
        print(f"BASELINE NOT GREEN: {exc}", file=sys.stderr)
        return 2
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
