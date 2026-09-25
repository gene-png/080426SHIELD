#!/usr/bin/env python3
r"""Merge-rule condition 5, with the executable-line exception.

WHY THIS EXISTS. Condition 5 routes a PR to the human when it touches a path
where a green suite proves least. #530 is the instance that motivated narrowing
it: its entire `docker-compose.yml` diff was comments -- nothing that runs
changed -- and it still came back. The owner's rule (2026-09-24): **a diff that
changes no EXECUTABLE line in a condition-5 path does not trip condition 5.**
Comments, docstrings and landing entries almost never alter behaviour, and the
ones that do -- tool directives, and a gate that reads a comment as wiring
(`check_gate_fixtures.invocation_text`) -- are exactly what the per-type rules
below either count or name as a residual. That makes the exception mechanical, unlike the status-based narrowing measured and rejected
earlier, so it is computed here rather than attested (D-095).

THE PATHS IT JUDGES. Two sources, and in `--range` mode (the CI form) both:

  * the indented list directly under `CLAUDE.md`'s `### Condition 5: the
    paths`, read from git at the MERGE BASE and at the HEAD -- never from the
    PR's own checkout alone, because CLAUDE.md is not a listed path, so a PR
    could delete an entry and edit that file in one diff. The union is judged,
    and a PR that changes the list at all trips.
  * the DERIVED set: every tracked `.py` / `.sh` a workflow `run:` names
    (dotted `-m` modules resolved, `working-directory` applied, `/app/...` and
    bare container paths tried under `apps/api/`); every one a compose
    `command` / `entrypoint` / healthcheck names, mapped through the service's
    bind mounts merged across compose files (`sh /app/web-install-if-stale.sh`
    is `scripts/web-install-if-stale.sh`; a path under a mount whose source
    needs interpolation is exit 2); and GATE CONFIGURATION by name shape at the
    top of the repo, apps/web and apps/api (package.json, pnpm-workspace.yaml,
    conftest.py, tsconfig*.json, *.config.*, *.setup.*, *.toml/.ini/.cfg,
    .prettier*, .eslintrc*).

WHAT THIS CANNOT PROTECT, and no in-repo change can: CI runs the merge base's
copy of this file, but the WORKFLOW that runs it is the PR's own
(`on: pull_request`), so a PR that edits that step, or this file, can make the
report say anything. Such a PR trips condition 5 through
`.github/workflows/**` and `check_*.py` only if a human reads the diff. Only
branch protection can close this; it is the owner's (#572).

RESIDUAL, stated because the verdict is only as wide as its sources and NO
other check covers it -- CLAUDE.md's derive-the-set grep reads workflows
only, which this already derives: a script reached from a sourced file or
another script; a path spelled through a `$VAR`; config deeper than the three
top levels, or referenced from a config file (eslint.config.js loads a local
rule); dependency changes (lockfiles) that change a tool's version; and any
gate input not matching these shapes. The list is open-ended on purpose. In `--old-root` mode nothing is
derived, and the output says so.

WHAT COUNTS AS AN EXECUTABLE CHANGE, per file type. Every rule leans toward
"executable" when unsure, because a false "not tripped" merges unattended and a
false "tripped" only asks the owner.

  * `.py`: the AST with docstrings removed, compared old against new. Comments
    are invisible to the AST, EXCEPT tool directives (`noqa`, `nosec`, `type:`,
    `pragma`, `fmt:`, `test-integrity:`, `pylint:`, `mypy:`, `ruff:`, `isort:`,
    `pyright:`, and an encoding cookie). A directive is compared WITH the code
    on its line, so moving a `# nosec` to another line is executable. A file
    that reads `__doc__` treats its docstrings as executable.
  * `.yml` / `.yaml`: the composed NODE tree -- tag and scalar text -- not the
    loaded object. `yaml.safe_load` is YAML 1.1 and `==` is Python's, so `on`
    -> `yes` (both True) and `1` -> `1.0` (equal numbers) would compare equal
    while compose and Actions, which parse YAML 1.2, see a different value.
  * `.json`: loaded with numbers kept as their source text and key order kept,
    so `true` is not `1` and `1` is not `1.0`.
  * shell (`.sh`, `.bash`, or a shell shebang): every line except full-line `#`
    comments and blank lines. If the file contains a heredoc (`<<`), every line
    counts, because a `#` line inside a heredoc is data, not a comment.
  * data and documents -- `.md`, `.txt`, `.csv`, `.toml`, `.ini`, `.cfg`,
    `.env` -- and ANY file under a `gates/` or `fixtures/` directory: every line
    counts. Fixtures are inputs to gates, and the PR template's text is what the
    gates parse.
  * added, deleted or renamed files: executable. The diff is read with
    `--no-renames`, so a moved file is a deletion of its old, listed path.
  * ANYTHING ELSE -- TypeScript/JavaScript, binaries, unknown types -- is
    unclassifiable: exit 2, which the merge rule reads as tripped.

`--report` is the CI form (audit-gate.yml): it prints the verdict on every PR
and exits 0 whether or not condition 5 trips, because tripping is a ROUTING
fact, not a defect in the PR. It still exits 2 when it could not look.

EXIT CODES (the gates' 0/1/2 convention): 0 no judged path changed executably;
1 condition 5 TRIPPED; 2 could not look -- no changed files, a list that is
missing, split, malformed or too short, a file that cannot be classified or
parsed, a missing root, a git failure, or an unknown argument. Exit 2 is never
clean.
"""

from __future__ import annotations

import ast
import fnmatch
import io
import json
import posixpath
import re
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path

MIN_PATHS = 10
_SECTION = re.compile(r"^### Condition 5: the paths\s*$", re.M)
_NEXT_HEADING = re.compile(r"^#{2,3} ", re.M)
_DIRECTIVE = re.compile(
    r"#\s*(noqa|nosec|type:|pragma|fmt:|test-integrity:|pylint:|mypy:|ruff:|isort:|pyright:|separator-class:)"
    r"|coding[:=]",
    re.I,
)
_DATA_SUFFIXES = {".md", ".txt", ".csv", ".toml", ".ini", ".cfg", ".env"}
_SHELL_SUFFIXES = {".sh", ".bash"}
_STRUCTURED = {".yml", ".yaml", ".json"}
_TOKEN = re.compile(r"[A-Za-z0-9_./-]+")
_DOTTED = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+$")


class CouldNotLook(Exception):
    """The gate could not establish the answer. Maps to exit 2, never 0 or 1."""


# --- the path list ---------------------------------------------------------------


def _is_list_line(line: str) -> bool:
    return line.startswith("    ") and bool(line.strip()) and not line.lstrip().startswith("-")


def paths_from_claude_md(text: str) -> list[str]:
    """The indented list directly under `### Condition 5: the paths`.

    NOT the backticked tokens of the prose, which name paths it EXCLUDES
    ("widening to `apps/web/**`", "not nothing under `alembic/`").
    `test_condition5_gate.py` pins that the list and the bullets agree in both
    directions.

    The list must be ONE unbroken run of single-token lines, ended by a blank
    line. A line inserted inside it (a `<!-- counted -->` marker, a note) used
    to end the read silently and drop every entry after it, with the floor of
    ten still satisfied. Now any interruption, a second run, or an entry with a
    space in it is exit 2.
    """
    m = _SECTION.search(text)
    if not m:
        raise CouldNotLook("no `### Condition 5: the paths` section in the CLAUDE.md given")
    rest = text[m.end() :]
    nxt = _NEXT_HEADING.search(rest)
    lines = (rest[: nxt.start()] if nxt else rest).splitlines()
    start = next((i for i, ln in enumerate(lines) if _is_list_line(ln)), None)
    if start is None:
        raise CouldNotLook("the condition-5 section has no indented path list")
    end = start
    while end < len(lines) and _is_list_line(lines[end]):
        end += 1
    found = [ln.strip() for ln in lines[start:end]]
    if end < len(lines) and lines[end].strip():
        raise CouldNotLook(
            f"the condition-5 list is interrupted after {found[-1]!r} by {lines[end].strip()!r}: "
            "every entry after it would be dropped"
        )
    following = next((ln for ln in lines[end:] if ln.strip()), None)
    if following is not None and _is_list_line(following):
        raise CouldNotLook(
            f"a second indented run follows the condition-5 list ({following.strip()!r}): "
            "the list was split by a blank line"
        )
    bad = [p for p in found if re.search(r"\s", p)]
    if bad:
        raise CouldNotLook(f"condition-5 list entries are not single paths: {bad}")
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


# --- the workflow-derived set --------------------------------------------------------


# GATE CONFIGURATION, by name shape, at the three levels a tool reads it from:
# the repo root, apps/web and apps/api. Trip-when-in-doubt rather than a list
# of the files someone thought of -- the first list missed vitest.setup.ts,
# apps/api/conftest.py (a collection hook there can deselect every test),
# ruff.toml, next.config.mjs and pnpm-workspace.yaml. Deeper config is a
# stated residual.
_CONFIG_DIRS = ("", "apps/web", "apps/api")
_CONFIG_NAME = re.compile(
    r"^(package\.json|pnpm-workspace\.yaml|conftest\.py|tsconfig[^/]*\.json"
    r"|[^/]*\.config\.[^/]+|[^/]*\.setup\.[^/]+|[^/]*\.(toml|ini|cfg)"
    r"|\.prettier[^/]*|\.eslintrc[^/]*|\.babelrc[^/]*|\.gitignore|\.dockerignore|Dockerfile[^/]*)$"
)


def gate_config(tracked: set[str]) -> set[str]:
    """Tracked config files at the top of the repo, apps/web and apps/api."""
    out = set()
    for f in tracked:
        head, _, name = f.rpartition("/")
        if head in _CONFIG_DIRS and _CONFIG_NAME.match(name):
            out.add(f)
    return out


def _script_candidates(token: str, wd: str, *, module: bool = False) -> list[str]:
    """Repo paths a token may name. A dotted name counts only after `-m` (module=True):
    compose's `uvicorn app.main:app` names product code, not a gate."""
    tok = token[2:] if token.startswith("./") else token
    if module and _DOTTED.match(tok) and not tok.endswith((".py", ".sh")):
        tok = tok.replace(".", "/") + ".py"
    if not tok.endswith((".py", ".sh")):
        return []
    out = []
    if wd:
        out.append(posixpath.normpath(posixpath.join(wd, tok)))
    if tok.startswith("/app/"):
        # The api container mounts apps/api at /app.
        out.append(posixpath.normpath("apps/api/" + tok[len("/app/") :]))
    elif not tok.startswith("/"):
        out.append(posixpath.normpath(tok))
        # `docker compose exec api python scripts/x.py` runs inside /app.
        out.append(posixpath.normpath("apps/api/" + tok))
    return out


def scripts_from_workflows(workflows: dict[str, str], tracked: set[str]) -> set[str]:
    """Every tracked `.py` / `.sh` a workflow `run:` names, plus the gate configuration it reads."""
    try:
        import yaml
    except ImportError as exc:
        raise CouldNotLook("PyYAML is not installed, so the workflows cannot be read") from exc
    found: set[str] = set()
    for name, src in workflows.items():
        try:
            doc = yaml.safe_load(src)
        except yaml.YAMLError as exc:
            raise CouldNotLook(f"{name} does not parse as YAML: {exc}") from exc
        jobs = (doc or {}).get("jobs") or {}
        for job in jobs.values():
            if not isinstance(job, dict):
                continue
            job_wd = (((job.get("defaults") or {}).get("run") or {}).get("working-directory")) or ""
            for step in job.get("steps") or []:
                run = step.get("run") if isinstance(step, dict) else None
                if not isinstance(run, str):
                    continue
                wd = step.get("working-directory") or job_wd
                tokens = _TOKEN.findall(run)
                for k, token in enumerate(tokens):
                    module = k > 0 and tokens[k - 1] == "-m"
                    for cand in _script_candidates(token, wd, module=module):
                        if cand in tracked:
                            found.add(cand)
                            break
    return found | gate_config(tracked)


UNRESOLVABLE = "?"
INTERPOLATED_TARGET = "$"  # a mount whose CONTAINER path compose must interpolate


def _compose_mounts(service: dict) -> list[tuple[str, str]]:
    """(container target, repo-relative host source) for each bind mount.

    A named volume is not a mount from the repo and is skipped. A host path
    outside the repo (absolute, `~`) is skipped. A source compose would have
    to interpolate (`${VAR}`) cannot be resolved here: it is kept with source
    UNRESOLVABLE, and a command path under its target is could-not-look,
    never a silent skip.
    """
    out = []
    for vol in service.get("volumes") or []:
        if isinstance(vol, str):
            parts = vol.split(":")
            if len(parts) < 2:
                continue
            # A `${VAR:-$HOME/x}` source contains colons of its own; the target
            # is the first part that starts with "/" after the source.
            k = next((i for i in range(1, len(parts)) if parts[i].startswith("/")), None)
            if k is None:
                if "$" in ":".join(parts[1:]):
                    out.append((INTERPOLATED_TARGET, UNRESOLVABLE))
                continue
            src, dst = ":".join(parts[:k]), parts[k]
            is_path = src.startswith((".", "/", "~", "$"))
        elif isinstance(vol, dict) and vol.get("type") == "bind":
            src, dst = str(vol.get("source", "")), str(vol.get("target", ""))
            is_path = True
            if "$" in dst:
                out.append((INTERPOLATED_TARGET, UNRESOLVABLE))
                continue
        else:
            continue
        if not is_path or not dst.startswith("/"):
            continue  # a named volume
        if "$" in src:
            out.append((dst.rstrip("/"), UNRESOLVABLE))
        elif src.startswith(("/", "~")):
            continue  # a host path outside the repo
        else:
            out.append((dst.rstrip("/"), posixpath.normpath(src)))
    return sorted(out, key=lambda m: -len(m[0]))


def scripts_from_compose(composes: dict[str, str], tracked: set[str]) -> set[str]:
    """Every tracked `.py` / `.sh` a compose command, entrypoint or healthcheck runs.

    #530's neighbour: `sh /app/web-install-if-stale.sh` is `scripts/...` on the
    host only through a bind mount, so the path is mapped through the mounts.
    """
    import yaml

    class ComposeLoader(yaml.SafeLoader):
        """Compose's own merge tags (`!reset`, `!override`) read as plain data."""

    def _plain(loader, suffix, node):
        if isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node)
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node)
        return loader.construct_scalar(node)

    ComposeLoader.add_multi_constructor("!", _plain)
    # Mounts are merged per SERVICE across every compose file: an override
    # file's command runs with the mounts the base file declares.
    services: dict[str, dict] = {}
    for name, src in composes.items():
        try:
            loaded = yaml.load(src, Loader=ComposeLoader)  # noqa: S506  # nosec B506
        except yaml.YAMLError as exc:
            raise CouldNotLook(f"{name} does not parse as YAML: {exc}") from exc
        for sname, service in ((loaded or {}).get("services") or {}).items():
            if isinstance(service, dict):
                entry = services.setdefault(sname, {"mounts": [], "words": []})
                entry["mounts"] += _compose_mounts(service)
                for key in ("command", "entrypoint"):
                    val = service.get(key)
                    entry["words"] += (
                        val if isinstance(val, list) else [val] if isinstance(val, str) else []
                    )
                test = (service.get("healthcheck") or {}).get("test")
                entry["words"] += (
                    test if isinstance(test, list) else [test] if isinstance(test, str) else []
                )
    found: set[str] = set()
    for sname, entry in services.items():
        mounts = sorted(set(entry["mounts"]), key=lambda m: -len(m[0]))
        for token in _TOKEN.findall(" ".join(str(w) for w in entry["words"])):
            for dst, host in mounts:
                if token == dst or token.startswith(dst + "/"):
                    if host == UNRESOLVABLE:
                        raise CouldNotLook(
                            f"compose service {sname!r} runs {token!r} from a mount whose "
                            f"source ({dst}) needs interpolation, so its repo path is unknown"
                        )
                    cand = posixpath.normpath(host + token[len(dst) :])
                    if cand in tracked and cand.endswith((".py", ".sh")):
                        found.add(cand)
                    break
            else:
                if token.startswith("/") and (INTERPOLATED_TARGET, UNRESOLVABLE) in mounts:
                    raise CouldNotLook(
                        f"compose service {sname!r} runs {token!r}, and has a mount whose "
                        "container path needs interpolation, so where that mount lands is unknown"
                    )
                for cand in _script_candidates(token, ""):
                    if cand in tracked:
                        found.add(cand)
                        break
    return found


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


def _directives(src: str) -> list[tuple[str, str]]:
    """Each directive comment WITH the code on its line: a directive applies to its line."""
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT and _DIRECTIVE.search(tok.string):
                out.append((tok.line[: tok.start[1]].strip(), tok.string.strip()))
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


def _yaml_nodes(src: str, name: str):
    import yaml

    def key(n):
        if isinstance(n, yaml.ScalarNode):
            return ("s", n.tag, n.value)
        if isinstance(n, yaml.SequenceNode):
            return ("q", n.tag, tuple(key(c) for c in n.value))
        if isinstance(n, yaml.MappingNode):
            return ("m", n.tag, tuple((key(k), key(v)) for k, v in n.value))
        raise CouldNotLook(f"{name}: unexpected YAML node {type(n).__name__}")

    try:
        return tuple(key(doc) for doc in yaml.compose_all(src))
    except yaml.YAMLError as exc:
        raise CouldNotLook(f"{name} does not parse as YAML: {exc}") from exc


def _json_exact(src: str, name: str):
    try:
        return json.loads(
            src,
            object_pairs_hook=lambda pairs: ("obj", tuple(pairs)),
            parse_int=lambda s: ("int", s),
            parse_float=lambda s: ("float", s),
            parse_constant=lambda s: ("const", s),
        )
    except ValueError as exc:
        raise CouldNotLook(f"{name} does not parse as JSON: {exc}") from exc


def structured_changed(old: str, new: str, name: str, suffix: str) -> bool:
    if suffix == ".json":
        return _json_exact(old, name) != _json_exact(new, name)
    try:
        import yaml  # noqa: F401  # lazy: only a YAML change needs it
    except ImportError as exc:
        raise CouldNotLook(
            f"{name}: PyYAML is not installed, so a YAML change cannot be classified"
        ) from exc
    return _yaml_nodes(old, name) != _yaml_nodes(new, name)


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


class Range:
    """A BASE..HEAD range, materialised: the changed files at the merge base and at the head."""

    def __init__(self, repo: Path, rng: str, tmp: Path) -> None:
        if ".." not in rng:
            raise CouldNotLook(f"--range must be BASE..HEAD, got {rng!r}")
        base, self.head = rng.split("..", 1)
        # The TOP LEVEL, whatever --repo names. CI runs from apps/api, and a
        # --repo pointing into the tree made `ls-tree` list cwd-relative paths:
        # no workflows, an empty derived set, exit 2 on every PR (measured).
        self.repo = Path(_git(repo, "rev-parse", "--show-toplevel").strip())
        self.merge_base = _git(repo, "merge-base", base, self.head).strip()
        # --no-renames: a rename would otherwise show only its NEW, possibly
        # unlisted, name and hide the listed path it moved away from.
        self.names = [
            ln
            for ln in _git(
                repo, "diff", "--no-renames", "--name-only", f"{base}...{self.head}"
            ).splitlines()
            if ln
        ]
        self.old_root, self.new_root = tmp / "old", tmp / "new"
        for rel in self.names:
            for root, ref in ((self.old_root, self.merge_base), (self.new_root, self.head)):
                proc = _run_git(repo, "show", f"{ref}:{rel}", text=False)
                if proc.returncode == 0:
                    dest = root / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(proc.stdout)

    def show(self, ref: str, rel: str) -> str:
        return _git(self.repo, "show", f"{ref}:{rel}")

    def workflow_scripts(self) -> set[str]:
        found: set[str] = set()
        for ref in (self.merge_base, self.head):
            tracked = set(
                _git(self.repo, "ls-tree", "-r", "--full-tree", "--name-only", ref).splitlines()
            )
            wfs = {
                p: self.show(ref, p)
                for p in tracked
                if p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))
            }
            if not wfs:
                raise CouldNotLook(f"no workflows at {ref}: the derived set would be empty")
            found |= scripts_from_workflows(wfs, tracked)
            composes = {
                p: self.show(ref, p)
                for p in tracked
                if "/" not in p and p.startswith("docker-compose") and p.endswith((".yml", ".yaml"))
            }
            found |= scripts_from_compose(composes, tracked)
        return found


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
    if "--range" in opts and "--claude-md" in opts:
        raise CouldNotLook(
            "--claude-md with --range: in range mode the list is read from git at the "
            "base AND the head, never from one checkout"
        )
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


def _judge(opts: dict, tmp: Path) -> tuple[list[str], list[str], list[str], str]:
    """(tripping, cleared, changed names, a line saying what was judged)."""
    report = bool(opts.get("--report"))
    if "--range" in opts:
        rng = Range(Path(opts.get("--repo", ".")), opts["--range"], tmp)
        pre: list[str] = []
        if "--paths-file" in opts:
            patterns = paths_from_file(Path(opts["--paths-file"]))
            source = f"{len(patterns)} pattern(s) from {opts['--paths-file']}"
        else:
            # The HEAD's list must read, or exit 2. The BASE's may not -- before
            # the list existed, its section's first indented block was a grep
            # command -- and an unreadable base list can only mean the list is
            # changing in this PR, which trips. Tripping routes to the human
            # exactly as exit 2 would, without turning the PR that repairs the
            # list red.
            at_head = paths_from_claude_md(rng.show(rng.head, "CLAUDE.md"))
            try:
                at_base = paths_from_claude_md(rng.show(rng.merge_base, "CLAUDE.md"))
            except CouldNotLook as exc:
                at_base = []
                pre.append(f"CLAUDE.md (no readable list at the base: {exc})")
            patterns = list(dict.fromkeys(at_base + at_head))
            if at_base and at_base != at_head:
                pre.append("CLAUDE.md (the condition-5 list itself changed)")
            source = f"{len(patterns)} listed pattern(s), base and head"
        derived = sorted(rng.workflow_scripts())
        patterns = patterns + derived
        source += (
            f", plus {len(derived)} derived (scripts workflows and compose run, and gate config)"
        )
        tripping, cleared = evaluate(patterns, rng.names, rng.old_root, rng.new_root, report=report)
        return pre + tripping, cleared, rng.names, source
    missing = [f for f in ("--old-root", "--new-root", "--changed-files") if f not in opts]
    if missing:
        raise CouldNotLook(
            f"need --range, or all of --old-root/--new-root/--changed-files (missing {missing})"
        )
    if "--paths-file" in opts:
        patterns = paths_from_file(Path(opts["--paths-file"]))
    else:
        cm = Path(opts.get("--claude-md", "CLAUDE.md"))
        try:
            patterns = paths_from_claude_md(cm.read_text(encoding="utf-8"))
        except OSError as exc:
            raise CouldNotLook(f"cannot read {cm}: {exc}") from exc
    old_root, new_root = Path(opts["--old-root"]), Path(opts["--new-root"])
    for r in (old_root, new_root):
        if not r.is_dir():
            raise CouldNotLook(f"{r} is not a directory")
    try:
        names = [
            ln.strip()
            for ln in Path(opts["--changed-files"]).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
    except OSError as exc:
        raise CouldNotLook(f"cannot read the changed-file list: {exc}") from exc
    if not names:
        raise CouldNotLook("no changed files: the diff did not resolve, which is not a clean diff")
    tripping, cleared = evaluate(patterns, names, old_root, new_root, report=report)
    return tripping, cleared, names, f"{len(patterns)} pattern(s); workflows NOT read in this mode"


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        opts = _parse(argv)
        with tempfile.TemporaryDirectory() as tmp:
            tripping, cleared, names, source = _judge(opts, Path(tmp))
        if not names:
            raise CouldNotLook(
                "no changed files: the diff did not resolve, which is not a clean diff"
            )
    except CouldNotLook as exc:
        print(f"check-condition5: could not look -- {exc}")
        print("  Read as TRIPPED: condition 5 comes back to the human.")
        return 2

    print(f"check-condition5: judged {source}.")
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
    print(
        "  Not derived, and covered by NO other check: scripts reached from sourced files "
        "or other scripts, paths spelled through a $VAR, config below the repo root, "
        "apps/web and apps/api or loaded by other config, lockfile changes, and any gate "
        "input not matching these shapes. And a PR editing this gate or "
        "the workflow step that runs it is NOT protected by this report (#572)."
    )
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
