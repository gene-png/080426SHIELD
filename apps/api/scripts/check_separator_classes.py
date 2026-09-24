#!/usr/bin/env python
"""Reject an enumerated whitespace class in the redactor.

WHY THIS IS A CHECK AND NOT A PARAGRAPH. `app/ai/redact.py` is the single LLM
egress path. Twice now, a separator class in it has been written by listing the
whitespace characters someone could think of, and both times it leaked:

  * D-058: `[ \\t\\xa0]` -- "space, tab, non-breaking space, surely that is all of
    them". Python's `\\s` matches 19 horizontal characters, so the list silently
    dropped SIXTEEN. A street address separated by a narrow-no-break space, which
    is what PDF and Word extraction emit, egressed verbatim with an empty
    `removed_counts`.
  * Item 10: `_PHONE_SEP = [ .\\-]` -- ASCII space only. Same defect, same file,
    **190 lines above the comment explaining the first one**, written by someone
    who had just read it.

The second instance is the argument. This shape demonstrably does not respond to
documentation, and unlike the prose-staleness rule it has a precise signature:

    a character class in redact.py that contains a literal space
    but neither `\\s` nor `_HSPACE`

Measured over the file: that hits `_PHONE_SEP` (the defect) and nothing else --
`[\\s:#.,-]`, `[A-Za-z0-9\\-]`, `[\\d.\\-/]` and the rest all pass. Signal is
effectively 1:1, against the 12.2% at which `check_test_integrity`'s TI001 was
narrowed and the 7.7% at which a prose-total gate was refused outright. It would
also have caught D-058's original class.

Scoped to `app/ai/redact.py` deliberately, and the scope is the rule rather than
a shortcut. Elsewhere a literal-space class is ordinary; here it is a security
boundary where the cost of missing a separator is a silent leak. `scripts/` and
`alembic/versions/` are NOT scanned because neither performs redaction --
scanning them would apply a rule to code it does not govern and buy false
positives on ordinary character classes. If redaction ever moves or is copied out
of this file, this target moves with it.

WHAT IT CANNOT CATCH, stated so a clean run is not read as more than it is:

  * A class built by CONCATENATION. `_PHONE_SEP = "(?:" + _HSPACE + "|[ .-])"`
    passes -- the literal-space class on that line sits beside `_HSPACE`, and the
    exemption is line-scoped. The signature is textual and always will be.
  * A separator defined outside this file and imported into it.
  * A class that is correctly enumerated today and silently wrong after Unicode
    adds a horizontal space. Only deriving from `\\s` survives that.
  * Whether the redactor HONOURS the mode it was handed -- that is behaviour, and
    no static gate sees it.

EXIT CODES, per this repo's fail-closed convention (D-051):
  0 - no enumerated whitespace class
  1 - at least one found
  2 - could not read the file (an unreadable input is NOT a pass)
"""

from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

_DEFAULT_TARGET = Path("apps/api/app/ai/redact.py")

# A character class: `[` ... `]`, not escaped, no nested `]`.
_CHAR_CLASS = re.compile(r"(?<!\\)\[\^?((?:[^]\\]|\\.)*)\]")

# The ONE function allowed to turn data into a pattern (#535).
_CONSTRUCTOR = "_literal_pattern"

# Written on the line or the line above, with a reason. An empty marker is not a
# reason -- same convention as `check_test_integrity`'s `# test-integrity:`.
_ALLOW = re.compile(r"#\s*separator-class:\s*(\S.*)")


def check(source: str) -> tuple[int, list[str]]:
    """Scan only STRING LITERALS, via tokenize.

    An earlier draft scanned every `[...]` on every line and reported twelve
    findings on this file -- all of them Python: list literals (`["strict",
    "standard", "off"]`), type annotations (`tuple[str, int]`), and
    comprehensions. Claimed signal 1:1, measured signal 1 in 13.

    That is the same ratio at which the prose-total gate was refused, produced
    the same way: by reasoning about the shape instead of running it over the
    file. Tokenizing removes the whole class -- a type annotation is not a string
    -- and takes the count back to zero false positives.
    """
    findings: list[str] = []
    lines = source.split("\n")
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
        return 2, [f"cannot tokenize: {type(exc).__name__}: {exc}"]

    for tok in tokens:
        if tok.type != tokenize.STRING:
            continue
        for match in _CHAR_CLASS.finditer(tok.string):
            body = match.group(1)
            if " " not in body:
                continue
            if r"\s" in body:
                continue
            lineno = tok.start[0]
            line = lines[lineno - 1] if lineno <= len(lines) else ""
            above = lines[lineno - 2] if lineno >= 2 else ""
            marked = _ALLOW.search(line) or _ALLOW.search(above)
            if marked:
                continue
            # `_HSPACE` is composed OUTSIDE the string literal, so the gate can
            # only see it on the source LINE -- which means the exemption cannot
            # tell whether THIS class is the one alternated with it. It used to
            # `continue` here, silently excusing every class on any line that
            # mentioned `_HSPACE` anywhere.
            #
            # Tightening the adjacency test does not work: the legitimate form
            # `r"(?:" + _HSPACE + r"|[ .-])"` puts a raw-string prefix between
            # the two, so any proximity rule either admits unrelated classes or
            # rejects the real one. The signature is textual and cannot parse
            # the expression.
            #
            # So the exemption is DOCUMENTED rather than silent: say why.
            if "_HSPACE" in line:
                findings.append(
                    f"line {lineno}: [{body}] lists a literal space on a line "
                    "that also references `_HSPACE`. If the class really is "
                    "alternated with it, the space is redundant -- drop it, or "
                    "say why with `# separator-class: <reason>`. This exemption "
                    "used to be silent and unbounded."
                )
                continue
            findings.append(
                f"line {lineno}: [{body}] lists a literal space without "
                + r"`\s`"
                + " or `_HSPACE`"
            )

    findings.extend(_data_escapes_outside_the_constructor(source))
    if findings:
        return 1, findings
    return 0, []


def _data_escapes_outside_the_constructor(source: str) -> list[str]:
    """The SECOND signature: a separator the code RECEIVES rather than writes.

    The class-literal scan above protects separators written in source. #535's
    space arrived from the DATABASE -- a stored legal name -- and `re.escape`
    turned it into a literal U+0020, so a no-break space between the words
    never matched and the client's name egressed with `counts == {}`. No class
    ever appeared in source, so the scan above could not see it: the third
    instance of the shape it exists to stop, after D-058 and item 10.

    The separator lives in data, but the place data BECOMES a pattern is
    source, and it is precise: `re.escape`. So data may become a pattern in
    exactly one function, `_literal_pattern`, which joins the needle's tokens
    with `_HSPACE+` and anchors conditionally. Any other call is a finding.

    Resolved by the AST, not by text, so a docstring or comment that MENTIONS
    `re.escape(` is not a call, and `from re import escape` or `import re as r`
    are still caught. WHAT IT CANNOT SEE: data interpolated into a pattern
    WITHOUT `re.escape` (an f-string of a raw variable) -- a regex injection,
    a different and worse defect, which this file does not do today -- and
    `getattr(re, "escape")`.

    Only called after the tokenize pass succeeded, so the source parses as far
    as tokenize reaches; a SyntaxError here is still reported, never swallowed.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"cannot parse for the re.escape check: {exc}"]

    re_aliases = {"re"}
    escape_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "re":
                    re_aliases.add(alias.asname or "re")
        elif isinstance(node, ast.ImportFrom) and node.module == "re":
            for alias in node.names:
                if alias.name == "escape":
                    escape_names.add(alias.asname or "escape")

    def is_escape_call(call: ast.Call) -> bool:
        f = call.func
        if isinstance(f, ast.Attribute) and f.attr == "escape":
            return isinstance(f.value, ast.Name) and f.value.id in re_aliases
        return isinstance(f, ast.Name) and f.id in escape_names

    findings: list[str] = []

    def visit(node: ast.AST, enclosing: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            name = enclosing
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = child.name
            if isinstance(child, ast.Call) and is_escape_call(child) and name != _CONSTRUCTOR:
                where = f"in `{name}`" if name else "at module level"
                findings.append(
                    f"line {child.lineno}: `re.escape` {where} turns DATA into a pattern "
                    f"outside `{_CONSTRUCTOR}` -- a separator in that data is matched "
                    "as a literal U+0020 (#535). Build the pattern with "
                    f"`{_CONSTRUCTOR}` instead."
                )
            visit(child, name)

    visit(tree, None)
    return findings


def main(argv: list[str]) -> int:
    # AN ARGUMENT THIS SCRIPT DOES NOT IMPLEMENT MUST NOT SUCCEED, and the
    # live slot is the SECOND one.
    #
    # This read `argv[1]` and ignored `argv[2:]` entirely. A leading unknown
    # flag was already caught by accident -- it resolves as a path and the path
    # does not exist -- but `ci.yml` PASSES A PATH to this gate, so the first
    # slot is occupied in exactly the invocation that matters and anything
    # after it was dropped in silence. `<gate> <path> --dry-run` ran a real
    # check and exited on its own verdict, reading as though the flag had done
    # something.
    #
    # A sweep recorded the opposite: "MEASURED, not assumed ... they already
    # fail closed on an unknown flag, because they read it as a path and the
    # path does not exist. Checked and left alone." True of a LEADING flag,
    # false of a trailing one, in the sentence whose words closed the question.
    if len(argv) > 2:
        print(
            f"check-separator-classes: could not look -- too many arguments; got: {argv[1:]}. "
            f"This script takes at most one PATH and implements no flags.",
            file=sys.stderr,
        )
        return 2
    if len(argv) > 1 and argv[1].startswith("-"):
        print(
            f"check-separator-classes: could not look -- {argv[1]!r} is a flag, and this script "
            f"implements none. It takes an optional PATH and nothing else.",
            file=sys.stderr,
        )
        return 2
    target = Path(argv[1]) if len(argv) > 1 else _DEFAULT_TARGET
    try:
        source = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"check-separator-classes: cannot read {target}: {type(exc).__name__}")
        return 2
    if not source.strip():
        print(f"check-separator-classes: {target} is empty")
        return 2

    code, findings = check(source)
    if code == 2:
        # "I could not look" must not share a branch with "I found a violation",
        # and it must not share one with "nothing to complain about" either.
        # This gate cited D-051 while collapsing its own 2 into a 1 -- the exit
        # code the docstring promises was unreachable through main().
        print(f"check-separator-classes: cannot parse {target}")
        for finding in findings:
            print(f"  {finding}")
        print("An unreadable input is NOT a pass and NOT a violation (D-051).")
        return 2
    if code == 0:
        print(f"check-separator-classes: clean ({target})")
        return 0

    # Two signatures, two causes, and a guard's message names the CAUSE.
    written = [f for f in findings if "re.escape" not in f]
    received = [f for f in findings if "re.escape" in f]
    print("check-separator-classes: separator defect in the egress path")
    print()
    for finding in findings:
        print(f"  {target}:{finding}")
    if written:
        print()
        print("A SEPARATOR THE CODE WRITES: `\\s` matches 19 horizontal whitespace")
        print("characters. A hand-written list drops the ones nobody pictures -- thin,")
        print("narrow-no-break, ideographic -- and those are exactly what PDF and Word")
        print("extraction emit. Build the class from `_HSPACE` (which is `\\s` minus the")
        print("line breaks), or, if the literal space really is intended, say why:")
        print()
        print('    _FOO = r"[ .-]"  # separator-class: ASCII-only on purpose because <reason>')
    if received:
        print()
        print("A SEPARATOR THE CODE RECEIVES: `re.escape` turns the space in stored")
        print("data (a legal name, a user's display name) into a literal U+0020, so the")
        print("same words joined by a no-break space never match (#535). Build the")
        print(f"pattern with `{_CONSTRUCTOR}`, the one function allowed to do this.")
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
        sys.stderr.write(f"check-separator-classes: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(2) from exc
