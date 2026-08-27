#!/usr/bin/env python
"""Fail when a doc states a spelled-out count of something that changes.

WHY THIS IS A CHECK AND NOT A FIFTH PARAGRAPH. Four documentation rules about
staleness have not held. The counts that went wrong on 2026-08-25/26 were all
written by someone who had just written a rule against exactly that:

  * "Open mvp-blocking issues (20)" under a paragraph certifying it read live
  * "Nine issues closed" in the bullet INTRODUCING the lesson about stale counts
  * "Four instances in one week" over a list of five, in the same bullet
  * "Three instances in two days" over four bullets, two lessons down
  * "A fourth citation was drafted and withdrawn" under a list of five
  * "five of the sixteen were pre-existing on main" when the figure was one
  * "the only two items with data" over a table with three rows

Seven, in two days, in the four files that document the rule. That is D-051's
argument verbatim: discipline against a known shape has failed here every time it
has been tried, and a two-second deterministic check has not.

## The rule this enforces

A spelled cardinal in front of a VOLATILE noun is a number recalled rather than
derived. Two ways to satisfy the gate, in preference order:

  1. DELETE THE COUNT. If the number describes a list in the same document, say
     "The blockers:" and let the list be the count. This removes the failure mode
     rather than managing it, and costs nothing.

  2. CITE IT. If the number comes from outside the document, paste what produced
     it and when, on the same line or the line above:

         <!-- counted: gh issue list --label mvp-blocking --state open
              --json number | jq length, 2026-08-26 -->

     If you cannot paste the command, you do not know the number.

## What it does NOT flag, and why the noun list is hand-built

About 100 of the ~154 spelled cardinals in the doc set are stable domain facts --
"five services", "four assessment services", "two developers". Those must not be
swept up, so this matches a cardinal only in front of nouns that change AS WORK
PROCEEDS. The list is enumerated below and is therefore a FLOOR, not a census:
a volatile noun nobody thought of is a miss. Extend it when one is found rather
than widening to all plural nouns, which would bury the signal.

## EXIT CODES, per this repo's fail-closed convention (D-051)

  0 - no unprovenanced recalled counts
  1 - at least one found
  2 - could not read a file (an unreadable input is NOT a pass)
"""

from __future__ import annotations

import contextlib
import re
import sys
from pathlib import Path

# Shared documents. A wrong count in one of these is a claim every reader of
# the repo is entitled to rely on, and anyone may fix it. Enforced.
ENFORCED_TARGETS = [
    "CLAUDE.md",
    "CONTEXT.md",
    "DELIVERY_PLAN.md",
    "docs/security.md",
    "docs/operations.md",
    "docs/architecture.md",
]

# The personal status files are IN the doc set -- `gene.md` is where the "(20)"
# heading and its freshness certificate lived, and owner-write-only by
# convention makes them likelier to drift, not less. They are REPORTED rather
# than enforced for a reason that is about the convention, not about wanting an
# exemption: `CLAUDE.md` says each file is written by its owner ONLY. A blocking
# gate on `dave.md` would therefore hold Gene's PR red on a line Gene may not
# edit, and vice versa -- the gate would be stopping the wrong person, and the
# only ways out are to break the ownership rule or to merge past a red check.
#
# Reporting has its own failure mode and it is named where the CI step declares
# it, not here: a finding nobody reads is a check that does not exist.
ADVISORY_TARGETS = [
    "context/gene.md",
    "context/dave.md",
]

# A human sweep wants everything; `--all` is that. Bare invocation is what CI
# blocks on, so it is the enforced set alone.
DEFAULT_TARGETS = ENFORCED_TARGETS

# Spelled cardinals. Digits are deliberately NOT matched: "14 open" beside a
# command is the FIXED form this gate steers towards, and flagging it would
# punish the correction.
_CARDINALS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    "fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|"
    "fifty|sixty|seventy|eighty|ninety|hundred"
)

# Nouns whose count changes as work proceeds. A FLOOR, not a census -- see the
# docstring. Each is here because a count of it went stale in this repo.
_VOLATILE = (
    "issues?|blockers?|findings?|instances?|rounds?|sessions?|gates?|sweeps?|"
    "bullets?|items?|commits?|defects?|regressions?|cells?|rows?|guards?|"
    "citations?|corpora|corpuses|leaks?|residuals?|checks?|specs?|migrations?|"
    "measurements?|overruns?|passes|violations?|entries"
)

_PATTERN = re.compile(
    rf"\b(?:{_CARDINALS})\b[\s\-]+(?:more\s+|further\s+|new\s+|other\s+|"
    rf"real\s+|live\s+|open\s+|such\s+)?(?:{_VOLATILE})\b",
    re.IGNORECASE,
)

# The provenance marker, in the shape this repo already uses for exemptions
# (`# test-integrity:`, `# separator-class:`). An empty marker is not a marker.
_PROVENANCE = re.compile(r"<!--\s*counted:\s*(\S.*?)-->", re.IGNORECASE | re.DOTALL)

# A count immediately followed by its own list is the FIXED form of rule 1 only
# when the number is gone; while it is present it is still a recalled count.
# But a cardinal inside a quotation of a PREVIOUS wrong count is the record of
# the fix, not a new instance -- those carry this marker.
# NOTE: there is deliberately no separate `historical` pattern. `historical` and
# a pasted command are different claims TO A READER, but the gate treats any
# non-empty reason alike -- it cannot judge whether a set can grow. A compiled
# constant matching only `historical` sat here with no call sites until the
# adversarial reviewer found it: a function with no callers, inside the gate,
# which is one of the four modes in this repo's own shape statement.


def _provenance_window(lines: list[str], index: int) -> str:
    """The line itself, the two above, and the two below.

    A marker may sit above a wrapped sentence or below a table, and prettier
    reflows prose, so the window has to be wider than one line. Deliberately
    generous: a false exemption costs one stale count, a false positive costs
    the gate its credibility.
    """
    start = max(0, index - 2)
    end = min(len(lines), index + 3)
    return "\n".join(lines[start:end])


def check(text: str) -> list[tuple[int, str, str]]:
    """Return (lineno, matched phrase, the line) for each unprovenanced count."""
    lines = text.split("\n")
    findings: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        for match in _PATTERN.finditer(line):
            window = _provenance_window(lines, i)
            if _PROVENANCE.search(window):
                continue
            findings.append((i + 1, match.group(0), line.strip()))
    return findings


def _echo(text: str) -> None:
    """Print without dying on a character the console cannot encode.

    Found the hard way: this gate CRASHED on a `→` in a quoted source line
    under Windows cp1252, part-way through the second of eight documents. It had
    already printed 35 findings, so the report LOOKED like a complete verdict --
    and Python exits 1 on an unhandled exception, which is the same code this
    gate uses for "violations found". A crash and a verdict were
    indistinguishable, in the checker written to catch exactly that shape.

    The real total was 73 across eight files; it never reached three of them.
    """
    # NOT the protection, despite how the docstring reads: encoding to UTF-8
    # always succeeds, so this round-trip is an identity and substitutes nothing.
    # The protection is `main`'s stdout.reconfigure(errors="replace"). If that
    # suppress ever fires, the gate still dies here -- now at exit 2 rather than
    # 1, which was the defect that mattered.
    safe = text.encode("utf-8", "replace").decode("utf-8")
    sys.stdout.write(safe + chr(10))


def repo_root() -> Path:
    """The repo root, resolved from this file: apps/api/scripts/x.py -> parents[3].

    RAISES rather than guessing when the layout is not what it expects. This
    used to be a bare `parents[3]`, which throws `IndexError` inside the api
    container -- where `/app` IS `apps/api`, so there is no fourth parent. That
    is the right OUTCOME (the crash handler turns it into exit 2, not a clean
    report on documents nobody opened) reached by the wrong route: an
    unexplained IndexError from pathlib tells the reader nothing. A gate that
    silently picked a different root would be the real disaster, so this refuses
    to pick one.

    Run this gate from the REPO ROOT, which is what `ci.yml` does.
    """
    return root_from(Path(__file__).resolve())


def root_from(here: Path) -> Path:
    """The repo-root rule, split out so it can be tested without moving files."""
    if len(here.parents) <= 3:
        raise RuntimeError(
            f"cannot resolve the repo root from {here} -- this gate expects to live at "
            "apps/api/scripts/ inside a full checkout, and must be run from the repo root"
        )
    return here.parents[3]


def main(argv: list[str], root: Path | None = None) -> int:
    # Any console, any codepage. Without this the gate is only as reliable as
    # the characters that happen to appear in the docs it quotes.
    with contextlib.suppress(AttributeError, OSError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    flags = {a for a in argv[1:] if a.startswith("--")}
    explicit = [a for a in argv[1:] if not a.startswith("--")]
    unknown = sorted(flags - {"--advisory", "--all", "--porcelain"})
    if unknown:
        _echo(f"check-recalled-counts: unknown option(s): {' '.join(unknown)}")
        _echo("Valid: --advisory (personal status files), --all (both sets),")
        _echo("       --porcelain (file<TAB>phrase<TAB>line, exit 0, for diffing).")
        return 2
    if explicit:
        targets = explicit
    elif "--all" in flags:
        targets = ENFORCED_TARGETS + ADVISORY_TARGETS
    elif "--advisory" in flags:
        targets = ADVISORY_TARGETS
    else:
        targets = DEFAULT_TARGETS
    root = root or repo_root()

    all_findings: list[tuple[str, int, str, str]] = []
    # COUNTED, never assumed. This used to report `len(targets)` -- the set the
    # gate MEANT to read -- in its own success message, which is a count
    # asserted rather than derived from what happened, inside the gate built to
    # catch exactly that. Fifth instance of the shape.
    checked = 0
    for rel in targets:
        path = root / rel
        if not path.exists():
            # A missing target used to `continue`, justified by a comment saying
            # "the doc set differs per checkout depth". That premise is FALSE and
            # was falsified by running it: `git clone --depth 1` yields history
            # depth 1 and every tracked file present, because depth controls
            # HISTORY, never the working tree. So the skip had no justification.
            #
            # It also guarded the wrong case. The old `read_any` flag fired only
            # when EVERY target was missing -- total blindness, which cannot happen
            # through CI's invocation, though `main()` can be called that way and a
            # test in this file does -- and stayed silent on one missing document,
            # which is the likely failure by an order of magnitude.
            #
            # The target list is committed beside the documents it names, so a
            # missing one means the list is wrong. That is fail-closed, not a skip.
            # stderr, not stdout: `--porcelain` writes machine-readable rows to
            # stdout, and the documented baseline-regeneration command redirects
            # stdout into a data file. Prose on that stream becomes baseline rows.
            nl = chr(10)
            sys.stderr.write(f"check-recalled-counts: MISSING target {rel}{nl}")
            sys.stderr.write(f"A document that could not be opened is not a clean document{nl}")
            sys.stderr.write(f"(D-051), and this gate will not report a verdict over a set it{nl}")
            sys.stderr.write(f"did not read.{nl}")
            return 2
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            _echo(f"check-recalled-counts: cannot read {rel}: {type(exc).__name__}")
            return 2
        checked += 1
        for lineno, phrase, line in check(text):
            all_findings.append((rel, lineno, phrase, line))

    if not checked:
        print("check-recalled-counts: read NOTHING -- no targets to check.")
        print("An unreadable doc set is not a clean doc set (D-051).")
        return 2

    if "--porcelain" in flags:
        # file<TAB>phrase<TAB>line-text. Keyed on the TEXT, never the line
        # number: a baseline keyed on line numbers reports a whole file as new
        # the first time someone inserts a paragraph above it, which is the
        # noise this mode exists to prevent.
        for rel, _lineno, phrase, line in all_findings:
            _echo(f"{rel}	{phrase}	{line}")
        return 0

    if not all_findings:
        print(f"check-recalled-counts: clean ({checked} documents)")
        return 0

    print("check-recalled-counts: spelled counts of things that change")
    print()
    for rel, lineno, phrase, line in all_findings:
        _echo(f"  {rel}:{lineno}: {phrase!r}")
        _echo(f"      {line[:100]}")
    print()
    print("A spelled count in front of a noun that changes is a number recalled,")
    print("not derived. This repo produced a run of them inside two days, every")
    print("one written by someone who had just written a rule against it.")
    print()
    print("Fix it one of two ways, in preference order:")
    print()
    print("  1. DELETE THE COUNT. If it describes a list in the same document,")
    print('     write "The blockers:" and let the list be the count.')
    print()
    print("  2. CITE IT. Paste what produced it, on the line or within two above:")
    print()
    print("         <!-- counted: gh issue list --label mvp-blocking --state open")
    print("              --json number | jq length, 2026-08-26 -->")
    print()
    print("     If you cannot paste the command, you do not know the number.")
    print()
    print("  For a count QUOTED as the record of a past error, mark it")
    print("  `<!-- counted: historical -->` -- it is the fix, not a new instance.")
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
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-recalled-counts: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(2) from exc
