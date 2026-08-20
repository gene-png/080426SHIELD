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


def scan_tree(root: Path) -> list[Finding]:
    """Every `test_*.py` under `root`, sorted for a stable report."""
    findings: list[Finding] = []
    for path in sorted(root.rglob("test_*.py")):
        rel = path.relative_to(root).as_posix()
        findings.extend(scan_source(rel, path.read_text(encoding="utf-8")))
    return findings


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1] / "tests"
    findings = scan_tree(root)
    for f in findings:
        print(f"{f.path}:{f.line}: {f.code} {f.message}")
    if findings:
        print(f"\n{len(findings)} unjustified finding(s).", file=sys.stderr)
        return 1
    print(f"test-integrity: clean ({root})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
