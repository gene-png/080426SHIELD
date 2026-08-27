#!/usr/bin/env python
"""Reject stray control characters in the repo's text files.

WHY THIS EXISTS. `\b` written into a non-raw Python string is a BACKSPACE byte,
and `\v`, `\f`, `\x1c`-`\x1e` and `\u2028` are equally invisible once
interpolated. Editing prose ABOUT regexes -- which this repo does constantly,
because its decision records quote the patterns they decide -- produces them
silently: the file still parses, prettier still passes, the diff looks right, and
DECISIONS.md ends up with an empty code span and an invisible control byte inside
a sentence explaining a word boundary.

That happened FOUR times on one branch. Twice in text written earlier; once in
the FIX for those two, by someone who had just read both and knew exactly what
the shape was; and once in the CI step that wires up this very gate, in the
sentence explaining what the defect is. The fourth was caught by this script on
its first run, which is the entire argument for it existing. CLAUDE.md's standing
line applies -- knowing the shape does not prevent producing it, only checking
does. This file is itself pure ASCII, and an earlier draft of it was not: it
carried a literal U+2028 inside its own error message.

U+2028/U+2029 matter beyond tidiness: they are line separators, so a markdown
renderer and a text editor disagree about how many lines the file has.

WHY NOT `str.isascii()`, WHICH IS THE OBVIOUS SPELLING. Because it is a
different check wearing this one's clothes, and it REJECTS THINGS THAT ARE
CORRECT. Run it over this repo and `app/models/llm_call.py` comes back False on
three characters -- two section signs in `Master Spec §11` and one em dash --
all of them legitimate typography, none of them a defect, all of them in text
nobody should be asked to rewrite. The gate would then fire on the em dash
inside the sentence explaining what the gate is for, which is the same joke this
file's own history already tells twice.

The distinction is not "ASCII vs not". It is "does this byte RENDER". `§` and
`—` render and carry meaning; U+0008 and U+2028 do not render and change what the
file means. So the rule is an explicit deny list of non-rendering characters,
never an allow list of ASCII -- and the list has to be maintained by hand, which
is the cost of getting it right.

Recorded because the over-broad version was tried and rejected during the
2026-08-25 slice, and a rejection that is not written down gets re-derived by
the next person at the same price. Same shape as the prose-total rule refused at
7.7% signal and the first separator-class draft: the cheap check is the one that
cries wolf, and a gate that cries wolf gets switched off.

EXIT CODES, per this repo's fail-closed convention (D-051):
  0 - clean
  1 - at least one stray control character found
  2 - could not read the tree (an unreadable input is NOT a pass)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Tab and newline are legitimate. Everything else below U+0020, plus the
# non-ASCII characters that behave as control or line-break characters.
_FORBIDDEN = {chr(c) for c in range(0x20)} - {"\t", "\n"}
_FORBIDDEN |= {"\x7f", "\x85", "\u2028", "\u2029", "\ufeff"}

_TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".yml", ".yaml", ".ts", ".tsx", ".js", ".jsx"}

# Skipped WHEREVER they appear. Every name here is unambiguous: no source tree in
# this repo has a directory called `node_modules` or `__pycache__` that holds
# code we wrote.
_SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    ".next",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
}

# Skipped only at these exact paths, because the NAME is ambiguous in this repo.
# `artifacts` is the trap: `e2e/artifacts` is Playwright output, and
# `apps/web/src/app/api/proxy/artifacts` is a real Next.js route. A name-based
# skip silently excluded two tracked TypeScript files -- an unstated exemption
# that makes the gate quietly narrower than it claims.
#
# CLAUDE.md already records this exact collision for `coverage/`, which the
# repo-wide gitignore swallowed and which needed a negation for
# `apps/web/src/app/api/proxy/attack/coverage/`. Same trap, same repo, and this
# script walked into it anyway -- so anchor the ambiguous ones to a path.
_SKIP_PATHS = {
    Path("e2e/artifacts"),
    Path("e2e/test-results"),
    Path("e2e/playwright-report"),
    Path("test-results"),
    Path("playwright-report"),
}


def _candidate_files(root: Path) -> list[Path]:
    if not root.is_dir():
        print(f"check-control-chars: not a directory: {root}")
        raise SystemExit(2)
    out: list[Path] = []
    # os.walk with in-place pruning rather than rglob: rglob descends into
    # node_modules before anything can filter it out, and a Windows symlink in
    # there raises WinError 1920 from is_file(). Prune the directory, never the
    # result.
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath).relative_to(root)
        dirnames[:] = [
            d for d in dirnames if d not in _SKIP_DIR_NAMES and (here / d) not in _SKIP_PATHS
        ]
        for name in filenames:
            if Path(name).suffix in _TEXT_SUFFIXES:
                out.append(Path(dirpath) / name)
    if not out:
        # An empty listing supports neither reading. Fail closed rather than
        # printing an encouraging sentence over input we could not read.
        print(f"check-control-chars: found no text files under {root}")
        raise SystemExit(2)
    return out


def main(argv: list[str]) -> int:
    """Always RETURNS the exit code; never raises SystemExit itself.

    So a caller -- including the unit tests -- gets 0/1/2 uniformly rather than
    having to catch an exception for one of the three outcomes. `_candidate_files`
    still raises for the unreadable-tree case; it is caught here.
    """
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd()
    violations: list[str] = []
    unreadable: list[str] = []
    try:
        files = _candidate_files(root)
    except SystemExit as exc:
        return int(exc.code or 2)
    checked = 0
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            # read_bytes + decode, NOT read_text: read_text opens with
            # newline=None, so universal-newline translation rewrites every
            # `\r` to `\n` before the scan and the `\r` entry in _FORBIDDEN can
            # never fire. A lone old-Mac `\r` is exactly the splitlines-vs-editor
            # disagreement this script argues about, so it has to survive to here.
            raw = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # NOT "not this check's business". A file saved UTF-16 or Latin-1 by
            # a Windows editor is one of the ways a raw 0x85 gets in, so an
            # undecodable file is precisely this check's business. Counting it as
            # scanned would print an encouraging sentence over input we could not
            # read -- the defect CLAUDE.md records for check_audit_evidence.py.
            unreadable.append(f"{rel}: {type(exc).__name__}")
            continue
        checked += 1
        # CRLF is a line ending, not a stray control character, and whether the
        # working tree has it depends on core.autocrlf -- so flagging it would
        # make this gate behave differently on Windows and in CI. Normalise it
        # away first; a LONE `\r` (old-Mac line ending) survives that and is
        # exactly the splitlines-vs-editor disagreement worth catching.
        text = raw.replace("\r\n", "\n")
        for lineno, line in enumerate(text.split("\n"), start=1):
            found = sorted({f"U+{ord(c):04X}" for c in line if c in _FORBIDDEN})
            if found:
                rel = path.relative_to(root).as_posix()
                violations.append(f"{rel}:{lineno}: {', '.join(found)}")

    if unreadable:
        print("check-control-chars: could not read these as UTF-8 text")
        print()
        for u in unreadable:
            print(f"  {u}")
        print()
        print("An undecodable file is not a pass. Convert it to UTF-8, or add its")
        print("directory to _SKIP_DIR_NAMES / _SKIP_PATHS if it is genuinely not source.")
        return 2

    if violations:
        print("check-control-chars: stray control characters found")
        print()
        for v in violations:
            print(f"  {v}")
        print()
        print("These are almost always an escape sequence written into a non-raw")
        print(r"string: `\b` -> BACKSPACE, `\v` -> VT, `\u2028` -> LINE SEPARATOR.")
        print("Write the escape as literal text, or build it with chr(92).")
        return 1

    print(f"check-control-chars: clean ({checked} files)")
    return 0


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
        sys.stderr.write(f"check-control-chars: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(2) from exc
