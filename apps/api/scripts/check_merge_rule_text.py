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

WHAT IT COMPARES. The BYTES of CLAUDE.md's `## The merge rule` section -- from
that heading to the next `## ` heading, which includes `### Condition 5: the
paths` and its list -- at the PR's merge base and at its head. Any difference,
including whitespace and line endings, is a change.

THE BOUNDARY IS PINNED, at both ends of the range. There must be EXACTLY ONE
`## The merge rule` heading, and `### Condition 5: the paths` must lie inside
its section. Otherwise the gate cannot say which text is the rule: a decoy
copy inserted above the real section would be read instead of it, and a `## `
heading inserted above the path list would end the section early, so that
later path-list edits compared green (review of 6fcc02f). Either is exit 2.

EXIT CODES (the gates' 0/1/2 convention), and a green means one thing only:
0 the section is byte-identical at base and head; 1 it CHANGED, and the
changed lines are printed; 2 could not look -- the section is missing, doubled,
or no longer contains `### Condition 5: the paths`, at the base or the head (a
renamed heading is could-not-look, so it is red too); git cannot read the base
or the head; CLAUDE.md is missing; or a bad argument.

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
_CONDITION_5 = re.compile(r"^### Condition 5: the paths\b", re.M)


class CouldNotLook(Exception):
    """The check could not establish the answer. Maps to exit 2."""


def section(text: str, where: str) -> str:
    """The `## The merge rule` section, heading included, up to the next `## `."""
    starts = list(_START.finditer(text))
    if not starts:
        raise CouldNotLook(f"no `## The merge rule` section in CLAUDE.md at {where}")
    if len(starts) > 1:
        raise CouldNotLook(
            f"{len(starts)} `## The merge rule` headings in CLAUDE.md at {where}: which one "
            "is the rule is unknown, and a decoy could be read instead of it"
        )
    m = starts[0]
    rest = text[m.end() :]
    nxt = _NEXT.search(rest)
    body = text[m.start() : m.end() + (nxt.start() if nxt else len(rest))]
    if not _CONDITION_5.search(body):
        raise CouldNotLook(
            f"`### Condition 5: the paths` is not inside the merge rule's section at {where}: "
            "the section ends early or the subsection moved, so the path list is not compared"
        )
    return body


def _git(repo: Path, *args: str) -> str:
    """git's stdout DECODED BUT UNTRANSLATED: a CRLF stays a CRLF, so it compares."""
    try:
        proc = subprocess.run(  # noqa: S603  # nosec B603 - fixed argv
            ["git", "-C", str(repo), *args],  # noqa: S607
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CouldNotLook("`git` is not installed here") from exc
    err = proc.stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        raise CouldNotLook(f"`git {' '.join(args)}` exited {proc.returncode}: {err}")
    try:
        return proc.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CouldNotLook(f"`git {' '.join(args)}` output is not UTF-8") from exc


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
            # read_bytes, not read_text: universal newlines would make a CRLF
            # edit compare equal to the LF original.
            texts.append(p.read_bytes().decode("utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
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
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            "merge base",
            "head",
            n=0,
        )
    )
    changed = [
        ln.rstrip("\n").replace("\r", "\\r")  # show a CR, which is otherwise invisible
        for ln in diff
        if ln[:1] in "+-" and not ln.startswith(("+++", "---"))
    ]
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
