#!/usr/bin/env python3
"""A gate's exit status must reach whoever reads the script's result (#213).

WHY THIS EXISTS. `set -e` has holes, and a green run can hide a red gate
behind them. Three recorded instances:

  * #143, the pre-push hook:
    `pytest -m unit 2>/dev/null || echo "skipped (api container not running)"`.
    A failing suite and a stopped container print the same line and both push.
  * #213 instance 1 (2026-09-24, twice): a gate at the head of an `&&` list,
    followed by more lines. bash exempts a command failing inside an `&&` list
    from `set -e`, so the red gate did not stop the `git commit` / `git push`
    that followed.
  * `python gate.py | head -1; echo $?`, from CLAUDE.md's opening table: a
    pipe without `pipefail` reports head's status, not the gate's.

WHAT IT FLAGS. A "gate command" is a check_* script, leave_row_oracle, pytest,
ruff, black, prettier --check, tsc, eslint, vitest, playwright test, bandit,
pip-audit, pnpm/npm audit, gitleaks, a `tests/gates/*.sh` script, or a
`pnpm ... lint|test|typecheck`.

  R1 pipe       the gate is not the LAST command of a pipeline, and pipefail is
                not on. Its status is lost. `set -o pipefail` (or `set -euo
                pipefail`) earlier in the same script turns pipefail on, and so
                does a workflow step whose `shell:` is `bash` (GitHub runs that
                as `bash -eo pipefail`).
  R2 swallow    the gate is followed by `||`, and the next element is not an
                exit, return, false, or a `$?` capture. `||` turns a failure into
                success.
  R3 mid-list   the gate is followed by `&&` in a statement that is not the
                script's last, with no later `|| exit` in the statement. Under
                `set -e` its failure does not stop the lines after it.

A statement that begins with `if`, `elif`, `while`, `until` or `!` is not
flagged under R2 or R3, because the condition consumes the status on purpose.
The gate recurses into `sh -c '...'` and `bash -c '...'` arguments and treats
each as a script of its own.

WHERE IT LOOKS. Every `run:` in `.github/workflows/*.yml` (parsed as YAML);
every `entry:` in `.pre-commit-config.yaml` (a `bash -c` / `sh -c` entry is
analysed as the script it runs); and every fenced ```bash / ```sh / ```shell
block in CLAUDE.md, plus every indented code block there that invokes a gate.

LIMITS, stated so a clean run is not read as more than it is. The parser is a
quote-aware pass plus `shlex`, not a shell. It flattens `{ ...; }` and
`( ... )` groups, skips heredoc bodies, and follows no functions, sourced
files, or variables holding commands. A gate invoked through a wrapper whose
name it does not know is unseen. So this is a floor, not a census. `mutation_sweep.py` is deliberately
NOT in the gate set: its workflow is schedule-only and report-only by design,
which #224 tracks.

EXIT CODES (the gates' 0/1/2 convention): 0 no finding; 1 at least one
finding; 2 could not look -- a workflow or the hook config that does not parse,
a script with unbalanced quotes, a missing root, no scripts found at all, or an
unknown argument.
"""

from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

_GATE = re.compile(
    r"(^|/|\.)(check_[a-z0-9_]+(\.py)?|leave_row_oracle(\.py)?)$"
    r"|^(pytest|ruff|black|tsc|eslint|vitest|bandit|pip-audit|gitleaks)$"
)
_CAPTURE = re.compile(r"^(exit|return|false)$|^[A-Za-z_][A-Za-z0-9_]*=\$\?$")
_CONDITIONAL = {"if", "elif", "while", "until", "!"}
_SEPARATORS = {";", "&", ";;", "(", ")", "{", "}", "then", "do", "else", "fi", "done"}
_FENCE = re.compile(r"^```(bash|sh|shell)\s*$")
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


class CouldNotLook(Exception):
    """The check could not establish the answer. Maps to exit 2."""


_EXEC_OPTS_WITH_VALUE = {"-e", "--env", "-w", "--workdir", "-u", "--user", "--index"}


def _through_docker_exec(w: list[str]) -> list[str] | None:
    """The command `docker compose exec [opts] SERVICE cmd...` / `docker exec` runs.

    The #143 hook runs pytest THROUGH `docker compose exec -T api`, so a gate
    test that looks only at the first word misses the one live instance.
    """
    if w[:3] == ["docker", "compose", "exec"]:
        rest = w[3:]
    elif w[:2] in (["docker-compose", "exec"], ["docker", "exec"]):
        rest = w[2:]
    else:
        return None
    i = 0
    while i < len(rest) and rest[i].startswith("-"):
        i += 2 if rest[i] in _EXEC_OPTS_WITH_VALUE else 1
    return rest[i + 1 :] if i < len(rest) else []


def is_gate(words: list[str]) -> bool:
    """Does this simple command run a gate?"""
    w = [x for x in words if not _ASSIGN.match(x)]  # drop VAR=x prefixes
    if not w:
        return False
    inner = _through_docker_exec(w)
    if inner is not None:
        return is_gate(inner)
    head = w[0]
    joined = " ".join(w)
    if head in ("python", "python3") or head.endswith("/python"):
        for tok in w[1:]:
            if tok.startswith("-"):
                continue
            return bool(_GATE.search(tok)) or tok == "pytest"
        return False
    if head in ("bash", "sh") and len(w) > 1 and re.search(r"(^|/)tests/gates/", w[1]):
        return True
    if _GATE.search(head):
        return True
    if head in ("npx", "pnpm", "npm"):
        if re.search(r"\bprettier\S*\b.*--check\b", joined):
            return True
        if re.search(r"\b(tsc|eslint|vitest|playwright test)\b", joined):
            return True
        if head in ("pnpm", "npm") and re.search(r"\b(audit|lint|test|typecheck)\b", joined):
            return True
    return False


def _strip_heredocs(script: str) -> str:
    out, lines, i = [], script.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", line)
        if m:
            end = m.group(1)
            i += 1
            while i < len(lines) and lines[i].strip() != end:
                i += 1
        i += 1
    return "\n".join(out)


def _flatten(script: str) -> str:
    """Strip comments, join continuations, and turn UNQUOTED newlines into `;`.

    Tokenizing line by line broke on a quoted string that spans lines (a
    `node -e "..."` block in ci.yml), so the script is scanned once with quote
    state, and shlex then reads it whole.
    """
    out: list[str] = []
    i, n = 0, len(script)
    single = double = False
    while i < n:
        c = script[i]
        if c == "\\" and not single and i + 1 < n:
            if script[i + 1] == "\n":
                out.append(" ")  # line continuation
            else:
                out.append(script[i : i + 2])
            i += 2
            continue
        if c == "'" and not double:
            single = not single
        elif c == '"' and not single:
            double = not double
        elif not single and not double:
            if c == "#" and (i == 0 or script[i - 1] in " \t\n;&|("):
                while i < n and script[i] != "\n":
                    i += 1
                continue
            if c == "\n":
                out.append(" ; ")
                i += 1
                continue
        out.append(c)
        i += 1
    if single or double:
        raise CouldNotLook("unbalanced quotes: cannot read the script")
    return "".join(out)


def statements(script: str) -> list[list[str]]:
    """The script as a flat list of statements, each a token list."""
    lex = shlex.shlex(_flatten(_strip_heredocs(script)), posix=True, punctuation_chars=";&|()")
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        toks = list(lex)
    except ValueError as exc:
        raise CouldNotLook(f"cannot tokenize: {exc}") from exc
    out: list[list[str]] = []
    cur: list[str] = []
    for tok in toks:
        if tok in _SEPARATORS:
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        out.append(cur)
    return out


def _elements(stmt: list[str]) -> list[tuple[list[list[str]], str | None]]:
    """[(pipeline commands, the operator after it)] for one statement."""
    elems: list[tuple[list[list[str]], str | None]] = []
    pipe: list[list[str]] = []
    cmd: list[str] = []
    for tok in stmt:
        if tok == "|":
            pipe.append(cmd)
            cmd = []
        elif tok in ("&&", "||"):
            pipe.append(cmd)
            elems.append((pipe, tok))
            pipe, cmd = [], []
        else:
            cmd.append(tok)
    pipe.append(cmd)
    elems.append((pipe, None))
    return elems


def _inner_scripts(cmd: list[str]) -> list[str]:
    """The argument of `sh -c` / `bash -lc` etc., analysed as a script of its own."""
    for i, w in enumerate(cmd[:-1]):
        if w in ("sh", "bash") or w.endswith("/sh") or w.endswith("/bash"):
            for j in range(i + 1, len(cmd) - 1):
                if re.fullmatch(r"-[a-z]*c[a-z]*", cmd[j]):
                    return [cmd[j + 1]]
    return []


def _turns_on_pipefail(stmt: list[str]) -> bool:
    return bool(stmt) and stmt[0] == "set" and "pipefail" in stmt


def analyse(script: str, where: str, *, pipefail: bool = False) -> list[str]:
    findings: list[str] = []
    stmts = statements(script)
    for idx, stmt in enumerate(stmts):
        if _turns_on_pipefail(stmt):
            pipefail = True
        elems = _elements(stmt)
        conditional = stmt[0] in _CONDITIONAL
        last_stmt = idx == len(stmts) - 1
        ops = [op for _, op in elems]
        for e_i, (pipe, op) in enumerate(elems):
            for cmd in pipe:
                for inner in _inner_scripts(cmd):
                    findings += analyse(inner, f"{where} (inside `{cmd[0]} -c`)")
            gate_at = [k for k, cmd in enumerate(pipe) if is_gate(cmd)]
            if not gate_at:
                continue
            gate_txt = " ".join(pipe[gate_at[0]])[:70]
            if any(k < len(pipe) - 1 for k in gate_at) and not pipefail:
                findings.append(
                    f"{where}: R1 pipe -- `{gate_txt}` is piped without pipefail, so its status is lost"
                )
            if conditional or (len(pipe) - 1) not in gate_at:
                continue  # the pipeline's status is not the gate's anyway (R1 covers it)
            # Rescued if a later `||` leads to exit/return/false/$?-capture.
            rescued = any(
                ops[k] == "||" and elems[k + 1][0][0] and _CAPTURE.match(elems[k + 1][0][0][0])
                for k in range(e_i, len(elems) - 1)
            )
            if op == "||" and not rescued:
                findings.append(
                    f"{where}: R2 swallow -- `{gate_txt} || ...` turns the gate's failure into success"
                )
            elif op == "&&" and not last_stmt and not rescued:
                findings.append(
                    f"{where}: R3 mid-list -- `{gate_txt} && ...` is followed by more statements; "
                    "under set -e its failure does not stop them"
                )
    return findings


# --- sources ------------------------------------------------------------------------


def _step_shell(job: dict, step: dict, doc: dict) -> str | None:
    scopes = (
        step,
        job,
        (job.get("defaults") or {}).get("run") or {},
        (doc.get("defaults") or {}).get("run") or {},
    )
    for scope in scopes:
        if isinstance(scope, dict) and scope.get("shell"):
            return str(scope["shell"])
    return None


def workflow_scripts(root: Path) -> list[tuple[str, str, bool]]:
    import yaml

    wfs = sorted((root / ".github" / "workflows").glob("*.y*ml"))
    if not wfs:
        raise CouldNotLook(f"no workflows under {root / '.github' / 'workflows'}")
    out = []
    for wf in wfs:
        try:
            doc = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise CouldNotLook(f"{wf} does not parse: {exc}") from exc
        for jname, job in (doc.get("jobs") or {}).items():
            for s_i, step in enumerate(job.get("steps") or []):
                run = step.get("run")
                if run:
                    name = step.get("name") or f"step {s_i + 1}"
                    shell = _step_shell(job, step, doc)
                    out.append((str(run), f"{wf.name} / {jname} / {name}", shell == "bash"))
    return out


def hook_scripts(root: Path) -> list[tuple[str, str, bool]]:
    import yaml

    cfg = root / ".pre-commit-config.yaml"
    if not cfg.exists():
        return []
    try:
        doc = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CouldNotLook(f"{cfg} does not parse: {exc}") from exc
    out = []
    for repo in doc.get("repos") or []:
        for hook in repo.get("hooks") or []:
            entry = hook.get("entry")
            if entry:
                out.append((str(entry), f".pre-commit-config.yaml / {hook.get('id')}", False))
    return out


def _block_has_gate(block: str) -> bool:
    try:
        return any(is_gate(c) for s in statements(block) for pipe, _ in _elements(s) for c in pipe)
    except CouldNotLook:
        return False  # prose in an indented block, not shell


def claude_md_scripts(root: Path) -> list[tuple[str, str, bool]]:
    md = root / "CLAUDE.md"
    if not md.exists():
        return []
    lines = md.read_text(encoding="utf-8").splitlines()
    out: list[tuple[str, str, bool]] = []
    i = 0
    while i < len(lines):
        if _FENCE.match(lines[i]):
            start = j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append(("\n".join(lines[start:j]), f"CLAUDE.md:{start}", False))
            i = j + 1
            continue
        if lines[i].startswith("    ") and (i == 0 or not lines[i - 1].strip()):
            j = i
            while j < len(lines) and (lines[j].startswith("    ") or not lines[j].strip()):
                j += 1
            block = "\n".join(ln[4:] for ln in lines[i:j])
            if _block_has_gate(block):
                out.append((block, f"CLAUDE.md:{i + 1}", False))
            i = j
            continue
        i += 1
    return out


def _parse(argv: list[str]) -> Path:
    root = Path(".")
    args = list(argv[1:])
    while args:
        flag = args.pop(0)
        if flag == "--root" and args:
            root = Path(args.pop(0))
        else:
            raise CouldNotLook(f"unknown or incomplete argument: {flag!r}")
    return root


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        root = _parse(argv)
        if not root.is_dir():
            raise CouldNotLook(f"{root} is not a directory")
        scripts = workflow_scripts(root) + hook_scripts(root) + claude_md_scripts(root)
        if not scripts:
            raise CouldNotLook("found no scripts to read; an empty scan is not a clean one")
        findings: list[str] = []
        for script, where, pipefail in scripts:
            try:
                findings += analyse(script, where, pipefail=pipefail)
            except CouldNotLook as exc:
                raise CouldNotLook(f"{where}: {exc}") from exc
    except CouldNotLook as exc:
        print(f"check-shell-status: could not look -- {exc}")
        return 2
    if findings:
        print(
            f"check-shell-status: {len(findings)} finding(s) -- a gate's status "
            "does not reach the result:"
        )
        for f in findings:
            print(f"  {f}")
        return 1
    print(
        f"check-shell-status: clean -- {len(scripts)} script(s) read; "
        "every gate's status reaches the result."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-shell-status: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation.{nl}")
        raise SystemExit(2) from exc
