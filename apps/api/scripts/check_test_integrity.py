"""W8a tier 1: static sweep for tests that cannot fail (#72).

Nine recorded instances of a test that passes whether or not the fix it guards
is present. Instances 8 and 9 were written by someone who had read the
`CLAUDE.md` rule that same day, which is the whole argument for a mechanism.

**What this does and does not cover, stated because overstating it would be the
#72 pattern one level up.** This is the cheap, deterministic, blocking tier. It
catches roughly a third of the recorded instances. It is structurally blind to:

- instance 2 — a test whose SETUP performs the step the code under test is
  supposed to perform (`test_deliverable_release.py` writing `parent_version`
  and then re-releasing). No static signature exists for this.
- instance 9 — a keyword argument deletable with the whole suite green. Nothing
  in the test's text is wrong; the omission is in what it never exercised.

And two evasions that are one line each, listed because a blind-spot section
that omits the EASIEST ways past it will be read as exhaustive:

- **TI001 sees only `from X import Y`.** `import app.routes.csf as csf` followed
  by `csf._DIM_FIELDS` is invisible — plain `Import` is not visited and attribute
  access is not inspected.
- **TI002 needs the `str(...)` at the comparison site.** `needle = str(total)` on
  one line and `assert needle in blob` on the next is not flagged, because
  `test.left` is then a bare `Name`.

Neither is exploited today and both are inherent to a two-second AST pass. They
are recorded rather than fixed: widening TI002 to bare names was measured at 36
false positives against 2 real ones, and a rule that noisy gets muted.

Those need diff-scoped mutation testing, which is tier 2 and runs on a schedule
rather than as a gate (the full unit suite is 13-16 min, so 50-150 mutants
cannot sit in front of a PR). A non-blocking mechanism that runs beats a
blocking one that gets disabled.

Both signals demand a written justification rather than forbidding the pattern,
because in both cases the same syntax is sometimes correct:

- `from app.ai.jobs import _CSF_SCORE_PROMPT` in a contract test is RIGHT — the
  prompt is the spec being checked. `from app.routes.csf import _DIM_FIELDS` to
  build the expected response is instance 1. No static rule separates them.
- `assert str(total) in blob` is defensible when the haystack provably contains
  no other numeric cell — but only if someone has checked, which is exactly
  what the marker records.

Marker: `# test-integrity: <reason>` on the offending line or the line above.
An empty reason is not a reason.

Usage:
    python -m scripts.check_test_integrity [TESTS_ROOT]
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

MARKER = "# test-integrity:"

#: Modules whose private names are the SUBJECT of a test rather than a shortcut
#: into it. `scripts._common` is a shared test helper; counting it was how the
#: first noise estimate for this rule came out at 5 hits instead of 4.
_HELPER_PREFIXES = ("scripts.", "tests.", ".")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    code: str
    message: str


def _justified(lines: list[str], lineno: int) -> bool:
    """A non-empty `# test-integrity:` reason on this line, or in the comment
    block directly above it.

    The whole block is scanned, not just the adjacent line: a justification worth
    demanding is usually a paragraph, and the real reasons written for this
    checker's own first run all ran to three or four lines. Requiring the marker
    to be the LAST line of its own explanation would have taught people to write
    one-line reasons, which is the opposite of the point.
    """
    idx = lineno - 1
    if 0 <= idx < len(lines) and MARKER in lines[idx]:
        return bool(lines[idx].split(MARKER, 1)[1].strip())
    # Walk up through the contiguous comment block immediately above.
    idx -= 1
    while idx >= 0 and lines[idx].lstrip().startswith("#"):
        if MARKER in lines[idx]:
            return bool(lines[idx].split(MARKER, 1)[1].strip())
        idx -= 1
    return False


def _is_app_module(module: str | None, level: int) -> bool:
    """True for `app.*` — the code under test — and not for test helpers."""
    if level:  # relative import: a sibling test helper
        return False
    if not module:
        return False
    if module.startswith(_HELPER_PREFIXES):
        return False
    return module == "app" or module.startswith("app.")


def _is_constant_name(name: str) -> bool:
    """`_UPPER_SNAKE` — a module constant, not a helper function."""
    return name.startswith("_") and name.lstrip("_").isupper()


def _is_explicitly_stringified(node: ast.expr) -> bool:
    """Did the author convert a value to text in order to search for it?

    That is the defect's fingerprint. A bare `x in y` is NOT flagged: it cannot
    be told apart from `key in mapping` or `code in {"a", "b"}` without types,
    and on this tree 36 of 38 such assertions are collection membership. Both
    recorded instances of this defect (8, and its twin in the same file) wrote
    `str(...)` explicitly.
    """
    if isinstance(node, ast.Call):
        return isinstance(node.func, ast.Name) and node.func.id == "str"
    return isinstance(node, ast.JoinedStr)


def _needle_has_literal_anchor(node: ast.expr) -> bool:
    """Does the searched-for value carry literal text of its own?

    `f"{n} gap(s) at target T4"` does; `str(n)`, `f"{n}"` and a bare `n` do not.
    That difference is exactly the fix applied to instance 8, where
    `str(dash["total_gap_count"]) in doc_summary` was satisfied by the coverage
    fraction `106/106 subcategories scored`.
    """
    if isinstance(node, ast.Constant):
        # A literal needle is fine — including a non-string one, which is not
        # substring containment at all.
        return True
    if isinstance(node, ast.JoinedStr):
        return any(
            isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value.strip()
            for v in node.values
        )
    return False


def _haystack_may_be_a_string(node: ast.expr) -> bool:
    """Exclude obvious collection membership — that cannot match by coincidence.

    `x in {"a", "b"}` / `x in [1, 2]` are set membership. Only a string haystack
    can be satisfied by an unrelated substring, which is the defect.
    """
    return not isinstance(node, (ast.Set, ast.List, ast.Tuple, ast.Dict))


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str, lines: list[str]) -> None:
        self.path = path
        self.lines = lines
        self.findings: list[Finding] = []

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if _is_app_module(node.module, node.level):
            # CONSTANTS only. The #72 shape is a test deriving its expected
            # VALUES from the module's own data — `_PARSER_ROW_KEYS`,
            # `_DIM_FIELDS`. A private CALLABLE is a different, legitimate
            # pattern: `_llm_dep` and `_storage_dep` are FastAPI
            # dependency-override keys, and importing them says nothing about
            # what the test asserts. Measured on this tree, flagging every
            # private name gives 41 findings of which 36 are override handles;
            # restricting to constant-style names gives 5, and they are exactly
            # the instance-1 shape. A rule whose signal is 12% of its output
            # gets muted, and a muted rule is worth nothing.
            private = [a.name for a in node.names if _is_constant_name(a.name)]
            if private and not _justified(self.lines, node.lineno):
                self.findings.append(
                    Finding(
                        path=self.path,
                        line=node.lineno,
                        code="TI001",
                        message=(
                            f"imports private {', '.join(private)} from {node.module} — a test "
                            "that derives what it checks from the thing it checks cannot fail. "
                            f"Justify with `{MARKER} <reason>` if this is the spec, not a shortcut."
                        ),
                    )
                )
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:  # noqa: N802
        self._check_containment(node.test, node.lineno)
        self.generic_visit(node)

    def _check_containment(self, test: ast.expr, lineno: int) -> None:
        if not isinstance(test, ast.Compare) or len(test.ops) != 1:
            return
        # `not in` cannot pass by coincidence — a stray match makes it FAIL.
        if not isinstance(test.ops[0], ast.In):
            return
        if not _haystack_may_be_a_string(test.comparators[0]):
            return
        if not _is_explicitly_stringified(test.left):
            return
        if _needle_has_literal_anchor(test.left):
            return
        if _justified(self.lines, lineno):
            return
        self.findings.append(
            Finding(
                path=self.path,
                line=lineno,
                code="TI002",
                message=(
                    "containment assertion whose needle carries no literal text — it can be "
                    "satisfied by an unrelated coincidence in the haystack (instance 8: "
                    '"106/106 subcategories scored" contains "106"). Anchor it, e.g. '
                    f'f"{{n}} gap(s) at target T4", or justify with `{MARKER} <reason>`.'
                ),
            )
        )


def scan_source(path: str, source: str) -> list[Finding]:
    """Findings for one file's text. Raises on a syntax error rather than skipping."""
    tree = ast.parse(source, filename=path)
    visitor = _Visitor(path, source.splitlines())
    visitor.visit(tree)
    return sorted(visitor.findings, key=lambda f: (f.line, f.code))


class CannotScan(Exception):
    """This gate could not read its input, which is not the same as clean.

    Its anticipated failures, decided here rather than inherited: a root that is
    not a directory, a root holding no `test_*.py` at all, a file that cannot be
    read or decoded, and a file that cannot be parsed. Every one of them used to
    end at the same `return 0` as a genuinely clean tree -- `rglob` on a missing
    path yields nothing, so `python -m scripts.check_test_integrity /nope`
    printed "test-integrity: clean" and exited **0**.

    **This was latent, not live.** `ci.yml`'s test-integrity step carries
    `working-directory: apps/api`, so the relative `tests` it passes has always
    resolved and the gate has always been reading real files in CI. The exposure
    is sharper than a live defect anyway: this gate's correctness lived in a
    `working-directory:` line in a DIFFERENT file, and nothing checks that line.
    Drop it, or reorder the step above something that changes directory, and the
    gate goes green and blind with no signal at all. What follows turns that
    from silent into exit 2.

    The shape is `check_audit_evidence`'s recorded defect -- an empty
    changed-file list reading as "documentation-only, exempt" -- in a second
    gate, and it is why D-051 asks for a checker's silent-success branches to be
    enumerated before its first line rather than found in review.
    """


def scan_tree(root: Path) -> list[Finding]:
    """Every `test_*.py` under `root`, sorted for a stable report.

    Raises `CannotScan` rather than returning `[]` for input it could not read:
    "I found nothing wrong" and "I could not look" must not share a branch.
    """
    if not root.is_dir():
        raise CannotScan(f"{root} is not a directory")
    paths = sorted(root.rglob("test_*.py"))
    if not paths:
        raise CannotScan(f"no test_*.py found under {root}")
    findings: list[Finding] = []
    for path in paths:
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CannotScan(f"cannot read {rel}: {type(exc).__name__}: {exc}") from exc
        try:
            findings.extend(scan_source(rel, source))
        except SyntaxError as exc:
            raise CannotScan(f"cannot parse {rel}: {exc}") from exc
    return findings


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1] / "tests"
    try:
        findings = scan_tree(root)
    except CannotScan as exc:
        print(f"test-integrity: cannot scan: {exc}", file=sys.stderr)
        print("Refusing to report clean on input it could not read (D-051).", file=sys.stderr)
        return 2
    for f in findings:
        print(f"{f.path}:{f.line}: {f.code} {f.message}")
    if findings:
        print(f"{chr(10)}{len(findings)} unjustified finding(s).", file=sys.stderr)
        return 1
    print(f"test-integrity: clean ({root})")
    return 0


if __name__ == "__main__":
    # A crash must NOT share an exit code with "violations found". Python exits
    # 1 on an unhandled exception, which is this gate's "found something" code,
    # so an uncaught error would read as a verdict it never reached.
    #
    # `BaseException` with both propagating cases NAMED, rather than the
    # equivalent `except Exception`: a handler that says out loud what it
    # declines to swallow does not rely on the reader knowing the inheritance
    # tree. `SystemExit` is somebody's deliberate exit code. `KeyboardInterrupt`
    # is an operator who knows exactly what happened and is owed 130, not
    # "could not look".
    #
    # Duplicated verbatim in all eight gates rather than shared -- an import is
    # one more thing that can fail BEFORE the handler is installed, which is the
    # defect this block exists to close. Drift is caught instead by
    # tests/unit/test_gate_crash_exit_code.py, which runs every one of them.
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"test-integrity: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(2) from exc
