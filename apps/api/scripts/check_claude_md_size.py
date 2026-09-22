#!/usr/bin/env python
"""Refuse a governance file large enough to be TRUNCATED before an agent reads it.

WHY THIS EXISTS, and it is the only gate here whose subject is the rules
themselves. On 2026-09-22 `CLAUDE.md` reached 210,958 bytes against a reader
limit of 150,000. The last 60,958 bytes -- 29% of the file -- were cut away
before any agent saw them, and the cut landed in the worst possible place:

    "An agent merges on green"   first at byte 192,494   LOST
    "apps/api/tests/**"          4 occurrences           ALL LOST
    "tests/gates/**"             4 occurrences           ALL LOST
    "condition 5"                14 mentions             10 LOST

So every agent was told that a PR tripping condition 5 comes back to the human,
and none of them could read WHICH PATHS trip it. The merge rule -- the most
consequential rule in the repo, and the one this file's own ratchet marks as
never to be weakened -- was a heading with its body removed.

**It arrived as a tool error, not as a red build.** Eleven gates ran on every
PR and not one of them measured the file all eleven are described in. That is
the gap this closes.

## Why it was misdiagnosed, which is the part worth keeping

A subagent reported that its injected `CLAUDE.md` lacked `tests/gates/**` in
condition 5 while disk carried it. That is EXACTLY the signature of #170,
injected-context lag, which this repo had already recorded and already had a
remedy for ("re-read from disk"). The familiar explanation fit, so it was filed
as #170 and the real cause ran for at least three more days.

Truncation and staleness present identically to the reader -- a rule that is on
disk and not in context -- and the prescribed remedy for one is useless against
the other: re-reading from disk cannot help when the disk copy is what gets cut.
`CLAUDE.md` records the general form under "N independent sources reporting the
same absence are data, and a mechanism that explains them away costs one command
to test". This is that bullet's own subject matter, and it still took a tool
error to surface.

## What is measured, and in what unit

BYTES of the file as it sits on disk, which is the most primitive available
signal -- no newline interpretation, no encoding round-trip, nothing between the
number and the file. Characters are reported beside it because the two differ
here (210,958 bytes against 210,215 characters: 743 bytes of multi-byte UTF-8,
mostly em-dashes and arrows) and a reader comparing this output against a
`wc -c` or a `len()` elsewhere should be able to see which one they have.

Bytes are also the CONSERVATIVE unit: for UTF-8, bytes >= characters, so a file
passing this gate in bytes also passes in characters. It is not conservative
against a reader that counts TOKENS, and that residual is stated below rather
than papered over.

## The limit, and the two things it is NOT

`LIMIT_BYTES = 150_000` is the boundary MEASURED on 2026-09-22, by observing
where a reader actually cut the file. It is not a style preference and not a
target.

It is NOT the file's own budget. `CLAUDE.md` sets itself a 600-line budget,
which is roughly 40,000 bytes -- so a file can clear this gate while sitting
almost four times over what it says it allows itself. This gate is the floor
under the cliff, not the ratchet; the ratchet is a human reading the headroom
line this prints on every clean run.

It is NOT margin-free by oversight. There is no margin, deliberately: an
invented one would be a number nobody derived, in the gate attached to the rule
against exactly that. The residual is real and is written down instead -- if a
reader's limit is lower than 150,000, or counts tokens rather than bytes, this
gate goes green while rules are still being cut. The way to close that is to
MEASURE the next reader that truncates and lower the constant, not to guess a
percentage now.

## Fail-closed, per D-051

Exit 2 is "I could not look": a target that does not exist, is a directory, or
cannot be decoded; an unknown option. Exit 1 is "I looked and it is too big".
They must never share a branch -- `check_audit_evidence`'s `is_code_change([])`
printing "documentation-only change, exempt" and exiting 0 is the recorded
reason this convention exists.

An empty file is a PASS and not a could-not-look. That is deliberate and it is
the case most likely to be argued: this gate's proposition is "small enough to
be read whole", and a zero-byte file satisfies it. Whether the file has any
CONTENT is a different proposition, and a gate answering a question adjacent to
the one in its name is the failure `CLAUDE.md` records as a certificate over the
wrong proposition.

## What it does NOT do

It measures SIZE. It cannot tell whether the rules inside are good, whether a
trim moved a rule to `DECISIONS.md` or deleted it, or whether the most important
rule is near the top where a partial read would still reach it. Form is
mechanisable, implication is not (#213).

## The SOFT line, and why a hard gate alone was not enough

`SOFT_LIMIT_BYTES = 135_000` warns and does not fail. A gate that fires with no
prepared remedy reads as the gate being broken -- the first person to add a
paragraph hits a red build and concludes the check is in the way. A gate that
fires early and NAMES THE NEXT CUT is a ratchet. So `CLAUDE.md` carries a
section, "Where the next 15,000 bytes come from", listing three candidates in
order, each a RECORD whose instruction is already stated in one line above it;
this constant is what sends you to read it while there is still room to act.

The difference is entirely in whether the answer was written down before the
alarm, which is the same reason the fail-closed convention names its branches
before the first line of a checker gets written.

## `--require-canary`: the variance the size gate CANNOT fix

The reader limit is a property of the READER. On 2026-09-22 one session's
injected copy carried all 210,958 bytes while another reader's was cut at
150,000 -- same commit, same file, different rule sets. Two agents can examine
the same PR, apply the merge rule sincerely, and reach opposite verdicts on
condition 5, and NEITHER CAN TELL WHICH ONE IT IS: nothing in either agent's
output distinguishes "this PR is clear" from "I could not see the clause that
would have caught it".

That is D-051's distinction -- "I checked and it passes" versus "I could not
look" -- missing from the governance layer itself. Keeping this file under the
limit fixes today's instance and not the mechanism: it goes over budget again
eventually, or a reader arrives with a limit below 150,000, and it recurs
silently.

`CLAUDE.md` therefore ends with a canary marker and an instruction to stop if
you cannot read it. `--require-canary` asserts the marker is the **last
non-empty line**, because the marker only answers "did I receive the whole
file" while nothing follows it -- an append below it leaves the canary readable
and everything after it invisible, which is strictly worse than no canary, since
the reader now has a POSITIVE signal that its copy is whole.

It is a FLAG rather than always-on because this gate is reusable for any
governance file, and the fixture files are themselves named `CLAUDE.md` without
carrying canaries. `ci.yml` passes it for the real file. Both refusal branches
exit 2 -- a missing marker and a mispositioned one are could-not-looks, not
findings about size.

## `--limit N` can only LOWER the bar, never raise it

The fixtures need a file this gate REFUSES, and the honest one is 150,001 bytes
— a blob that size in the fixture tree is its own problem. `--limit N` solves
that, and it is constrained so it cannot become the hole: a value ABOVE
`LIMIT_BYTES` is refused with exit 2, not honoured. So the flag can tighten the
gate and can never weaken it, which keeps "DO NOT RAISE THE LIMIT" a property of
the code rather than a sentence in this docstring.

The trade is stated rather than hidden: the fixtures then exercise the
COMPARISON and the exit codes against a small limit, and not the 150,000
constant itself. `tests/unit/test_claude_md_size_gate.py` pins that constant
separately, because a constant is the one thing a negative control cannot prove.

Usage:  python apps/api/scripts/check_claude_md_size.py
            [--limit N] [--require-canary] [PATH ...]
        (default: CLAUDE.md at the repo root)
"""

from __future__ import annotations

import sys
from pathlib import Path

#: The reader limit measured on 2026-09-22. See the docstring: this is an
#: observed cliff, not a preference, and it is in BYTES.
LIMIT_BYTES = 150_000

#: A SOFT line, warned about and NOT failed on. It exists because a gate that
#: fires with no prepared remedy reads as the gate being broken, while one that
#: fires early and names the next cut is a ratchet. `CLAUDE.md` carries the
#: named candidate list under "Where the next 15,000 bytes come from"; this
#: constant is what tells you to go read it, with room still left to act.
SOFT_LIMIT_BYTES = 135_000

#: The marker that must be the LAST non-empty line of a canary-bearing file.
#: A reader that cannot see it has been truncated and is told to stop.
CANARY = "<!-- CLAUDE-MD-CANARY: v1 -->"

#: The budget `CLAUDE.md` sets for itself, reported but NOT enforced. Enforcing
#: it today would put the repo permanently red, which teaches everyone to route
#: around the gate -- the failure mode `check_plan_totals` already recorded when
#: the cheapest route to green was to edit the total.
SELF_IMPOSED_LINE_BUDGET = 600

DEFAULT_TARGETS = ["CLAUDE.md"]


def repo_root(start: Path | None = None) -> Path:
    """The repo root, found by searching UPWARD for a marker.

    `parents[N]` is wrong here for the same reason `_common.py` records: this
    script runs from the host checkout (three parents to the root) and from the
    api container, which mounts `./apps/api` at `/app`. Searching for the marker
    works in both and raises rather than guessing.

    Takes `start` so BOTH directions are testable -- the find and the raise. A
    guard observed only in the state that fires is not a guard that has been
    checked.
    """
    here = (start or Path(__file__)).resolve()
    for candidate in here.parents:
        if (candidate / ".github").is_dir() and (candidate / "apps").is_dir():
            return candidate
    raise RuntimeError(
        f"cannot locate a repo root with `.github/` and `apps/` above {here}. "
        "Pass an explicit path instead of relying on discovery."
    )


def measure(path: Path) -> tuple[int, int, int]:
    """Return `(bytes, characters, lines)` for `path`.

    Bytes come from the raw read, characters from decoding it, lines from
    counting newlines in the decoded text. Reading once and deriving all three
    keeps them describing the same read -- three separate reads could disagree
    if the file changed underneath, and disagreeing numbers in one report are
    worse than one number.
    """
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    return len(raw), len(text), text.count("\n") + (1 if text and not text.endswith("\n") else 0)


def _fmt(n: int) -> str:
    return f"{n:,}"


def main(argv: list[str]) -> int:
    args = argv[1:]
    limit = LIMIT_BYTES
    require_canary = False
    rest: list[str] = []

    # `--limit` is the ONLY option. Everything else is a could-not-look: five
    # gates in this repo ignored `argv[2:]` entirely, so a typo'd flag was
    # silently dropped and the gate reported on its default target while the
    # caller believed it had been redirected (#343).
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--limit":
            if i + 1 >= len(args):
                print("check-claude-md-size: --limit needs a value")
                return 2
            raw = args[i + 1]
            if not raw.isdigit():
                print(f"check-claude-md-size: --limit wants a whole number, got {raw!r}")
                return 2
            limit = int(raw)
            i += 2
            continue
        if a == "--require-canary":
            require_canary = True
            i += 1
            continue
        if a.startswith("-"):
            print(f"check-claude-md-size: unknown option: {a}")
            print(
                "check-claude-md-size: this gate takes `--limit N`, "
                "`--require-canary` and file paths."
            )
            return 2
        rest.append(a)
        i += 1

    # The flag may TIGHTEN the bar and may never loosen it. Without this the
    # option is the hole: anyone hitting the gate could pass the number that
    # makes their file legal, and the docstring's "do not raise the limit"
    # would be advice rather than a property.
    if limit > LIMIT_BYTES:
        print(
            f"check-claude-md-size: --limit {limit} is ABOVE the measured reader "
            f"limit of {LIMIT_BYTES}."
        )
        print("check-claude-md-size: this flag may only lower the bar, never raise it.")
        print("Raising it does not make the reader read more; it only silences this gate.")
        return 2

    explicit = rest

    if explicit:
        targets = [Path(a) for a in explicit]
    else:
        try:
            root = repo_root()
        except RuntimeError as exc:
            print(f"check-claude-md-size: {exc}")
            return 2
        targets = [root / name for name in DEFAULT_TARGETS]

    findings: list[tuple[Path, int, int, int]] = []
    checked: list[tuple[Path, int, int, int]] = []

    for target in targets:
        if not target.exists():
            print(f"check-claude-md-size: target does not exist: {target}")
            return 2
        if target.is_dir():
            print(f"check-claude-md-size: target is a directory, not a file: {target}")
            return 2
        try:
            size, chars, lines = measure(target)
        except (OSError, UnicodeDecodeError) as exc:
            print(f"check-claude-md-size: cannot read {target}: {type(exc).__name__}: {exc}")
            return 2
        checked.append((target, size, chars, lines))
        if size > limit:
            findings.append((target, size, chars, lines))

        # The canary is a SEPARATE proposition from the size, and it fails
        # closed on its own. A file can be comfortably under the limit and
        # still have had the marker pushed out of last place by an append,
        # which silently restores the failure the marker exists to announce.
        if require_canary:
            raw_lines = target.read_text(encoding="utf-8").splitlines()
            tail = [ln for ln in raw_lines if ln.strip()]
            if not tail:
                print(f"check-claude-md-size: {target} is empty, so it carries no canary.")
                return 2
            if CANARY not in tail:
                print(f"check-claude-md-size: {target} has NO canary marker.")
                print(f"  expected the last non-empty line to be: {CANARY}")
                print("  A reader cannot tell a truncated copy from a whole one without it.")
                return 2
            if tail[-1] != CANARY:
                print(f"check-claude-md-size: {target}'s canary is NOT the last line.")
                print(f"  last non-empty line is: {tail[-1][:70]}")
                print("  Something was appended past the marker, so a reader can see the")
                print("  canary and still be missing everything after it. Move the marker")
                print("  back to the end, or move the new content above it.")
                return 2

    if not findings:
        for target, size, chars, lines in checked:
            head = _fmt(limit - size)
            print(
                f"check-claude-md-size: {target.name} is {_fmt(size)} bytes "
                f"({_fmt(chars)} chars, {_fmt(lines)} lines) -- {head} bytes of headroom."
            )
            if size > SOFT_LIMIT_BYTES:
                print(
                    f"  SOFT LINE PASSED: {_fmt(size - SOFT_LIMIT_BYTES)} bytes over "
                    f"{_fmt(SOFT_LIMIT_BYTES)}. This is a WARNING, not a failure."
                )
                print('  Read "Where the next 15,000 bytes come from" in CLAUDE.md and take')
                print("  the next candidate. The list is there so the alarm arrives with a")
                print("  remedy already chosen, rather than as an obstruction.")
            if lines > SELF_IMPOSED_LINE_BUDGET:
                over = _fmt(lines - SELF_IMPOSED_LINE_BUDGET)
                print(
                    f"  NOTE, not enforced: {over} lines over the "
                    f"{SELF_IMPOSED_LINE_BUDGET}-line budget the file sets itself."
                )
        return 0

    print("check-claude-md-size: a governance file is large enough to be TRUNCATED")
    print()
    for target, size, chars, lines in findings:
        print(f"  {target}: {_fmt(size)} bytes ({_fmt(chars)} chars, {_fmt(lines)} lines)")
        print(
            f"      {_fmt(size - limit)} bytes past the {_fmt(limit)}-byte "
            f"reader limit -- that tail is cut before any agent reads it."
        )
    print()
    print("Everything past the limit is removed SILENTLY. There is no error, no")
    print("marker, and no way for a reader to tell a rule was dropped -- which is")
    print("how the merge rule's condition-5 path list went unreadable for days")
    print("while eleven gates stayed green.")
    print()
    print("Fix it the way the file's own ratchet says, in preference order:")
    print()
    print("  1. MOVE THE RECORD, KEEP THE RULE. `CLAUDE.md` is INSTRUCTIONS and")
    print("     `DECISIONS.md` is the RECORD. Most length here is postmortem")
    print("     narrative -- why a rule exists, what it caught, which PR found")
    print("     it. Move the story under a D-number and cite it in one line.")
    print()
    print("  2. PUT THE CONSEQUENTIAL RULES FIRST. A partial read still reaches")
    print("     the top of the file, so what a truncated reader loses is decided")
    print("     by ORDER. The merge rule belongs near the top for that reason")
    print("     alone.")
    print()
    print("  3. DO NOT RAISE THE LIMIT. It is a measured property of a reader,")
    print("     not a budget anyone chose. Raising it does not make the reader")
    print("     read more; it only stops this gate saying so.")
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
        sys.stderr.write(f"check-claude-md-size: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(2) from exc
