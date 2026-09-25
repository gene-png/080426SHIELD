#!/usr/bin/env python3
"""A PR that changes the merge rule's text goes red, every time (interim, #572).

WHY THIS EXISTS. The merge rule in CLAUDE.md decides when an agent may merge
without the owner. A PR can edit the rule and, under the rule as it then
reads, clear itself: nothing in condition 5 lists CLAUDE.md, and the rule's own
conditions are not a listed path (#572). Until CODEOWNERS covers the
governance files (the owner's decision, after the bot account exists), this
makes every change to the rule's text VISIBLE as a red check, so a human reads
it before anything merges on it. There is no label and no escape of any kind:
a change to the rule is always red.

WHAT IT COMPARES. The text of CLAUDE.md's `## The merge rule` section -- from
that heading to the next `## ` heading, which includes `### Condition 5: the
paths` and its list -- at the PR's merge base and at its head. Any difference
in any line, including whitespace, is a change.

EXIT CODES (the gates' 0/1/2 convention), and a green means one thing only:
0 the section is byte-identical at base and head; 1 it CHANGED, and the
changed lines are printed; 2 could not look -- the section is missing at the
base or the head (a renamed heading is could-not-look, so it is red too), git
cannot read the base or the head, CLAUDE.md is missing, or a bad argument.

LIMITS, stated so a green is not read as more than it is:
  * It enforces VISIBILITY, not a signature. A red check can still be merged
    past by anyone the branch settings allow; it only guarantees the change is
    not silent.
  * It does not catch a SEMANTIC change outside the section: a D-record the
    rule cites, an agent definition in `.claude/agents/`, or the code of a gate
    the rule relies on (the condition-5 path matcher, `compose_unchanged.py`).
  * A PR that edits THIS GATE'S OWN WORKFLOW STEP can neuter it: the workflow
    runs from the PR (`on: pull_request`). That stays open until CODEOWNERS
    covers `.github/workflows/` and the bot account exists (#572).
  * It is not a required check; that is the owner's branch-protection setting.

USAGE:
  python check_merge_rule_text.py --range BASE..HEAD [--repo DIR]
  python check_merge_rule_text.py --old FILE --new FILE      (two CLAUDE.md copies)
"""

from __future__ import annotations

import difflib
import re
import subprocess
import sys
from pathlib import Path

_START = re.compile(r"^## The merge rule\b.*$", re.M)
_NEXT = re.compile(r"^## ", re.M)


class CouldNotLook(Exception):
    """The check could not establish the answer. Maps to exit 2."""


def section(text: str, where: str) -> str:
    """The `## The merge rule` section, heading included, up to the next `## `."""
    m = _START.search(text)
    if not m:
        raise CouldNotLook(f"no `## The merge rule` section in CLAUDE.md at {where}")
    rest = text[m.end() :]
    nxt = _NEXT.search(rest)
    return text[m.start() : m.end() + (nxt.start() if nxt else len(rest))]


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(  # noqa: S603  # nosec B603 - fixed argv
            ["git", "-C", str(repo), *args],  # noqa: S607
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError as exc:
        raise CouldNotLook("`git` is not installed here") from exc
    if proc.returncode != 0:
        raise CouldNotLook(
            f"`git {' '.join(args)}` exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout


def from_range(repo: Path, rng: str) -> tuple[str, str]:
    if ".." not in rng or "..." in rng:
        raise CouldNotLook(f"--range must be BASE..HEAD, got {rng!r}")
    base, head = rng.split("..", 1)
    merge_base = _git(repo, "merge-base", base, head).strip()
    if not merge_base:
        raise CouldNotLook(f"no merge base for {rng}")
    old = _git(repo, "show", f"{merge_base}:CLAUDE.md")
    new = _git(repo, "show", f"{head}:CLAUDE.md")
    return section(old, f"the merge base {merge_base[:7]}"), section(new, f"the head {head}")


def from_files(old: Path, new: Path) -> tuple[str, str]:
    texts = []
    for p in (old, new):
        try:
            texts.append(p.read_text(encoding="utf-8"))
        except OSError as exc:
            raise CouldNotLook(f"cannot read {p}: {exc}") from exc
    return section(texts[0], str(old)), section(texts[1], str(new))


def _parse(argv: list[str]) -> dict:
    opts: dict = {}
    args = list(argv[1:])
    while args:
        flag = args.pop(0)
        if flag in ("--range", "--repo", "--old", "--new") and args:
            opts[flag] = args.pop(0)
        else:
            raise CouldNotLook(f"unknown or incomplete argument: {flag!r}")
    if ("--range" in opts) == ("--old" in opts or "--new" in opts):
        raise CouldNotLook("need exactly one of --range, or --old with --new")
    if "--range" not in opts and not ("--old" in opts and "--new" in opts):
        raise CouldNotLook("--old and --new go together")
    return opts


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        opts = _parse(argv)
        if "--range" in opts:
            old, new = from_range(Path(opts.get("--repo", ".")), opts["--range"])
        else:
            old, new = from_files(Path(opts["--old"]), Path(opts["--new"]))
    except CouldNotLook as exc:
        print(f"check-merge-rule-text: could not look -- {exc}")
        return 2
    if old == new:
        print(
            "check-merge-rule-text: the merge rule's text is unchanged "
            f"({len(new.splitlines())} lines compared). This says nothing about "
            "the gates, records or agent files it relies on."
        )
        return 0
    diff = list(
        difflib.unified_diff(
            old.splitlines(), new.splitlines(), "merge base", "head", n=0, lineterm=""
        )
    )
    changed = [ln for ln in diff if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
    print(
        f"check-merge-rule-text: this PR CHANGES the merge rule ({len(changed)} line(s)). "
        "A human must read it before anything merges on it (#572):"
    )
    for line in changed:
        print(f"  {line}")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-merge-rule-text: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation.{nl}")
        raise SystemExit(2) from exc
