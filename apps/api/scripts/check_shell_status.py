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

WHAT IT IS, AND WHAT IT IS NOT. A LINE-LEVEL HEURISTIC, NOT A SHELL PARSER --
a quote-aware scan plus `shlex`. Its clean result means "none of the four
shapes below was found in the scripts listed", never "every gate's status
reaches the result". A real parser (bashlex, tree-sitter-bash) was weighed and
not taken: it is a new dependency for one gate, and neither models `set -e`
semantics either. The shapes it does not model are listed under LIMITS and
filed.

A "gate command" is a check_* script, leave_row_oracle, pytest, ruff, black,
prettier --check, tsc, eslint, vitest, playwright test, bandit, pip-audit,
pnpm/npm audit, gitleaks, a `tests/gates/*.sh` script, a `pnpm ...
lint|test|typecheck|format:check`, or a GROUP / `sh -c` wrapper containing one.
Leading `VAR=x`, `env`, `time`, `timeout N`, `command`, `exec`, `nice`, `xargs`
and `docker compose exec|run [opts] SERVICE` are looked through.

  R1 pipe       the gate is not the LAST command of a pipeline, and pipefail is
                not on (`set -o pipefail`, `set -euo pipefail`, or a workflow
                step whose `shell:` is `bash`). `set +o pipefail` turns it off.
  R2 swallow    the gate is followed by `||`, and what runs when it fails is
                not on a deliberately NARROW whitelist (four review rounds each
                found a hole in a more permissive model). What runs is the
                element after the FIRST `||` following the gate (`&&` in
                between short-circuits to it), and it must be the statement's
                last element: `gate || exit 0 || exit 1` exits 0. Allowed:
                  - exactly `exit N` / `return N`, N a literal, N % 256 != 0;
                  - exactly `exit $?` / `return $?`;
                  - `false`, only while errexit is on;
                  - exactly `{ echo/printf ...; exit N; }`: echo or printf
                    statements, then one exit, last, at top level, with no
                    if/then/&&/||/nested group/$( inside;
                  - `var=$?` whose NEXT statement is exactly `exit $var`,
                    `return $var`, `[ "$var" -ne 0 ] && exit "$var"` or
                    `[ "$var" -eq 0 ] || exit "$var"`.
                Any other right side is a finding. A false positive costs rewriting
                a script into one of these shapes; a false negative costs the
                next #143. A statement `! gate` is R2 as well: `!` inverts the
                status and `set -e` ignores it.
  R3 mid-list   the gate is followed by `&&` in a statement that is not the
                script's last, with no later rescue. Under `set -e` its failure
                does not stop the lines after it.
  R4 no errexit the script is not under `set -e` and a gate is not its last
                statement, and the next statement does not propagate its status
                in a whitelisted shape (`exit $?`, or a whitelisted capture). Its
                status is overwritten by whatever runs next. Applied to scripts
                that run unattended: workflow steps (after a `set +e`, or under
                a custom `shell:` without -e), `sh -c` / `bash -c` bodies,
                pre-commit entries and `.sh` files (a shebang's `-e` counts).
                NOT to CLAUDE.md's blocks, which a person runs line by line.

A `{ ...; }` group's last statement is NOT terminal unless the group is: bash
does not exit when a brace group fails because of a command that failed while
`-e` was ignored, so `{ pytest && echo ok; }` then `git push` pushes. A
`( ... )` subshell's failure does exit, so its body's end is terminal.

A gate as an `if` condition (rounds 5 and 6): only the plain `if gate` /
`if ! gate` shape is modelled. The branch that runs when the gate FAILS (the
else-branch of `if gate`, the then-branch of `if ! gate`) must be EXACTLY one
of:
  - zero or more simple `echo` / `printf` statements, then a literal failing
    `exit N` / `return N` (N % 256 != 0), last -- the SAME closed grammar as
    R2's `{ echo...; exit N; }` rescue, from one function;
  - `exit $?` / `return $?` as the SOLE statement of the else-branch of
    `if gate`. Never after another statement (`$?` is then that statement's),
    and never under `if !` (`$?` is then the negation's, 0).
Any nested compound in the failure branch (if, while, until, for, case, a
subshell, a group), no such branch, an `elif` chain, or a gate inside a
compound condition (`&&`, `||`, a pipe) is an R2 finding. `while` / `until`
conditions are NOT modelled.
A `var=$?` capture counts only when nothing but `;` or a newline separates it
from the gate: read across `else`, `fi`, `done` or `;;` it is refused.

WHERE IT LOOKS. Every `run:` in `.github/workflows/*.yml` (under `bash -e`,
which is what GitHub runs); every `entry:` in `.pre-commit-config.yaml`; every
tracked-looking `*.sh` file outside `node_modules`; and every fenced
```bash / ```sh / ```shell block in CLAUDE.md, plus every indented block there
that invokes a gate.

LIMITS, and each is a way a clean run can be wrong: functions, sourced files
and variables holding commands are not followed; a loop's earlier iterations
are not modelled (only the body's own statements); a gate ending an if/case
branch is taken to reach the compound's status, so code after the compound is
not checked; `"$( ... )"` inside double quotes is read as one word, so a gate
there is unseen; `then`, `do`, `fi`, `done` and `else` split a statement
wherever they appear as words, not only in keyword position; `docker run IMAGE cmd` is
not looked through; a wrapper not named above hides the gate; `set -e` inside
a function or subshell is not scoped; an unquoted `$(gate)` inside `echo`,
`export` or `local` (the builtin's 0 replaces the gate's status); a
backgrounded gate (`gate &`, and a bare `wait` returns 0); heredoc bodies fed
to a shell (`bash <<EOF`), which are not scanned; `trap ... EXIT`, which can
rewrite the final status; and `while` / `until` conditions (#586). Missing
inputs are also asymmetric: no workflows directory is could-not-look, while a
missing `.pre-commit-config.yaml` or an empty `.sh` set is silently nothing,
`package.json` scripts are not scanned, and a `pwsh` / `python` step is read as
if it were a POSIX shell script (#587).
So this is a floor, not a census.
`mutation_sweep.py` is deliberately NOT in the gate set: its workflow is
report-only by design (#224).

EXIT CODES (the gates' 0/1/2 convention): 0 no finding; 1 at least one
finding; 2 could not look -- a workflow or hook config that does not parse, a
script with unbalanced quotes, groups or an unterminated heredoc, an indented
CLAUDE.md block that names a gate but does not parse, a missing CLAUDE.md, a
missing root, no workflows, or an unknown argument.
"""

from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

_GATE = re.compile(
    r"(^|/|\.)(check_[a-z0-9_]+(\.py)?|leave_row_oracle(\.py)?)$"
    r"|(^|/)(pytest|ruff|black|tsc|eslint|vitest|bandit|pip-audit|gitleaks)$"
)
_PYTHON = re.compile(r"(^|/)python(\d+(\.\d+)?)?$")
_CONDITIONAL = {"if", "elif", "while", "until"}
_SEPARATORS = {";", "&", ";;", "then", "do", "else", "fi", "done"}
_FENCE = re.compile(r"^```(bash|sh|shell)\s*$")
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_GROUP = "__GROUP__:"
_OPEN = {"(": ")", "{": "}"}
_BRACE = "__BRACE__:"


class CouldNotLook(Exception):
    """The check could not establish the answer. Maps to exit 2."""


# --- what is a gate ------------------------------------------------------------------

_EXEC_OPTS_WITH_VALUE = {"-e", "--env", "-w", "--workdir", "-u", "--user", "--index", "--name"}


def _through_docker(w: list[str]) -> list[str] | None:
    """The command `docker compose exec|run [opts] SERVICE cmd...` / `docker exec` runs."""
    if w[:3] in (["docker", "compose", "exec"], ["docker", "compose", "run"]):
        rest = w[3:]
    elif w[:2] in (["docker-compose", "exec"], ["docker-compose", "run"], ["docker", "exec"]):
        rest = w[2:]
    else:
        return None
    i = 0
    while i < len(rest) and rest[i].startswith("-"):
        i += 2 if rest[i] in _EXEC_OPTS_WITH_VALUE else 1
    return rest[i + 1 :] if i < len(rest) else []


def _strip_wrappers(w: list[str]) -> list[str]:
    """Drop `VAR=x`, `env`, `time`, `timeout N`, `command`, `exec`, `nice`, `xargs` prefixes."""
    while w:
        head = w[0]
        if _ASSIGN.match(head):
            w = w[1:]
        elif head in ("env", "command", "exec", "time", "nice", "xargs"):
            w = w[1:]
            while w and (w[0].startswith("-") or _ASSIGN.match(w[0])):
                w = w[1:]
        elif head == "timeout":
            w = w[1:]
            while w and w[0].startswith("-"):
                w = w[1:]
            w = w[1:]  # the duration
        else:
            break
    return w


def _group_body(tok: str) -> str | None:
    for prefix in (_GROUP, _BRACE):
        if tok.startswith(prefix):
            return tok[len(prefix) :]
    return None


def is_gate(words: list[str]) -> bool:
    """Does this simple command, group or wrapper run a gate?"""
    for tok in words:
        body = _group_body(tok)
        if body is not None and _script_has_gate(body):
            return True
    w = _strip_wrappers([x for x in words if _group_body(x) is None])
    if not w:
        return False
    inner = _through_docker(w)
    if inner is not None:
        return is_gate(inner)
    if any(_script_has_gate(s) for s in _inner_scripts(w)):
        return True
    head = w[0]
    joined = " ".join(w)
    if _PYTHON.search(head):
        args = w[1:]
        while args and args[0].startswith("-") and args[0] != "-m":
            args = args[2:] if args[0] in ("-X", "-W") else args[1:]
        if args and args[0] == "-m":
            args = args[1:]
        return bool(args) and (bool(_GATE.search(args[0])) or args[0] == "pytest")
    if head in ("bash", "sh") and len(w) > 1 and re.search(r"(^|/)tests/gates/", w[1]):
        return True
    if _GATE.search(head):
        return True
    if head in ("npx", "pnpm", "npm"):
        if re.search(r"\bprettier\S*\b.*--check\b", joined):
            return True
        if re.search(r"\b(tsc|eslint|vitest|playwright test)\b", joined):
            return True
        if head in ("pnpm", "npm") and re.search(
            r"\b(audit|lint|test|typecheck)\b|format:check", joined
        ):
            return True
    return False


def _script_has_gate(script: str) -> bool:
    return any(is_gate(c) for s in statements(script) for pipe, _ in _elements(s) for c in pipe)


# --- reading a script ------------------------------------------------------------------


def _heredoc_delim(script: str, i: int) -> tuple[str, bool, int] | None:
    """At an unquoted `<<`: (delimiter, strip-tabs, index after it), or None for `<<<`."""
    j = i + 2
    if j < len(script) and script[j] == "<":
        return None  # here-string
    strip = j < len(script) and script[j] == "-"
    j += strip
    while j < len(script) and script[j] in " \t":
        j += 1
    m = re.match(r"""(['"]?)\\?([A-Za-z_][A-Za-z0-9_]*)\1""", script[j:])
    if not m:
        return None  # `1 << SHIFT` inside arithmetic, or not a heredoc
    return m.group(2), strip, j + m.end()


def _flatten(script: str) -> str:
    """Strip comments and heredoc bodies, join continuations, normalise redirections,
    and turn UNQUOTED newlines into `;` -- in one quote-aware pass.

    Comments are stripped BEFORE a `<<` is read as a heredoc, so a comment
    quoting `python - <<'PY'` does not swallow the rest of the script, and an
    unterminated heredoc is could-not-look, never the end of the script.
    """
    out: list[str] = []
    i, n = 0, len(script)
    single = double = False
    pending: list[tuple[str, bool]] = []
    # `"$( ... )"`: a command substitution opens a NEW quoting context inside
    # double quotes. Each frame saves the enclosing double-quote state and
    # counts parens, so a heredoc or a quote inside the substitution is read
    # as the shell reads it.
    frames: list[list] = []
    while i < n:
        c = script[i]
        if not single and script.startswith("$(", i):
            out.append("$(")
            frames.append([double, 0, len(out)])
            double = False
            i += 2
            continue
        if frames and not single and not double and c in "()":
            if c == "(":
                frames[-1][1] += 1
            elif frames[-1][1] == 0:
                saved, _, start = frames.pop()
                if saved:
                    # Opened inside double quotes: emit nothing between the
                    # parens, so shlex reads one word rather than re-reading
                    # the substitution's own quotes against the outer ones.
                    del out[start:]
                double = saved
            else:
                frames[-1][1] -= 1
        if c == "\\" and not single and i + 1 < n:
            out.append(" " if script[i + 1] == "\n" else script[i : i + 2])
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
            if script.startswith("<<", i):
                hd = _heredoc_delim(script, i)
                if hd is not None:
                    pending.append((hd[0], hd[1]))
                    out.append(" HEREDOC ")
                    i = hd[2]
                    continue
            if script.startswith(">&", i) or script.startswith("<&", i):
                out.append(c + "FD")  # `2>&1` must not read as a background `&`
                i += 2
                continue
            if script.startswith("&>", i):
                out.append("ALLOUT>")
                i += 2
                continue
            if script.startswith("|&", i):
                out.append("|")
                i += 2
                continue
            if c == "\n":
                # `pytest ||` then `exit 1` on the next line is ONE list.
                tail = "".join(out[-4:]).rstrip()
                out.append(" " if tail.endswith(("&&", "||", "|")) else " ; ")
                i += 1
                for delim, strip in pending:
                    while True:
                        if i >= n:
                            raise CouldNotLook(f"heredoc `{delim}` is never terminated")
                        end = script.find("\n", i)
                        line = script[i : n if end == -1 else end]
                        i = n if end == -1 else end + 1
                        if (line.lstrip("\t") if strip else line) == delim:
                            break
                pending = []
                continue
        out.append(c)
        i += 1
    if single or double or frames:
        raise CouldNotLook("unbalanced quotes: cannot read the script")
    if pending:
        raise CouldNotLook(f"heredoc `{pending[0][0]}` is never terminated")
    return "".join(out)


def statements(script: str) -> list[list[str]]:
    return [s for s, _ in statements_with_ends(script)]


def statements_with_ends(script: str) -> list[tuple[list[str], list[str]]]:
    """The script as a flat list of (statement, EVERY separator after it).

    Every one, not the last: in `x; fi; fi` the trailing `;` would otherwise
    overwrite the `fi`s, and an if's branches could not be found.

    A `( ... )`, `{ ...; }` or `$( ... )` group becomes ONE token carrying its
    body, so the rules see `(cd x && gate) && git push` as a gate-bearing
    element followed by `&&` -- not as two statements with the gate last in the
    first.
    """
    lex = shlex.shlex(_flatten(script), posix=True, punctuation_chars=";&|()")
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        toks = [piece for tok in lex for piece in _split_punct(tok)]
    except ValueError as exc:
        raise CouldNotLook(f"cannot tokenize: {exc}") from exc
    out: list[list[str]] = []
    ends: list[list[str]] = []
    cur: list[str] = []
    stack: list[tuple[str, list[str]]] = []
    for tok in toks:
        if tok in _OPEN:
            stack.append((tok, []))
            continue
        if stack:
            opener, body = stack[-1]
            if tok == _OPEN[opener]:
                stack.pop()
                prefix = _BRACE if opener == "{" else _GROUP
                token = prefix + " ".join(shlex.quote(t) if t not in _PUNCT else t for t in body)
                (stack[-1][1] if stack else cur).append(token)
            else:
                body.append(tok)
            continue
        if tok == ")" or tok in _SEPARATORS:  # `)` alone: a `case` pattern's close
            if cur:
                out.append(cur)
                ends.append([])
            if out:
                ends[-1].append(tok)
            cur = []
        else:
            cur.append(tok)
    if stack:
        raise CouldNotLook(f"unbalanced `{stack[-1][0]}`: cannot read the script")
    if cur:
        out.append(cur)
        ends.append([])
    return list(zip(out, ends, strict=True))


_PUNCT = {";", "&", "&&", "|", "||", ";;", "(", ")"}
_OPERATOR = re.compile(r"&&|\|\||;;|[;&|()]")


def _split_punct(tok: str) -> list[str]:
    """shlex returns a run of punctuation as ONE token (`);`, `)|`); split it into operators."""
    if tok and all(ch in ";&|()" for ch in tok):
        return _OPERATOR.findall(tok)
    return [tok]


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
    """The argument of `sh -c` / `bash -lc` etc."""
    for i, w in enumerate(cmd[:-1]):
        if w in ("sh", "bash") or w.endswith("/sh") or w.endswith("/bash"):
            for j in range(i + 1, len(cmd) - 1):
                if re.fullmatch(r"-[a-z]*c[a-z]*", cmd[j]):
                    return [cmd[j + 1]]
    return []


def _set_flags(stmt: list[str]) -> dict[str, bool]:
    """What a `set` statement turns on (True) or off (False): errexit, pipefail."""
    if not stmt or stmt[0] != "set":
        return {}
    out: dict[str, bool] = {}
    args = stmt[1:]
    for k, a in enumerate(args):
        if a[:1] not in "-+" or len(a) < 2:
            continue
        on = a[0] == "-"
        if "e" in a[1:] and not a.startswith(("--", "++")):
            out["errexit"] = on
        if "o" in a[1:] and k + 1 < len(args):
            if args[k + 1] == "pipefail":
                out["pipefail"] = on
            elif args[k + 1] == "errexit":
                out["errexit"] = on
    return out


# A WHITELIST, DELIBERATELY NARROW. Four review rounds each found a new way a
# "rescue" model let a red gate through: `|| exit 0`; `|| { echo x; exit; }`;
# a capture nobody read; an `exit 0` hidden behind `docker ps ||` or an `if`
# inside a group; `exit 256`. Each fix modelled a little more of the shell and
# opened the next hole. So nothing is modelled any more: a rescue is one of the
# exact shapes below, and anything else is a finding. A false positive costs
# rewriting a script into one of these shapes; a false negative costs the next
# #143. If a real script fails this, rewrite the script -- do not widen this.
_ASSIGN_STATUS = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=\$\?$")
_ECHOES = {"echo", "printf"}
_GROUP_FORBIDDEN = {"if", "then", "||", "&&", "{", "(", "exit", "return"}


def _literal_failure(words: list[str]) -> bool:
    """`exit N` / `return N`: exactly two words, N a literal the SHELL sees as non-zero."""
    return (
        len(words) == 2
        and words[0] in ("exit", "return")
        and bool(re.fullmatch(r"[0-9]+", words[1]))
        and int(words[1]) % 256 != 0
    )


def _is_status_exit(words: list[str]) -> bool:
    """`exit $?` / `return $?`: exactly those two words."""
    return len(words) == 2 and words[0] in ("exit", "return") and words[1] == "$?"


def _echoes_then_failure(stmts: list[list[str]]) -> bool:
    """The ONE closed grammar for "report, then fail": zero or more simple
    echo/printf statements, then a literal failing `exit N` / `return N`, last.

    Shared by the `{ ...; }` rescue and the `if` failure branch, so the two
    cannot drift apart. A statement that is not a simple echo/printf -- any
    nested compound (if, while, until, for, case, a subshell, a group) or a
    command substitution -- fails it.
    """
    if not stmts or not _literal_failure(stmts[-1]):
        return False
    for s in stmts[:-1]:
        if not s or s[0] not in _ECHOES:
            return False
        for tok in s:
            if tok in _GROUP_FORBIDDEN or "$(" in tok or _group_body(tok) is not None:
                return False
    return True


def _group_is_whitelisted(body: str) -> bool:
    """Exactly `{ <echo/printf statements>; exit N; }`: one exit, at top level, last."""
    return _echoes_then_failure(statements(body))


def _capture_is_whitelisted(var: str, nxt: list[str]) -> bool:
    """The NEXT statement propagates the captured status, in exactly one of these shapes."""
    ref = ("$" + var, "${" + var + "}")
    if len(nxt) == 2 and nxt[0] in ("exit", "return") and nxt[1] in ref:
        return True
    # `[ "$var" -ne 0 ] && exit "$var"` or `[ "$var" -eq 0 ] || exit "$var"`
    return (
        len(nxt) == 8
        and nxt[0] == "["
        and nxt[1] in ref
        and (nxt[2], nxt[5]) in (("-ne", "&&"), ("-eq", "||"))
        and nxt[3] == "0"
        and nxt[4] == "]"
        and nxt[6] == "exit"
        and nxt[7] in ref
    )


def _failure_branch(pairs: list, idx: int, negated: bool):
    """The statements that run when the gate in the `if` at pairs[idx] FAILS.

    `if ! gate; then ...` fails into the then-branch; `if gate; then ...; else
    ...; fi` into the else-branch, which is None when there is none. Returns
    "unmodelled" for an `elif` chain or an `if` with no closing `fi`.
    """
    then: list = []
    els = None
    cur = then
    depth = 0
    for s, seps in pairs[idx + 1 :]:
        if s and s[0] == "if":
            depth += 1
        if s and s[0] == "elif" and depth == 0:
            return "unmodelled"
        cur.append(s)
        for sep in seps:
            if sep == "fi":
                if depth == 0:
                    return then if negated else els
                depth -= 1
            elif sep == "else" and depth == 0:
                els = []
                cur = els
    return "unmodelled"


def _if_failure_kept(pairs: list, idx: int, negated: bool) -> bool:
    """Is the failure branch EXACTLY the `{ echo...; exit N; }` grammar?

    Zero or more simple echo/printf statements, then a literal failing
    `exit N` / `return N` (`_echoes_then_failure`), or `exit $?` / `return $?`
    as the SOLE statement of the else-branch of `if gate`. Anything after
    another statement reads that statement's `$?` (`echo ...; exit $?` exits
    echo's 0); in the then-branch of `if ! gate`, `$?` is the NEGATION's
    status, 0 when the gate failed (measured, recorded in audit-gate.yml).
    """
    branch = _failure_branch(pairs, idx, negated)
    if not isinstance(branch, list) or not branch:
        return False
    if not negated and len(branch) == 1 and _is_status_exit(branch[0]):
        return True
    return _echoes_then_failure(branch)


def _rescue(element: list[list[str]], nxt: list[str], errexit: bool) -> bool:
    """Is the right side of `||` -- EXACTLY one command -- a whitelisted rescue?"""
    if len(element) != 1:
        return False  # a pipeline on the right of `||` is not a whitelisted shape
    words = element[0]
    if not words:
        return False
    body = _group_body(words[0])
    if body is not None:
        return len(words) == 1 and words[0].startswith(_BRACE) and _group_is_whitelisted(body)
    if _literal_failure(words) or _is_status_exit(words):
        return True
    if words == ["false"]:
        return errexit  # `|| false` keeps the failure only if something exits on it
    m = _ASSIGN_STATUS.match(words[0])
    return bool(m) and len(words) == 1 and _capture_is_whitelisted(m.group(1), nxt)


def analyse(
    script: str,
    where: str,
    *,
    pipefail: bool = False,
    errexit: bool = True,
    unattended: bool = False,
    tail_terminal: bool = True,
) -> list[str]:
    findings: list[str] = []
    pairs = statements_with_ends(script)
    stmts = [s for s, _ in pairs]
    for idx, stmt in enumerate(stmts):
        # TERMINAL: the script's last statement, or the last of an if/case/loop
        # branch. A branch's last status is the compound's status; code AFTER the
        # compound is not modelled, which is a stated limit.
        nxt = stmts[idx + 1][0] if idx + 1 < len(stmts) else None
        terminal = (
            (idx == len(stmts) - 1 and tail_terminal)
            or any(sep in ("else", "fi", ";;", "done") for sep in pairs[idx][1])
            or nxt in ("elif", "esac")
        )
        flags = _set_flags(stmt)
        pipefail = flags.get("pipefail", pipefail)
        errexit = flags.get("errexit", errexit)
        negated = stmt[0] == "!"
        body_stmt = stmt[1:] if negated else stmt
        elems = _elements(body_stmt)
        conditional = stmt[0] in _CONDITIONAL
        if stmt[0] == "if":
            # A gate used as an `if` condition: its failure branch must end in a
            # whitelisted exit, or the failure is swallowed. Only the plain
            # `if [!] gate` shape is modelled; a gate inside a compound condition
            # (&&, ||, a pipe) is a finding, by the same whitelist rule.
            cond = stmt[1:]
            cond_negated = bool(cond) and cond[0] == "!"
            if cond_negated:
                cond = cond[1:]
            cond_elems = _elements(cond)
            if any(is_gate(c) for pipe, _ in cond_elems for c in pipe):
                simple = len(cond_elems) == 1 and len(cond_elems[0][0]) == 1
                if not simple or not _if_failure_kept(pairs, idx, cond_negated):
                    shape = (
                        "if ! gate; then ...; exit N; fi"
                        if cond_negated
                        else "if gate; then ...; else ...; exit N; fi"
                    )
                    findings.append(
                        f"{where}: R2 swallow -- `{' '.join(stmt)[:70]}`: the branch that runs when the "
                        f"gate fails does not end in a whitelisted exit (write `{shape}`)"
                    )
        last_stmt = terminal
        nxt_stmt = stmts[idx + 1] if idx + 1 < len(stmts) else []
        # The next statement propagates the status, in a WHITELISTED shape only:
        # `exit $?` / `return $?`, or `var=$?` followed by a whitelisted
        # propagation of `$var`. A printed or merely tested `$?` is not kept.
        after = stmts[idx + 2] if idx + 2 < len(stmts) else []
        # The flat token list reads `gate` then `fi` then `rc=$?` as adjacent; a
        # capture counts only when nothing but `;` / a newline separates them.
        seps_plain = all(sep == ";" for sep in pairs[idx][1])
        captured = (
            seps_plain
            and bool(nxt_stmt)
            and (
                _is_status_exit(nxt_stmt)
                or (
                    len(nxt_stmt) == 1
                    and bool(_ASSIGN_STATUS.match(nxt_stmt[0]))
                    and _capture_is_whitelisted(_ASSIGN_STATUS.match(nxt_stmt[0]).group(1), after)
                )
            )
        )
        ops = [op for _, op in elems]
        for e_i, (pipe, op) in enumerate(elems):
            for cmd in pipe:
                for inner in _inner_scripts(_strip_wrappers(list(cmd))):
                    findings += analyse(
                        inner, f"{where} (inside `-c`)", errexit=False, unattended=True
                    )
                for tok in cmd:
                    body = _group_body(tok)
                    if body is not None:
                        findings += analyse(
                            body,
                            where,
                            pipefail=pipefail,
                            errexit=errexit,
                            unattended=unattended,
                            # A brace group's end is terminal only if the group is.
                            tail_terminal=terminal if tok.startswith(_BRACE) else True,
                        )
            gate_at = [k for k, cmd in enumerate(pipe) if is_gate(cmd)]
            if not gate_at:
                continue
            gate_txt = " ".join(pipe[gate_at[0]]).replace(_GROUP, "(").replace(_BRACE, "{")[:70]
            if any(k < len(pipe) - 1 for k in gate_at) and not pipefail:
                findings.append(
                    f"{where}: R1 pipe -- `{gate_txt}` is piped without pipefail, so its status is lost"
                )
            if conditional or (len(pipe) - 1) not in gate_at:
                continue
            if negated:
                findings.append(
                    f"{where}: R2 swallow -- `! {gate_txt}` inverts the gate's status, and set -e ignores it"
                )
                continue
            # When the gate fails, `&&` short-circuits to the FIRST `||` after it,
            # and what follows that `||` is what runs. So the rescue must be the
            # element after the first `||`, be the last element (exactly one
            # statement), and be whitelisted. `gate || exit 0 || exit 1` exits 0.
            first_or = next((k for k in range(e_i, len(elems) - 1) if ops[k] == "||"), None)
            rescued = (
                first_or is not None
                and first_or + 1 == len(elems) - 1
                and _rescue(elems[first_or + 1][0], nxt_stmt if seps_plain else [], errexit)
            )
            if first_or is not None and not rescued:
                findings.append(
                    f"{where}: R2 swallow -- `{gate_txt} || ...` turns the gate's failure into success"
                )
            elif op == "&&" and first_or is None and not last_stmt and not captured:
                findings.append(
                    f"{where}: R3 mid-list -- `{gate_txt} && ...` is followed by more statements; "
                    "under set -e its failure does not stop them"
                )
            elif op is None and unattended and not errexit and not last_stmt and not captured:
                findings.append(
                    f"{where}: R4 no errexit -- `{gate_txt}` is not the last statement and set -e "
                    "is off, so what runs next overwrites its status"
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


Source = tuple[str, str, dict]


def _shell_flags(shell: str | None) -> dict:
    """What GitHub runs a step under. Default: `bash -e {0}`; `bash`: `bash -eo pipefail`.

    A custom string (`bash -euo pipefail {0}`, `bash {0}`) is read for its own
    flags: the first version compared it to "bash" and read every custom shell
    as no-pipefail, and `bash {0}` -- no -e at all -- as errexit.
    """
    base = {"unattended": True}
    if shell is None or shell.strip() == "sh":
        return {**base, "errexit": True, "pipefail": False}
    s = shell.strip()
    if s == "bash":
        return {**base, "errexit": True, "pipefail": True}
    flags = [w for w in s.split() if w.startswith("-") and not w.startswith("--")]
    return {**base, "errexit": any("e" in w[1:] for w in flags), "pipefail": "pipefail" in s}


def workflow_scripts(root: Path) -> list[Source]:
    import yaml

    wfs = sorted((root / ".github" / "workflows").glob("*.y*ml"))
    if not wfs:
        raise CouldNotLook(f"no workflows under {root / '.github' / 'workflows'}")
    out: list[Source] = []
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
                    out.append((str(run), f"{wf.name} / {jname} / {name}", _shell_flags(shell)))
    return out


def hook_scripts(root: Path) -> list[Source]:
    import yaml

    cfg = root / ".pre-commit-config.yaml"
    if not cfg.exists():
        return []
    try:
        doc = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CouldNotLook(f"{cfg} does not parse: {exc}") from exc
    out: list[Source] = []
    for repo in doc.get("repos") or []:
        for hook in repo.get("hooks") or []:
            entry = hook.get("entry")
            if entry:
                out.append(
                    (
                        str(entry),
                        f".pre-commit-config.yaml / {hook.get('id')}",
                        {"errexit": False, "unattended": True},
                    )
                )
    return out


def shell_file_scripts(root: Path) -> list[Source]:
    out: list[Source] = []
    for p in sorted(root.rglob("*.sh")):
        rel = p.relative_to(root).as_posix()
        if "node_modules" in p.parts or rel.startswith(".git/"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CouldNotLook(f"cannot read {rel}: {exc}") from exc
        first = text.splitlines()[0] if text else ""
        errexit = first.startswith("#!") and any(
            w.startswith("-") and not w.startswith("--") and "e" in w[1:] for w in first.split()[1:]
        )
        opts = {"errexit": errexit, "unattended": True, "pipefail": "pipefail" in first}
        out.append((text, rel, opts))
    return out


def _names_a_gate(block: str) -> bool:
    """Could this unparseable text name a gate? Derived from `is_gate`, one definition.

    The first version used its own word list, narrower than `is_gate`: a block
    running `bash tests/gates/x.sh` read as prose, so could-not-look became clean.
    """
    try:
        if any(is_gate(line.split()) for line in block.splitlines() if line.strip()):
            return True
        return any(is_gate([w]) for w in re.findall(r"[A-Za-z0-9_./:@-]+", block))
    except CouldNotLook:
        return True  # it could not even be read as candidate commands


def _block_has_gate(block: str) -> bool:
    try:
        return _script_has_gate(block)
    except CouldNotLook as exc:
        # Most such blocks are prose or transcripts. One that names a gate is
        # not known to be prose, and reading it as "no gate" was could-not-look
        # sharing a branch with clean.
        if _names_a_gate(block):
            raise CouldNotLook(f"an indented block names a gate but does not parse: {exc}") from exc
        return False


def claude_md_scripts(root: Path) -> list[Source]:
    md = root / "CLAUDE.md"
    if not md.exists():
        raise CouldNotLook(f"no CLAUDE.md under {root}: its command blocks cannot be read")
    lines = md.read_text(encoding="utf-8").splitlines()
    out: list[Source] = []
    i = 0
    while i < len(lines):
        if _FENCE.match(lines[i]):
            start = j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append(("\n".join(lines[start:j]), f"CLAUDE.md:{start}", {"errexit": False}))
            i = j + 1
            continue
        if lines[i].startswith("    ") and (i == 0 or not lines[i - 1].strip()):
            j = i
            while j < len(lines) and (lines[j].startswith("    ") or not lines[j].strip()):
                j += 1
            block = "\n".join(ln[4:] for ln in lines[i:j])
            try:
                has = _block_has_gate(block)
            except CouldNotLook as exc:
                raise CouldNotLook(f"CLAUDE.md:{i + 1}: {exc}") from exc
            if has:
                out.append((block, f"CLAUDE.md:{i + 1}", {"errexit": False}))
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
        groups = {
            "workflow steps": workflow_scripts(root),
            "hook entries": hook_scripts(root),
            ".sh files": shell_file_scripts(root),
            "CLAUDE.md blocks": claude_md_scripts(root),
        }
        findings: list[str] = []
        for scripts in groups.values():
            for script, where, opts in scripts:
                try:
                    findings += analyse(script, where, **opts)
                except CouldNotLook as exc:
                    raise CouldNotLook(f"{where}: {exc}") from exc
    except CouldNotLook as exc:
        print(f"check-shell-status: could not look -- {exc}")
        return 2
    scope = ", ".join(f"{len(v)} {k}" for k, v in groups.items())
    if findings:
        print(f"check-shell-status: {len(findings)} finding(s) in {scope}:")
        for f in findings:
            print(f"  {f}")
        return 1
    print(
        f"check-shell-status: none of R1-R4 found in {scope}. A line-level heuristic, "
        "not a shell parser, so a floor, not a census. NOT modelled: functions, sourced "
        "files, command variables, loop bodies and while/until conditions, unlisted "
        "wrappers, unquoted $(gate) in echo/export/local, backgrounded gates, heredoc "
        "bodies, trap EXIT (#586); package.json scripts are not scanned, and pwsh/python "
        "steps are read as shell (#587). See its docstring."
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
