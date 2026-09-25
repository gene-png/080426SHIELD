#!/usr/bin/env python3
"""A PR that changes the merge rule section's bytes goes red, every time (interim, #572).

WHY THIS EXISTS. The merge rule in CLAUDE.md decides when an agent may merge
without the owner. A PR can edit the rule and, under the rule as it then
reads, clear itself: nothing in condition 5 lists CLAUDE.md, and the rule's own
conditions are not a listed path (#572). Until CODEOWNERS covers the
governance files (the owner's decision, after the bot account exists), this
makes every change to the rule's text VISIBLE as a red check, so a human reads
it before anything merges on it. There is no label and no opt-out marker;
editing this workflow step is a stated limit (#572, #585).

WHAT IT COMPARES. The BYTES of CLAUDE.md's `## The merge rule` section -- from
that heading to the `## Real commands` heading, which includes `### Condition
5: the paths` and its list -- at the PR's merge base and at its head. Any
difference, including whitespace and line endings, is a change.

WHAT IS PINNED, checked separately in the base's CLAUDE.md and in the head's,
so the gate knows which text is the rule:
  * the start: EXACTLY ONE `## The merge rule` heading (a decoy copy would
    otherwise be read instead of the real section);
  * the end: EXACTLY ONE `## Real commands` heading, below the start, and it
    must be the FIRST `## ` line after the start. Any other `## ` line in between -- above the
    path list, inside it, lower down, or at column 0 inside a code fence --
    would end the section early, so the text after it would compare green
    (reviews of 6fcc02f and 2ae1650);
  * the subsection: `### Condition 5: the paths` lies inside the section.
Any of the three failing, at the base or the head, is exit 2.

EXIT CODES (the gates' 0/1/2 convention), and a green means one thing only:
0 the section is byte-identical at base and head; 1 it CHANGED, and the
changed lines are printed; 2 could not look -- a pin above fails (a renamed
heading is could-not-look, so it is red too); git cannot read the base or the
head; CLAUDE.md is missing; or a bad argument.

LIMITS, stated so a green is not read as more than it is:
  * It sees bytes, not meaning. A change that leaves the section's bytes
    identical while altering how it is read (wrapping it in an HTML comment,
    adding a second rule under a variant heading elsewhere, or editing this
    workflow step) is out of scope. It catches edits, not evasion (#585).
  * It enforces VISIBILITY, not a signature. A red check can still be merged
    past by anyone the branch settings allow; it only guarantees the change is
    not silent.
  * It does not catch a SEMANTIC change outside the section: a D-record the
    rule cites, an agent definition in `.claude/agents/`, or the code of a gate
    the rule relies on (the condition-5 path matcher, #581's compose check).
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
_NEXT = re.compile(r"^## .*$", re.M)
_END = re.compile(r"^## Real commands\b.*$", re.M)
_CONDITION_5 = re.compile(r"^### Condition 5: the paths\b", re.M)


class CouldNotLook(Exception):
    """The check could not establish the answer. Maps to exit 2."""


def section(text: str, where: str) -> str:
    """The `## The merge rule` section, heading included, up to `## Real commands`."""
    starts = list(_START.finditer(text))
    if not starts:
        raise CouldNotLook(f"no `## The merge rule` section in CLAUDE.md at {where}")
    if len(starts) > 1:
        raise CouldNotLook(
            f"{len(starts)} `## The merge rule` headings in CLAUDE.md at {where}: which one "
            "is the rule is unknown, and a decoy could be read instead of it"
        )
    ends = list(_END.finditer(text))
    if len(ends) != 1:
        raise CouldNotLook(
            f"{len(ends)} `## Real commands` headings in CLAUDE.md at {where}: the heading "
            "that ends the merge rule's section must occur exactly once"
        )
    m = starts[0]
    if ends[0].start() < m.start():
        raise CouldNotLook(
            f"`## Real commands` comes BEFORE `## The merge rule` in CLAUDE.md at {where}: "
            "the heading that ends the section precedes it, so where the section ends is unknown"
        )
    rest = text[m.end() :]
    nxt = _NEXT.search(rest)
    if nxt is None or m.end() + nxt.start() != ends[0].start():
        found = f"`{nxt.group(0)}`" if nxt else "the end of the file"
        raise CouldNotLook(
            f"the merge rule's section at {where} is interrupted by {found} before "
            "`## Real commands`: the text after it would not be compared"
        )
    body = text[m.start() : m.end() + nxt.start()]
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
            "check-merge-rule-text: the merge rule section's bytes are unchanged "
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
        f"check-merge-rule-text: this PR CHANGES the merge rule section's bytes ({len(changed)} line(s)). "
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
