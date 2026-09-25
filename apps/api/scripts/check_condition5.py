#!/usr/bin/env python3
r"""Merge-rule condition 5, with the executable-line exception.

WHY THIS EXISTS. Condition 5 routes a PR to the human when it touches a path
where a green suite proves least. #530 is the instance that motivated narrowing
it: its entire `docker-compose.yml` diff was comments -- nothing that runs
changed -- and it still came back. The owner's rule (2026-09-24): **a diff that
changes no EXECUTABLE line in a condition-5 path does not trip condition 5.**
Comments, docstrings and landing entries cannot alter behaviour. That makes the
exception mechanical, unlike the status-based narrowing measured and rejected
earlier, so it is computed here rather than attested.

WHAT IT DECIDES, AND WHAT IT DOES NOT. It decides condition 5 over the paths it
knows. By default those are DERIVED from `CLAUDE.md`'s `### Condition 5: the
paths` section -- the indented list directly under the heading, which the
bullets below it explain -- so the list cannot drift from the file that defines
it. It does NOT re-derive the "does any
workflow execute it as a gate" set. That derivation was withdrawn from
`check_merge_rule_conditions.py` because it could not see every invocation
spelling, and it stays with the human here too. A PR touching an invoked script
this list does not name is exactly as self-attested as before.

WHAT COUNTS AS AN EXECUTABLE CHANGE, per file type. Every rule leans toward
"executable" when unsure, because a false "not tripped" merges unattended and a
false "tripped" only asks the owner.

  * `.py`: the AST with docstrings removed, compared old against new. Comments
    are invisible to the AST, EXCEPT tool directives (`noqa`, `nosec`,
    `type:`, `pragma`, `fmt:`, `test-integrity:`, `pylint:`, `mypy:`). Those
    change what a gate or linter does, so a changed directive is executable. A
    file that reads `__doc__` treats its docstrings as executable, since they
    are then output.
  * `.yml` / `.yaml` / `.json`: the parsed object. A comment or reflow leaves it
    equal. A shell comment INSIDE a `run:` string changes the object, and so
    counts; that is deliberate.
  * shell (`.sh`, `.bash`, or a shell shebang): every line except full-line `#`
    comments and blank lines. If the file contains a heredoc (`<<`), every line
    counts, because a `#` line inside a heredoc is data, not a comment.
  * data and documents -- `.md`, `.txt`, `.csv`, `.toml`, `.ini`, `.cfg`,
    `.env` -- and ANY file under a `gates/` or `fixtures/` directory: every line
    counts. Fixtures are inputs to gates, and the PR template's text is what the
    gates parse.
  * added, deleted or renamed files: executable.
  * ANYTHING ELSE -- TypeScript/JavaScript, binaries, unknown types -- is
    unclassifiable: exit 2, which the merge rule reads as tripped. TS/JS lacks a
    lexer here: a `//` or `*` line can sit inside a template literal, so a
    line-based guess would clear lines that execute.

`--report` is the CI form (audit-gate.yml): it prints the verdict on every PR
and exits 0 whether or not condition 5 trips, because tripping is a ROUTING
fact (the PR comes back to the human), not a defect in the PR. It still exits 2
when it could not look, so the step can fail. In report mode an unclassifiable
file is printed as tripping rather than stopping the report.

EXIT CODES (the gates' 0/1/2 convention): 0 no listed path changed executably
(either none was touched, or every change in one was non-executable); 1 at
least one executable change in a listed path, so condition 5 is TRIPPED; 2
could not look -- no changed files, the path source unreadable or too small to
be the real list, a file in a listed path that cannot be classified or parsed,
a missing root, a git failure, or an unknown argument. Exit 2 is never clean.
"""

from __future__ import annotations

import ast
import fnmatch
import io
import json
import re
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path

MIN_PATHS = 10
_SECTION = re.compile(r"^### Condition 5: the paths\s*$", re.M)
_NEXT_HEADING = re.compile(r"^#{2,3} ", re.M)
_DIRECTIVE = re.compile(r"#\s*(noqa|nosec|type:|pragma|fmt:|test-integrity:|pylint:|mypy:)", re.I)
_DATA_SUFFIXES = {".md", ".txt", ".csv", ".toml", ".ini", ".cfg", ".env"}
_SHELL_SUFFIXES = {".sh", ".bash"}
_STRUCTURED = {".yml", ".yaml", ".json"}


class CouldNotLook(Exception):
    """The gate could not establish the answer. Maps to exit 2, never 0 or 1."""


# --- the path list ---------------------------------------------------------------


def paths_from_claude_md(text: str) -> list[str]:
    """The indented list directly under `### Condition 5: the paths`.

    NOT the backticked tokens of the prose. The first draft read those, and the
    prose names paths it EXCLUDES ("widening to `apps/web/**` would expand
    scope", "not nothing under `alembic/`"), so every web change and every
    alembic file would have tripped condition 5. The list is the machine source;
    the bullets explain it; `test_condition5_gate.py` pins that every listed path
    is also named in the bullets.
    """
    m = _SECTION.search(text)
    if not m:
        raise CouldNotLook("no `### Condition 5: the paths` section in the CLAUDE.md given")
    rest = text[m.end() :]
    nxt = _NEXT_HEADING.search(rest)
    section = rest[: nxt.start()] if nxt else rest
    found: list[str] = []
    started = False
    for line in section.splitlines():
        if line.startswith("    ") and line.strip() and not line.lstrip().startswith("-"):
            found.append(line.strip())
            started = True
        elif started and line.strip():
            break
    if len(found) < MIN_PATHS:
        raise CouldNotLook(
            f"found {len(found)} path(s) in the condition-5 list, fewer than "
            f"{MIN_PATHS}: the list moved or changed shape, and a short list is "
            "not the real one"
        )
    return found


def paths_from_file(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CouldNotLook(f"cannot read {path}: {exc}") from exc
    found = [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]
    if not found:
        raise CouldNotLook(f"{path} lists no paths")
    return found


def is_listed(path: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if fnmatch.fnmatchcase(path, pat):
            return True
        if pat.endswith("/**") and path.startswith(pat[:-2]):
            return True
        # `apps/web/**/*.test.ts` must also match a file directly under apps/web/.
        if "/**/" in pat and fnmatch.fnmatchcase(path, pat.replace("/**/", "/")):
            return True
    return False


# --- executable-line classification ---------------------------------------------


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return tree


def _directives(src: str) -> list[str]:
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT and _DIRECTIVE.search(tok.string):
                out.append(tok.string.strip())
    except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
        raise CouldNotLook(f"cannot tokenize: {exc}") from exc
    return out


def python_changed(old: str, new: str, name: str) -> bool:
    try:
        t_old, t_new = ast.parse(old), ast.parse(new)
    except SyntaxError as exc:
        raise CouldNotLook(f"{name} does not parse as Python: {exc}") from exc
    if _directives(old) != _directives(new):
        return True
    if "__doc__" in old or "__doc__" in new:
        return ast.dump(t_old) != ast.dump(t_new)
    return ast.dump(_strip_docstrings(t_old)) != ast.dump(_strip_docstrings(t_new))


def structured_changed(old: str, new: str, name: str, suffix: str) -> bool:
    if suffix == ".json":
        try:
            return json.loads(old) != json.loads(new)
        except ValueError as exc:
            raise CouldNotLook(f"{name} does not parse as JSON: {exc}") from exc
    try:
        import yaml  # lazy: only a YAML change needs it
    except ImportError as exc:
        raise CouldNotLook(
            f"{name}: PyYAML is not installed, so a YAML change cannot be classified"
        ) from exc
    try:
        return yaml.safe_load(old) != yaml.safe_load(new)
    except yaml.YAMLError as exc:
        raise CouldNotLook(f"{name} does not parse as YAML: {exc}") from exc


def shell_changed(old: str, new: str) -> bool:
    if "<<" in old or "<<" in new:
        return old != new

    def code_lines(src: str) -> list[str]:
        lines = src.splitlines()
        return [
            ln.rstrip()
            for i, ln in enumerate(lines)
            if ln.strip()
            and not (ln.lstrip().startswith("#") and not (i == 0 and ln.startswith("#!")))
        ]

    return code_lines(old) != code_lines(new)


def _is_shell(path: str, old: str, new: str) -> bool:
    if Path(path).suffix in _SHELL_SUFFIXES:
        return True
    first = (new or old).splitlines()[:1]
    return (
        bool(first)
        and first[0].startswith("#!")
        and re.search(r"\b(ba)?sh\b", first[0]) is not None
    )


def classify(path: str, old: str | None, new: str | None) -> bool:
    """True if the change to `path` is executable. Raises CouldNotLook if unclassifiable."""
    if old is None or new is None:
        return True  # added or deleted
    if old == new:
        return False
    parts = Path(path).parts
    suffix = Path(path).suffix.lower()
    if "gates" in parts or "fixtures" in parts or suffix in _DATA_SUFFIXES:
        return True
    if suffix == ".py":
        return python_changed(old, new, path)
    if suffix in _STRUCTURED:
        return structured_changed(old, new, path, suffix)
    if _is_shell(path, old, new):
        return shell_changed(old, new)
    raise CouldNotLook(
        f"{path}: cannot classify a `{suffix or 'no extension'}` file, so whether "
        "its change is executable is unknown -- read as TRIPPED"
    )


# --- inputs ----------------------------------------------------------------------


def _read(root: Path, rel: str) -> str | None:
    p = root / rel
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise CouldNotLook(f"{rel} is not UTF-8 text (binary?): cannot classify") from exc


def _run_git(repo: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(  # noqa: S603  # nosec B603 - fixed argv
            ["git", "-C", str(repo), *args],  # noqa: S607
            capture_output=True,
            text=text,
            encoding="utf-8" if text else None,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CouldNotLook("`git` is not installed here, so the range cannot be read") from exc


def _git(repo: Path, *args: str) -> str:
    proc = _run_git(repo, *args)
    if proc.returncode != 0:
        raise CouldNotLook(
            f"`git {' '.join(args)}` exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout


def materialise_range(repo: Path, rng: str, tmp: Path) -> tuple[Path, Path, list[str]]:
    if ".." not in rng:
        raise CouldNotLook(f"--range must be BASE..HEAD, got {rng!r}")
    base, head = rng.split("..", 1)
    names = [ln for ln in _git(repo, "diff", "--name-only", f"{base}...{head}").splitlines() if ln]
    old_root, new_root = tmp / "old", tmp / "new"
    merge_base = _git(repo, "merge-base", base, head).strip()
    for rel in names:
        for root, ref in ((old_root, merge_base), (new_root, head)):
            proc = _run_git(repo, "show", f"{ref}:{rel}", text=False)
            if proc.returncode == 0:
                dest = root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(proc.stdout)
    return old_root, new_root, names


def _parse(argv: list[str]) -> dict:
    opts: dict = {}
    args = list(argv[1:])
    flags = (
        "--old-root",
        "--new-root",
        "--changed-files",
        "--claude-md",
        "--paths-file",
        "--range",
        "--repo",
    )
    while args:
        flag = args.pop(0)
        if flag == "--report":
            opts[flag] = True
        elif flag in flags and args:
            opts[flag] = args.pop(0)
        else:
            raise CouldNotLook(f"unknown or incomplete argument: {flag!r}")
    return opts


def evaluate(
    patterns: list[str], names: list[str], old_root: Path, new_root: Path, *, report: bool = False
) -> tuple[list[str], list[str]]:
    """(tripping files, listed files changed only non-executably).

    In report mode an unclassifiable file is listed as tripping instead of
    raising: the verdict is the same (it comes back to the human), and the
    report must still be printed for every other file.
    """
    tripping, cleared = [], []
    for rel in names:
        if not is_listed(rel, patterns):
            continue
        try:
            executable = classify(rel, _read(old_root, rel), _read(new_root, rel))
        except CouldNotLook as exc:
            if not report:
                raise
            tripping.append(f"{rel} (unclassifiable, read as tripped: {exc})")
            continue
        (tripping if executable else cleared).append(rel)
    return tripping, cleared


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        opts = _parse(argv)
        if "--paths-file" in opts:
            patterns = paths_from_file(Path(opts["--paths-file"]))
        else:
            cm = Path(opts.get("--claude-md", "CLAUDE.md"))
            try:
                patterns = paths_from_claude_md(cm.read_text(encoding="utf-8"))
            except OSError as exc:
                raise CouldNotLook(f"cannot read {cm}: {exc}") from exc
        with tempfile.TemporaryDirectory() as tmp:
            if "--range" in opts:
                old_root, new_root, names = materialise_range(
                    Path(opts.get("--repo", ".")), opts["--range"], Path(tmp)
                )
            else:
                missing = [
                    f for f in ("--old-root", "--new-root", "--changed-files") if f not in opts
                ]
                if missing:
                    raise CouldNotLook(
                        f"need --range, or all of --old-root/--new-root/--changed-files (missing {missing})"
                    )
                old_root, new_root = Path(opts["--old-root"]), Path(opts["--new-root"])
                for r in (old_root, new_root):
                    if not r.is_dir():
                        raise CouldNotLook(f"{r} is not a directory")
                try:
                    names = [
                        ln.strip()
                        for ln in Path(opts["--changed-files"])
                        .read_text(encoding="utf-8")
                        .splitlines()
                        if ln.strip()
                    ]
                except OSError as exc:
                    raise CouldNotLook(f"cannot read the changed-file list: {exc}") from exc
            if not names:
                raise CouldNotLook(
                    "no changed files: the diff did not resolve, which is not a clean diff"
                )
            tripping, cleared = evaluate(
                patterns, names, old_root, new_root, report=bool(opts.get("--report"))
            )
    except CouldNotLook as exc:
        print(f"check-condition5: could not look -- {exc}")
        print("  Read as TRIPPED: condition 5 comes back to the human.")
        return 2

    for rel in cleared:
        print(f"  non-executable change only: {rel}")
    if tripping:
        print(f"check-condition5: condition 5 TRIPPED by {len(tripping)} file(s):")
        for rel in tripping:
            print(f"  executable change in a condition-5 path: {rel}")
        if opts.get("--report"):
            print("  (--report: a verdict, not a failure -- a tripped PR comes back to the human.)")
            return 0
        return 1
    how = "every change in one was non-executable" if cleared else "none was touched"
    print(f"check-condition5: condition 5 not tripped -- {len(names)} changed file(s); {how}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-condition5: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation.{nl}")
        raise SystemExit(2) from exc
