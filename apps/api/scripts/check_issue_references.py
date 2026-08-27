"""Fail a PR that would close an issue by accident.

**Why this is a check and not a line in CLAUDE.md.** GitHub's issue-closing
parser matches a keyword followed by `#N` and does not read the words around it.
This repo has closed the same issue by accident **three times**, and each fix was
a better-worded rule:

1. A commit body read `Filed, not fixed: #NNN`. The parser sees `fixed: #NNN`.
   The rule added: never put a closing keyword near an issue number you are not
   closing.
2. The PR documenting that rule re-closed the same issue, because it QUOTED the
   offending sentence with the live number in it. The rule added: quotation
   marks and code fences are not exempt; use a placeholder number.
3. The PR that finished the work said `Closing keywords deliberately omitted --
   this repo has closed #NNN twice by accident`. `closed #NNN` is a valid match.
   Written, again, while explaining the trap.

Incident 3 also moved the surface: it was the **pull request description**, which
GitHub parses independently of commit messages, while every previous rule
targeted commit bodies.

Three rounds of documentation produced a fourth incident. #72's own finding is
that discipline against a known shape has failed nine recorded times in this
repo, including instances written minutes after the rule was logged. So: a
deterministic check, stdlib-only, sub-second, no model in the loop — the same
shape and the same argument as D-054's audit gate.

## What it checks

Every place GitHub reads: the PR **title**, the PR **description**, and every
**commit message** in the PR. Missing any one of them would have missed at least
one of the three incidents.

## What it does NOT do, deliberately

It does not ask GitHub whether the referenced issue exists. That sounds like the
precise version of "a REAL issue number" and it is the wrong trade twice over: it
puts a network call inside a merge gate, and it is unsound, because **issue
numbers only go up**. A closing keyword beside an invented number is inert today
and a live closing reference the day the repo reaches it. A number that is safe
now is not safe later.

(This paragraph originally made that point with a literal number, which made it
the sixth instance of the bug, inside the file written to prevent it. Caught by
running this checker over its own source.)

The sound alternative is a placeholder with **no digits** — `#NNN`. GitHub's
parser needs digits, so it cannot match, and it cannot become live. That is what
CLAUDE.md's examples use and what this check makes enforceable.

## The escape hatch

CLAUDE.md permits a closing keyword on the PR that genuinely closes the issue, so
this is not a prohibition — it is a demand that the intent be **stated**. Declare
it in the PR description:

    Auto-close-approved: <issue numbers, bare>

Bare numbers, no `#`. A marker containing the word "close" beside `#N` would
itself be an instance of the bug it guards.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: GitHub's closing keywords, verbatim from its documentation. Widening this is
#: safe; narrowing it is the only way this check can fail open, which is why the
#: test enumerates every form rather than sampling.
_KEYWORDS = r"clos(?:e|es|ed)|fix(?:|es|ed)|resolv(?:e|es|ed)"

#: Keyword, optional colon, any whitespace (a NEWLINE counts — GitHub does not
#: require them on the same line), then `#` and digits.
#:
#: `\b` before the keyword stops `prefixes #12` and `unfixed #12` matching on a
#: substring. Nothing after the keyword is anchored, because GitHub itself does
#: not care what follows.
_CLOSING = re.compile(rf"\b(?:{_KEYWORDS})\s*:?\s*#(\d+)", re.IGNORECASE)

#: Bare numbers, no `#`. See the module docstring for why.
_APPROVED = re.compile(r"^\s*Auto-close-approved:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def find_closing_references(text: str) -> list[int]:
    """Issue numbers this text would close, in order of appearance.

    Nothing is stripped first — not code fences, not blockquotes, not HTML
    comments. GitHub parses raw text, and incident 2 was a quoted sentence.

    HTML comments are scanned even though it is unconfirmed whether GitHub acts
    on a keyword inside one. Scanning them can only over-report; skipping them
    fails open, and the failure that matters here is the silent one. (Note the
    audit gate wants the opposite treatment for the same construct — there, text
    nobody can see must not count as evidence. Different question, opposite
    answer, both fail-closed.)
    """
    return [int(m.group(1)) for m in _CLOSING.finditer(text)]


def approved_numbers(body: str) -> set[int]:
    """Numbers the PR author declared they intend to close.

    Only bare digits count. That is also why every EXAMPLE of this marker -- here,
    in the module docstring, and in CLAUDE.md -- uses a non-numeric placeholder.
    An example carrying real digits is an auto-approving incantation: quote it
    into a PR description and it silently pre-approves closing those issues. The
    first draft of this file used `101, 102`, which are real. And issue numbers
    only go up, so invented digits approve nothing today and something later --
    the same argument this module makes about `#NNN`, one layer out.

    Found by running this checker over the documentation that describes it.
    """
    out: set[int] = set()
    for m in _APPROVED.finditer(body):
        for token in re.split(r"[,\s]+", m.group(1).strip()):
            if token.isdigit():
                out.add(int(token))
    return out


def _read(path: str, label: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"{label} file not found: {path}")
    return p.read_text(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reject accidental issue closes.")
    ap.add_argument("--title", required=True, help="file containing the PR title")
    ap.add_argument("--body", required=True, help="file containing the PR description")
    ap.add_argument("--commits", required=True, help="file containing every commit message")
    args = ap.parse_args(argv)

    try:
        title = _read(args.title, "title")
        body = _read(args.body, "body")
        commits = _read(args.commits, "commits")
    except FileNotFoundError as exc:
        # FAIL CLOSED. The audit gate shipped the opposite of this: empty input
        # made it print a positive message and exit 0. A guard that goes green
        # when it cannot read its input is worse than no guard, because it is
        # read as an assurance.
        print(f"issue-close guard: {exc}", file=sys.stderr)
        print("Refusing to report clean on input it could not read.", file=sys.stderr)
        return 2

    approved = approved_numbers(body)
    hits: list[tuple[str, int, str]] = []
    for where, text in (("title", title), ("description", body), ("commit message", commits)):
        for m in _CLOSING.finditer(text):
            number = int(m.group(1))
            if number in approved:
                continue
            start = max(0, m.start() - 60)
            snippet = " ".join(text[start : m.end() + 20].split())
            hits.append((where, number, snippet))

    if not hits:
        if approved:
            print(
                "issue-close guard: clean "
                f"({len(approved)} declared close{'s' if len(approved) != 1 else ''}: "
                f"{', '.join(str(n) for n in sorted(approved))})."
            )
        else:
            print("issue-close guard: clean — no closing references.")
        return 0

    print(
        "This PR would CLOSE issues on merge. GitHub matches a closing keyword "
        "followed by #<number> and does not read the words around it.\n",
        file=sys.stderr,
    )
    for where, number, snippet in hits:
        print(f"  {where}: would close #{number}", file=sys.stderr)
        print(f"    ...{snippet}...\n", file=sys.stderr)
    print(
        "If that is intended, declare it in the PR description:\n\n"
        "    Auto-close-approved: "
        + ", ".join(str(n) for n in sorted({n for _, n, _ in hits}))
        + "\n\n"
        "Bare numbers, no '#'.\n\n"
        "If it is NOT intended, rephrase. `filed as #N`, `see #N` and "
        "`tracked in #N` do not close anything.\n"
        "In examples, write '#NNN' — a placeholder with no digits cannot match "
        "GitHub's parser, and unlike a made-up number it cannot become a live "
        "issue later.\n\n"
        "Quotes, code fences and HTML comments are NOT exempt; the second "
        "accidental close in this repo was a quoted sentence, and the third was "
        "a sentence warning about the second.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    # A crash must NOT share an exit code with "violations found". Python exits
    # 1 on an unhandled exception, which is this gate's "found something" code,
    # so an uncaught error would read as a verdict it never reached.
    #
    # `BaseException` with both propagating cases NAMED, rather than the
    # equivalent `except Exception`: a handler that says out loud what it
    # declines to swallow does not rely on the reader knowing the inheritance
    # tree. `SystemExit` is somebody's deliberate exit code. `KeyboardInterrupt`
    # is an operator who knows exactly what happened and is owed 130, not
    # "could not look".
    #
    # Duplicated verbatim in every gate rather than shared -- an import is
    # one more thing that can fail BEFORE the handler is installed, which is the
    # defect this block exists to close. Drift is caught instead by
    # tests/unit/test_gate_crash_exit_code.py, which runs every one of them.
    try:
        raise SystemExit(main())
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"issue-close guard: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(2) from exc
