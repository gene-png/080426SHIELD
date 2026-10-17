"""Prove a PR's test edits change only expected literals, so the advisor's mechanical pre-approval applies.

    python -m scripts.check_literal_test_edits --base REF --head REF --body FILE [--repo DIR]
    python -m scripts.check_literal_test_edits --old-tree DIR --new-tree DIR --body FILE

WHY. #736 6234238148 item 1: "A test edit that changes only expected literals
(numbers or strings) on existing assertion lines, following a behavior change I
have already approved on #736, may merge without waiting for me when a checker
passes." This is that checker. It must fail closed, and refuse: any removed
assertion; any changed assertion subject, matcher or operator; any new, renamed
or deleted test; any change outside literals; a literal edit with no approved
behavior change cited. The advisor audits every such merge afterwards, and a
miss ends the pre-approval, so this prints each literal edit it let through.

WHAT COUNTS AS "ONLY LITERALS". Both versions of a test file are tokenised. A
number or string token (an f-string's text included) is replaced by a
placeholder of its kind, and the two token streams must then be IDENTICAL:
every name, operator, bracket, keyword, comment, decorator and indentation. That
single test refuses a removed or added assertion, a changed subject, matcher or
operator (`==` to `>=`, `in` to `not in`), a renamed or new test, a new
argument and an edited comment, because each changes a non-literal token. Line
breaks inside brackets are not tokens that matter, so a reflow is not a change.
Only if the streams match are the changed literals judged one by one:

    * a literal must be an EXPECTED VALUE: a direct operand of `==` or `in` in
      an `assert` statement (through tuples, lists, sets, dicts, a unary minus
      and the text of an f-string, under `and`). A literal anywhere else is
      refused, because token-for-token it still looks like "a literal edit":
      a call argument, a bound or ordering (`<`, `!=`, `not in`), a `range` or
      slice, a skip or `importorskip` condition, a regex or `match=`, a
      tolerance, a `parametrize` value or id, a docstring, or a triple-quoted
      string that holds source. Each of those can disable a test with CI green;
    * a string made EMPTY or BLANK is refused: `"x" in text` with an empty or
      whitespace needle always passes, which weakens the test while changing
      "only a literal";
    * a number must stay a number and a string a string (None, True, a name or
      another kind in a literal's place changes the token kind, refused above).

SCOPE, stated plainly. Only Python test files are machine-checkable here. A
changed test file that is not Python (a vitest or Playwright spec, a fixture's
JSON) is REFUSED as "not machine-checkable": it still goes to the advisor. A
file under a test path that is added or deleted is refused. A changed file that
is not a test file (the behavior change itself) is listed as not judged, EXCEPT a file that decides what runs or how a gate judges (pytest or vitest config, a conftest, a workflow, a gate or shard script), which is refused. The citation is
checked for FORM only (`Approved-behavior-comment: <comment id>` on a line of
its own in the PR body); that the comment exists and is the advisor's is the
advisor's audit, and this cannot see it.

Exit codes (D-090): 0 every changed test file differs only in literals, and a
behavior change is cited; 1 a finding, each named; 2 could not look -- an
argument missing or unknown, an unreadable tree, ref, diff or body, a test file
that does not tokenise, or NO test file differing at all (an empty read is never
"clean").
"""

from __future__ import annotations

import ast
import io
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

_TEST_PATH = re.compile(
    r"^(apps/api/tests/|e2e/|apps/web/.+\.(test|spec)\.tsx?$)",
)
#: A non-test file that decides WHAT RUNS or HOW A GATE JUDGES: changing one beside a
#: literal-only test edit can switch tests off without touching a test file, so the
#: pre-approval does not cover it.
_DECIDES_TESTS = re.compile(
    r"(^|/)(pyproject\.toml|pytest\.ini|setup\.cfg|tox\.ini|conftest\.py|"
    r"(vitest|playwright)(\.setup|\.config)[^/]*)$"
    r"|^\.github/workflows/|^apps/api/scripts/(check_|shard_|preflight|mutation|leave_row)"
)
#: A line of its own in the PR body. Digits only, long enough to be a comment id.
_CITATION = re.compile(r"^Approved-behavior-comment:[ \t]*(\d{7,})[ \t]*$", re.MULTILINE)
_LITERAL_KINDS = {tokenize.NUMBER, tokenize.STRING}
_FSTRING_TEXT = getattr(tokenize, "FSTRING_MIDDLE", -1)
_IGNORED = {tokenize.NL, tokenize.ENCODING, tokenize.ENDMARKER}


class _CouldNotLook(Exception):
    pass


@dataclass
class Result:
    findings: list[str] = field(default_factory=list)
    edits: list[str] = field(default_factory=list)
    files: int = 0
    unjudged: list[str] = field(default_factory=list)


def is_test_path(path: str) -> bool:
    return bool(_TEST_PATH.match(path))


# --- one Python file, old against new ---------------------------------------------


def _tokens(source: str, path: str) -> list[tokenize.TokenInfo]:
    try:
        return [
            t
            for t in tokenize.generate_tokens(io.StringIO(source).readline)
            if t.type not in _IGNORED
        ]
    except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
        raise _CouldNotLook(f"{path} does not tokenise: {exc}") from exc


def _is_literal(tok: tokenize.TokenInfo) -> bool:
    return tok.type in _LITERAL_KINDS or tok.type == _FSTRING_TEXT


def _shape(tok: tokenize.TokenInfo) -> tuple[int, str]:
    """The token with its literal value blanked: the part that must not change."""
    if _is_literal(tok):
        return (tok.type, "")
    if tok.type in (getattr(tokenize, "FSTRING_START", -1), getattr(tokenize, "FSTRING_END", -2)):
        return (tok.type, "")
    return (tok.type, tok.string)


_SAFE_OPS = (ast.Eq, ast.In)
_NUMBER_NODES = (int, float, complex)


def _pos(node: ast.AST) -> tuple[tuple[int, int], tuple[int, int]]:
    return (node.lineno, node.col_offset), (
        node.end_lineno or node.lineno,
        node.end_col_offset or 0,
    )


def _expected_value_spans(
    source: str, path: str
) -> tuple[
    list[tuple[tuple[int, int], tuple[int, int]]], list[tuple[tuple[int, int], tuple[int, int]]]
]:
    """(safe, unsafe) source spans, as ((line, byte col), (line, byte col)).

    A literal is an EXPECTED VALUE only when it is a direct operand of `==` or
    `in` in an `assert` (through tuples, lists, sets, dicts, a unary minus and the
    text of an f-string), under `and` and nothing else. Everything else is not
    judged here and is refused: a literal inside a call, an index, a slice, a
    `range`, a decorator, a skip or `importorskip`, a regex, a `match=`, a
    tolerance, an ordering or `!=` / `not in` / `is` comparison, a
    `parametrize` value, a docstring, or a string that holds code.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise _CouldNotLook(f"{path} does not parse: {exc}") from exc
    safe: list = []
    unsafe: list = []

    def operand(node: ast.AST) -> None:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (str, bytes, *_NUMBER_NODES)) and not isinstance(
                node.value, bool
            ):
                safe.append(_pos(node))
        elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            for elt in node.elts:
                operand(elt)
        elif isinstance(node, ast.Dict):
            for part in (*node.keys, *node.values):
                if part is not None:
                    operand(part)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            operand(node.operand)
        elif isinstance(node, ast.JoinedStr):
            safe.append(_pos(node))
            for part in node.values:
                if isinstance(part, ast.FormattedValue):
                    unsafe.append(_pos(part))

    def test(node: ast.AST) -> None:
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
            for value in node.values:
                test(value)
        elif isinstance(node, ast.Compare) and all(isinstance(op, _SAFE_OPS) for op in node.ops):
            for part in (node.left, *node.comparators):
                operand(part)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            test(node.test)
    return safe, unsafe


def _inside(inner: tuple[int, int], span: tuple[tuple[int, int], tuple[int, int]]) -> bool:
    return span[0] <= inner < span[1]


def _is_expected_value(tok: tokenize.TokenInfo, source: str, spans) -> bool:
    """Is this literal token inside an expected-value span and outside any f-string expression?"""
    safe, unsafe = spans
    row, col = tok.start
    line = source.splitlines()[row - 1]
    point = (row, len(line[:col].encode("utf-8")))
    return any(_inside(point, sp) for sp in safe) and not any(_inside(point, sp) for sp in unsafe)


def compare_python(path: str, old: str, new: str) -> tuple[list[str], list[str]]:
    """(findings, literal edits) for one Python test file."""
    old_toks, new_toks = _tokens(old, path), _tokens(new, path)
    old_shape, new_shape = [_shape(t) for t in old_toks], [_shape(t) for t in new_toks]
    if old_shape != new_shape:
        at = next(
            (i for i, (a, b) in enumerate(zip(old_shape, new_shape, strict=False)) if a != b),
            min(len(old_shape), len(new_shape)),
        )
        was = old_toks[at].string if at < len(old_toks) else "<end of file>"
        now = new_toks[at].string if at < len(new_toks) else "<end of file>"
        row = (new_toks[at] if at < len(new_toks) else old_toks[-1]).start[0]
        return (
            [
                f"{path}: a change outside literals (first at line {row}: {was!r} became {now!r}); "
                "an assertion, subject, matcher, operator, comment or test changed, so this is not a literal-only edit"
            ],
            [],
        )
    old_spans, new_spans = _expected_value_spans(old, path), _expected_value_spans(new, path)
    findings: list[str] = []
    edits: list[str] = []
    for a, b in zip(old_toks, new_toks, strict=True):
        if not _is_literal(a) or a.string == b.string:
            continue
        row = b.start[0]
        edits.append(f"{path}:{row}: {a.string} -> {b.string}")
        if not (_is_expected_value(a, old, old_spans) and _is_expected_value(b, new, new_spans)):
            findings.append(
                f"{path}:{row}: {a.string} -> {b.string} is not an expected value in an `assert` "
                "(only a direct operand of == or in, in an assert statement, is a literal-only edit; "
                "a call argument, bound, skip condition, regex, parametrize value or embedded source is not)"
            )
        if a.type == tokenize.STRING and b.type == tokenize.STRING:
            try:
                emptied = bool(ast.literal_eval(a.string).strip()) and not (
                    ast.literal_eval(b.string).strip()
                )
            except (ValueError, SyntaxError, AttributeError):
                emptied = False
            if emptied:
                findings.append(
                    f"{path}:{row}: {a.string} -> {b.string}: a string made empty or blank "
                    "(an empty or whitespace needle always matches), which weakens the assertion"
                )
    return findings, edits


# --- which files, old and new ---------------------------------------------------------


def judge(
    changes: dict[str, tuple[str | None, str | None]],
    body: str,
    *,
    others: list[str] | None = None,
    source: str = "",
) -> Result:
    """`changes`: test path -> (old text or None if absent, new text or None if absent);
    `others`: every other changed path (the behavior change, which is not judged)."""
    result = Result()
    for path in sorted(others or []):
        if _DECIDES_TESTS.search(path):
            result.findings.append(
                f"{path}: a file that decides what tests run or how a gate judges changed; "
                "the pre-approval covers test literals only, so this goes to the advisor"
            )
        else:
            result.unjudged.append(path)
    if not _CITATION.search(body):
        result.findings.append(
            "no approved behavior change is cited: the PR body needs a line "
            "`Approved-behavior-comment: <the #736 comment id>`"
        )
    tests = {p: c for p, c in changes.items() if is_test_path(p)}
    if not tests:
        raise _CouldNotLook(f"no test file differs{source}, so there is nothing to certify")
    for path, (old, new) in sorted(tests.items()):
        result.files += 1
        if old is None:
            result.findings.append(f"{path}: a new test file")
        elif new is None:
            result.findings.append(f"{path}: a deleted test file")
        elif not path.endswith(".py"):
            result.findings.append(
                f"{path}: not machine-checkable (only Python test files are covered); it goes to the advisor"
            )
        else:
            found, edits = compare_python(path, old, new)
            result.findings += found
            result.edits += edits
    return result


def _read_tree(root: Path) -> tuple[dict[str, str], dict[str, bytes]]:
    """(test files as text, every other file as bytes)."""
    if not root.is_dir():
        raise _CouldNotLook(f"{root} is not a directory")
    tests: dict[str, str] = {}
    others: dict[str, bytes] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        try:
            if is_test_path(rel):
                tests[rel] = path.read_text(encoding="utf-8")
            else:
                others[rel] = path.read_bytes()
        except (OSError, UnicodeDecodeError) as exc:
            raise _CouldNotLook(f"cannot read {path}: {exc}") from exc
    return tests, others


def changes_from_trees(
    old_root: Path, new_root: Path
) -> tuple[dict[str, tuple[str | None, str | None]], list[str]]:
    """(changed test files, every other changed path)."""
    (old, old_o), (new, new_o) = _read_tree(old_root), _read_tree(new_root)
    tests = {
        p: (old.get(p), new.get(p)) for p in sorted(set(old) | set(new)) if old.get(p) != new.get(p)
    }
    others = [p for p in sorted(set(old_o) | set(new_o)) if old_o.get(p) != new_o.get(p)]
    return tests, others


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, refs from the command line
            ["git", "-C", str(repo), *args],  # noqa: S607 - git from PATH
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError as exc:
        raise _CouldNotLook(f"cannot run git: {exc}") from exc
    if proc.returncode != 0:
        raise _CouldNotLook(
            f"`git {' '.join(args)}` exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout


def changes_from_git(
    repo: Path, base: str, head: str
) -> tuple[dict[str, tuple[str | None, str | None]], list[str]]:
    """(changed test files, every other changed path) between the MERGE BASE and head."""
    mb = _git(repo, "merge-base", base, head).strip()
    names = _git(repo, "diff", "--name-status", "--no-renames", "-z", mb, head).split("\0")
    changes: dict[str, tuple[str | None, str | None]] = {}
    others: list[str] = []
    items = [n for n in names if n]
    if len(items) % 2:
        raise _CouldNotLook("git diff --name-status -z gave an odd number of fields")
    for status, path in zip(items[0::2], items[1::2], strict=True):
        if status[0] not in "MAD":
            raise _CouldNotLook(f"{path}: git status {status!r} is not modified, added or deleted")
        if not is_test_path(path):
            others.append(path)
            continue
        old = None if status[0] == "A" else _git(repo, "show", f"{mb}:{path}")
        new = None if status[0] == "D" else _git(repo, "show", f"{head}:{path}")
        changes[path] = (old, new)
    return changes, sorted(others)


# --- the command ----------------------------------------------------------------------


def _parse(argv: list[str]) -> dict[str, str]:
    allowed = {"--base", "--head", "--body", "--repo", "--old-tree", "--new-tree"}
    opts: dict[str, str] = {}
    it = iter(argv[1:])
    for arg in it:
        if arg not in allowed:
            raise _CouldNotLook(f"unexpected argument {arg!r}")
        value = next(it, None)
        if value is None:
            raise _CouldNotLook(f"{arg} given with no value")
        opts[arg] = value
    git_mode = {"--base", "--head"} <= set(opts)
    tree_mode = {"--old-tree", "--new-tree"} <= set(opts)
    if "--body" not in opts or git_mode == tree_mode:
        raise _CouldNotLook(
            "usage: --body FILE with either --base REF --head REF [--repo DIR] "
            "or --old-tree DIR --new-tree DIR (not both, not neither)"
        )
    if git_mode and ({"--old-tree", "--new-tree"} & set(opts)):
        raise _CouldNotLook("--base/--head and --old-tree/--new-tree cannot be mixed")
    if tree_mode and ({"--base", "--head", "--repo"} & set(opts)):
        raise _CouldNotLook("--old-tree/--new-tree and --base/--head/--repo cannot be mixed")
    return opts


def main(argv: list[str]) -> int:
    try:
        opts = _parse(argv)
        try:
            body = Path(opts["--body"]).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise _CouldNotLook(f"cannot read the PR body {opts['--body']}: {exc}") from exc
        if "--base" in opts:
            changes, others = changes_from_git(
                Path(opts.get("--repo", ".")), opts["--base"], opts["--head"]
            )
            source = f" between {opts['--base']} and {opts['--head']}"
        else:
            changes, others = changes_from_trees(Path(opts["--old-tree"]), Path(opts["--new-tree"]))
            source = ""
        result = judge(changes, body, others=others, source=source)
    except _CouldNotLook as exc:
        print(f"check-literal-test-edits: could not look -- {exc}")
        return 2
    for line in result.edits:
        print(f"check-literal-test-edits: literal edit {line}")
    if result.findings:
        print(
            f"check-literal-test-edits: {len(result.findings)} finding(s), not a literal-only edit:"
        )
        for line in result.findings[:50]:
            print(f"  {line}")
        if len(result.findings) > 50:
            print(f"  ... and {len(result.findings) - 50} more")
        return 1
    for path in result.unjudged:
        print(f"check-literal-test-edits: not judged (not a test file): {path}")
    print(
        f"check-literal-test-edits: clean -- {len(result.edits)} literal edit(s) in "
        f"{result.files} test file(s), and a behavior change is cited. The citation's "
        "existence and author are the advisor's audit, not this check's."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-literal-test-edits: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a verdict and not a finding (D-090).{nl}")
        raise SystemExit(2) from exc
