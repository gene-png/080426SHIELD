"""A commit's subject must not name a decision the commit does not add.

## The failure this replaces

A branch carried a commit subject reading `docs(decisions): D-072 -- the
instrument exits 0 with failures on record`. The entry it actually added was
**D-078**. `main` had meanwhile grown D-072 through D-077, all legitimately.

Rebasing produced a conflict in `DECISIONS.md` at every commit that touched it,
and each one LOOKED like a D-number clash: the subject said D-072, the file
already had a D-072, and the two were unrelated. Every conflict had to be
opened and read to discover it was positional -- two appends to an append-only
file -- rather than a collision. None of them was a collision.

The subject is the one place a reader looks before opening the diff, and it was
the only thing that was wrong.

## What this checks: a MISMATCH, not an omission

If a commit's subject names a `D-NNN` **and** the commit adds a different one,
that is the defect. A subject naming no number at all is not flagged.

That boundary was chosen by measurement rather than taste. Every merge on
`main` is a squash whose subject is the PR title -- `docs: record the
false-remedy class, and fix twins and prose by shape (#249)` adds D-076 and
D-077 and names neither. **Requiring completeness would fail every legitimate
merge in the repo's history while catching one real defect.** Requiring
consistency fails exactly that one defect and nothing else; both were run
against the real commits before this boundary was chosen.

It also targets the harm precisely: a subject naming no number causes no false
clash on a rebase. A subject naming the WRONG one is what made every positional
append look like a collision.

## Silent-success branches, enumerated before the first line

Exits 0 for:

  * **no commit in the range touches `DECISIONS.md`** -- the common case.
  * **a commit's subject names no decision** -- squash merges, and any ordinary
    edit. Nothing to be inconsistent with.
  * **a commit touches the file and adds no `## D-NNN` heading** -- a
    correction or amendment to an existing entry.
  * **every number the subject names is among those added** -- the passing
    state.

And the paths that do not:

  * **the subject names a number the commit does not add** -- exit 1.
  * **`git` is unavailable, or the range cannot be resolved** -- exit 2. With
    no commits to read, every branch would look clean, and "I could not look"
    must not share an exit with "nothing to complain about".

## The range is TWO dots, deliberately

`git log A...B` is the SYMMETRIC DIFFERENCE and would pull in the base's own
commits, judging this branch on prose nobody on it wrote. `audit-gate.yml`
shipped exactly that defect and it is recorded in
`test_audit_gate_collects_only_this_branch.py`. Two dots.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_COULD_NOT_LOOK = 2

#: A decision heading as `DECISIONS.md` writes them, SUFFIX INCLUDED: `D-059a`
#: is a distinct entry from `D-059`, and a pattern that truncates the letter
#: reports the pair as a duplicate. That exact false positive was produced,
#: believed and reported before being caught, so the suffix is captured on
#: purpose in both patterns here.
_HEADING = re.compile(r"^\+##\s*(D-\d+[a-z]*)\b", re.M)

#: The same id as a subject line writes it.
_SUBJECT_NUMBER = re.compile(r"\bD-\d+[a-z]*\b", re.I)


def _git(*args: str) -> str:
    # S603/S607: the argument list is built from this script's own constants and
    # the two refs its caller passes; nothing here is user input, and `git` is
    # resolved from PATH deliberately so the check works in the CI image and in
    # a developer shell without hardcoding either location. `shell=False` is the
    # default and is what makes the ref strings safe to pass through.
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607 - PATH lookup, see above
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def added_decisions(sha: str, path: str) -> list[str]:
    """The `## D-NNN` headings this commit ADDS to `path`."""
    diff = _git("show", "--format=", "--unified=0", sha, "--", path)
    return _HEADING.findall(diff)


def subject_decisions(subject: str) -> list[str]:
    return _SUBJECT_NUMBER.findall(subject)


def inconsistent(subject: str, added: list[str]) -> list[str]:
    """Numbers the subject claims that the commit does not add."""
    have = {a.upper() for a in added}
    return [n for n in subject_decisions(subject) if n.upper() not in have]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Subjects must match the decisions added.")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--file", default="DECISIONS.md")
    args = ap.parse_args(argv)

    rng = f"{args.base}..{args.head}"  # TWO dots -- see the module docstring.
    try:
        listed = _git("log", "--format=%H%x00%s", rng, "--", args.file)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(
            f"check-decision-numbers: could not look -- `git log {rng}` failed "
            f"({type(exc).__name__}). A range that cannot be resolved makes every "
            f"branch look clean, so this is not reported as a pass.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    commits = [ln.split("\0", 1) for ln in listed.splitlines() if "\0" in ln]
    if not commits:
        print(f"check-decision-numbers: no commit in {rng} touches {args.file}.")
        return EXIT_OK

    problems: list[str] = []
    checked = 0
    for sha, subject in commits:
        if not subject_decisions(subject):
            continue  # names no decision; nothing to be inconsistent with
        try:
            added = added_decisions(sha, args.file)
        except subprocess.CalledProcessError:
            print(
                f"check-decision-numbers: could not look -- `git show {sha[:8]}` " f"failed.",
                file=sys.stderr,
            )
            return EXIT_COULD_NOT_LOOK
        if not added:
            continue
        checked += 1
        wrong = inconsistent(subject, added)
        if wrong:
            problems.append(
                f"  {sha[:8]}  subject names {', '.join(wrong)}\n"
                f"            but adds     {', '.join(added)}\n"
                f"            subject: {subject}"
            )

    if problems:
        print(
            "\n".join(
                [
                    "",
                    "check-decision-numbers: a subject names a decision the commit",
                    "does not add.",
                    "",
                    *problems,
                    "",
                    "The subject is the one thing a reader sees before opening the diff,",
                    "and on a rebase it is what makes an ordinary positional append look",
                    "like a D-number collision. Every conflict then has to be opened and",
                    "read to find out it was not one.",
                    "",
                    "Amend the subject to the number the commit actually adds.",
                    "",
                ]
            ),
            file=sys.stderr,
        )
        return EXIT_MISMATCH

    print(
        f"check-decision-numbers: clean -- {checked} commit(s) both naming and "
        f"adding a decision, each consistent ({len(commits)} touched {args.file})."
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
