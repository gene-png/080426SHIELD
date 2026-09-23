#!/usr/bin/env python3
"""Compute merge-rule condition 4 from the diff, and refuse a PR body that does
not declare it.

`CLAUDE.md`'s merge rule says an agent merges unattended only when six
conditions hold, and that "any PR tripping 4, 5 or 6 comes back to the human".
Condition 4 -- "No migration" -- is a path question with an exact answer, and it
was answered from memory by whoever wanted to merge.

## THIS GATE COVERED CONDITION 5 TOO, AND THAT HALF WAS WITHDRAWN

Worth stating first, because the withdrawal is the decision and the remaining
code is the easy part.

Adversarial review found the condition-5 derivation could not see a PR whose
only change is `scripts/web-install-if-stale.sh` -- the web install guard, which
`CLAUDE.md` names as a reason `docker-compose.yml` is a condition-5 path, which
decides whether a lockfile security bump reaches the running container (#226),
and which `tests/gates/web_install_guard.sh` gates. It hid three ways at once:
the derivation opened only `.github/workflows/`, the invocation verb is `sh`
rather than `bash|python`, and the operand is the container path
`/app/web-install-if-stale.sh`, carrying none of the markers the pattern sought.

**That was a regression against a fix this repo had already made.**
`check_gate_fixtures.py::invocation_text` takes compose files as `extra`
precisely because reading only the workflows directory was, in its own words,
"a live FALSE POSITIVE, not a latent one". This gate read the narrower surface
the sibling gate was corrected away from.

Widening the derivation is a different design rather than a patch -- the surface
is compose files, `tests/gates/*.sh` driving other scripts, and any future
invocation spelling -- so it is filed rather than bolted on.

## AND THE ACKNOWLEDGMENT MATCHER COULD NOT TELL AN ACKNOWLEDGMENT FROM A DENIAL

The first version matched a bare digit inside a `## Merge rule` section. Three
ways that passes a body acknowledging nothing:

  * `## Merge rule` + "This does not trip condition 5." -- the negation is
    invisible to the matcher. That is `CLAUDE.md`'s closing-keyword defect,
    rebuilt inside the gate whose subject is honesty.
  * `.github/pull_request_template.md` has no `## Merge rule` heading, so the
    region fell back to the WHOLE body -- and the template's own commented
    example reads `Scope -> the 4 files in this diff`. Every author who left the
    comment block in place acknowledged condition 4 for free.
  * A sha, a version, an ordered-list item, or a changed path with an isolated
    digit: `a3137d5`, `prettier@3.9.5`, `e2e/smoke/s5-login.spec.ts`.

**So the acknowledgment is an explicit MARKER, not a digit.** The template does
not contain it, and a denial IN PROSE cannot produce it:

    Merge-rule-condition-4: <what the migration does>

Same shape as `Auto-close-approved:`, and for the same reason: that gate learned
that a matcher looking for a number beside a word is defeated by the most natural
honest phrasing, and a positive token is not.

**A denial in MARKER form is a different matter, and the first version of this
paragraph claimed it was impossible.** `Merge-rule-condition-4: n/a` matched, the
reason was non-empty, exit 0. That is refused now by `_NOT_A_REASON`, which is a
DENYLIST and is named as one: it is a floor over the phrasings someone reaches for
when they have nothing to declare, not a proof that a denial cannot be written.
The honest claim is that the marker makes a denial DELIBERATE rather than
accidental -- the template no longer supplies one, and neither does a stray digit,
a sha or a quoted merge rule.

## What this enforces, and what it deliberately does not

It does NOT refuse a PR for carrying a migration. The enforced property is that
the PR SAYS SO. The failure it closes is a body reading "trips nothing" over a
diff that adds a revision -- which is the failure that actually happened, and one
that re-reading the path list does not prevent.

Conditions 5 and 6 are NOT computed, and saying so is the point. Condition 6 is a
judgement about what a change MEANS; a path match cannot decide it. Condition 5
is mechanisable in principle and is not mechanised here. The merge rule already
calls 2, 3 and 6 self-attested; this leaves 5 exactly as self-attested as it was,
rather than pretending a partial glob decided it.

## Silent-success branches, enumerated before the first line

Exits 0 only for: a changed-file list containing no migration, or one containing
a migration whose marker the body carries with a reason that is non-empty, not a
`<placeholder>`, and not in `_NOT_A_REASON`. Everything else is 1 (the body
understates) or 2 (could not look) -- an empty changed-file list, an unreadable
input, an unknown flag, a missing argument. The empty list is the one that would
otherwise read as "no migration", which is `check_audit_evidence.py`'s
`is_code_change([])` shape.

The marker is searched for in the body with HTML comments and fenced code blocks
REMOVED, so a marker inside either does not count -- the hazard the PR template
records for the sibling gate. A blockquoted marker was already excluded by the
`^[ \t]*` anchor.
"""

from __future__ import annotations

import re
import sys
from fnmatch import fnmatch
from pathlib import Path

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_COULD_NOT_LOOK = 2

#: Condition 4. A revision under `alembic/versions/`.
#:
#: `alembic/env.py` is NOT here. The merge rule puts it under condition 5 in as
#: many words, because changing it alters stored behaviour without adding a
#: revision -- and condition 5 is not computed by this gate, so `env.py` is
#: unenforced here. Stated rather than left for a reader to discover.
MIGRATION_GLOBS = ("apps/api/alembic/versions/*.py",)

#: The declaration the body must carry.
#:
#: A POSITIVE TOKEN, because the thing it replaced -- a bare digit near the word
#: "condition" -- was satisfied by "This does not trip condition 4." and by the
#: PR template's own boilerplate, which puts the digit in every body in the repo.
#:
#: The COLON is required, so `Merge-rule-condition-4` appearing in prose ("I read
#: the Merge-rule-condition-4 rule and it does not apply") does not satisfy it.
#: **AT MOST THREE LEADING SPACES, AND NO TAB.** That is markdown's own rule for
#: what is NOT an indented code block, and this pattern was `[ \t]*` -- so
#:
#:     Merge-rule-condition-4: adds a column
#:
#: matched at exit 0 while RENDERING to a reviewer as a code sample, which is
#: exactly the hazard the fence stripping below exists to close. Markdown has two
#: code-block syntaxes and the first fix handled one of them.
#:
#: TWO COMMENTS TWO SCREENS APART WERE IN DIRECT CONFLICT AND NEITHER NOTICED.
#: `[ \t]*` was chosen deliberately and documented as the reason a blockquote
#: cannot match -- `>` is not whitespace, so the anchor excludes it. That same
#: tolerance is what let an indented code block through. The blockquote property
#: survives this narrowing and is still asserted by its own test.
_MARKER = re.compile(
    r"^ {0,3}merge-rule-condition-4[ \t]*:[ \t]*(?P<why>.+?)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)

#: An HTML comment block, and a fenced code block.
#:
#: BOTH ARE STRIPPED BEFORE THE MARKER IS SEARCHED FOR, and the first version did
#: neither. `.github/pull_request_template.md` states the repo's own view of this
#: hazard for the SIBLING gate: "this checker does not strip HTML comments --
#: restore the colon and every PR passes having recorded nothing, in a body that
#: renders no audit block at all." The new gate reproduced it.
#:
#: A blockquote needs no handling: `_MARKER` anchors on `^[ \t]*`, so
#: `> Merge-rule-condition-4: x` already does not match. Checked rather than
#: assumed.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CODE_FENCE = re.compile(r"^[ \t]*```.*?^[ \t]*```", re.DOTALL | re.MULTILINE)

#: Reasons that are the ABSENCE of a reason wearing the marker's syntax.
#:
#: A DENYLIST, and named as one rather than described as an allow-list -- this
#: file has already paid for that confusion once. It is a FLOOR: it catches the
#: phrasings someone reaches for when they have nothing to declare, and it cannot
#: catch every one. What it is not is a claim that a denial is impossible.
#:
#: THE PROSE SAID "a denial cannot produce it" IN THREE PLACES and that was false:
#: `Merge-rule-condition-4: n/a` matched, `why` was non-empty, exit 0. The
#: original denial test covered only the PROSE form ("This does not trip condition
#: 4."), so the marker-shaped denial was untested. Refusing "" and accepting "n/a"
#: is the same ritual-satisfaction outcome one character away.
_NOT_A_REASON = frozenset(
    {
        "n/a",
        "na",
        "none",
        "no",
        "nil",
        "nothing",
        "-",
        "--",
        "tbd",
        "todo",
        "x",
        # THE PHRASES THE ABBREVIATIONS ABBREVIATE. The first version held `n/a`
        # and `na` and not `not applicable` -- a floor that blocked the short
        # form and passed the long one, one word short of its own examples.
        "not applicable",
        "no migration",
        "no migration in this pr",
        "does not apply",
        "not a migration",
        "n/a - no migration",
    }
)


def _declaration_region(body: str) -> str:
    """The body with HTML comments and fenced code removed."""
    return _CODE_FENCE.sub("", _HTML_COMMENT.sub("", body))


def condition_4(changed: list[str]) -> list[str]:
    """Changed paths that are alembic revisions."""
    return sorted(p for p in changed if any(fnmatch(p, g) for g in MIGRATION_GLOBS))


def declares_migration(body: str) -> str | None:
    """The reason on the marker line, or None when there is no usable marker.

    Returns the REASON rather than a bool so an empty one can be refused.
    `CLAUDE.md`: an empty reason is not a reason -- the rule
    `check_test_integrity` applies to `# test-integrity:`.
    """
    for match in _MARKER.finditer(_declaration_region(body)):
        why = match.group("why").strip()
        if not why:
            continue
        # A PLACEHOLDER, and the gate's own failure message is where it comes
        # from: that message prints `Merge-rule-condition-4: <what the migration
        # does>`, and `_MARKER` allows leading whitespace, so pasting the CI
        # output into the body -- or copying the suggested line without filling
        # it in -- satisfied the gate. The template-boilerplate defect this
        # narrowing was built to close, rebuilt out of its own instruction text.
        if why.startswith("<") and why.endswith(">"):
            continue
        if why.lower().strip(".") in _NOT_A_REASON:
            continue
        return why
    return None


def _usage(stream) -> None:
    print(
        "  Usage: check_merge_rule_conditions.py --changed-files <file> --body <file>",
        file=stream,
    )


def main(argv: list[str]) -> int:
    changed_path: str | None = None
    body_path: str | None = None
    args = argv[1:]
    index = 0
    while index < len(args):
        if args[index] == "--changed-files" and index + 1 < len(args):
            changed_path = args[index + 1]
            index += 2
        elif args[index] == "--body" and index + 1 < len(args):
            body_path = args[index + 1]
            index += 2
        else:
            print(
                f"check-merge-rule-conditions: unknown argument {args[index]!r}.",
                file=sys.stderr,
            )
            _usage(sys.stderr)
            print(
                "  Refusing to report on input it could not parse -- an ignored\n"
                "  flag is how a gate reports clean having read nothing (#343).",
                file=sys.stderr,
            )
            return EXIT_COULD_NOT_LOOK

    if not changed_path or not body_path:
        print(
            "check-merge-rule-conditions: --changed-files and --body are both required.",
            file=sys.stderr,
        )
        _usage(sys.stderr)
        return EXIT_COULD_NOT_LOOK

    try:
        raw_changed = Path(changed_path).read_text(encoding="utf-8")
        body = Path(body_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(
            f"check-merge-rule-conditions: could not read its input ({exc}).\n"
            "  Exit 2, not a pass. An unreadable diff is not a clean diff.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    changed = [line.strip() for line in raw_changed.splitlines() if line.strip()]
    if not changed:
        print(
            "check-merge-rule-conditions: the changed-file list is EMPTY.\n"
            "  A PR changes something, so an empty list means the diff did not\n"
            "  resolve -- a shallow checkout, or the wrong base. Reading it as\n"
            "  'no migration' is the false green this gate exists to avoid;\n"
            "  see check_audit_evidence.py's is_code_change([]).",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    migrations = condition_4(changed)

    if not migrations:
        print(
            f"check-merge-rule-conditions: clean -- none of {len(changed)} changed "
            f"path(s) is an alembic revision, so condition 4 is not tripped. "
            f"Conditions 5 and 6 are NOT computed by this gate and remain "
            f"self-attested -- see the module docstring."
        )
        return EXIT_OK

    print("check-merge-rule-conditions: this PR trips condition 4 (migration):")
    for path in migrations:
        print(f"    {path}")

    why = declares_migration(body)
    if why is None:
        print(
            "\ncheck-merge-rule-conditions: FAILED -- the PR body does not declare "
            "the migration.",
            file=sys.stderr,
        )
        print(
            "  The merge rule says a PR tripping condition 4 comes back to the\n"
            "  human. THAT is not enforced here and is not meant to be; what is\n"
            "  enforced is that the PR says so.\n"
            "\n"
            "  Add a line to the body:\n"
            "\n"
            "      Merge-rule-condition-4: <what the migration does>\n"
            "\n"
            "  A MARKER rather than a mention, because the first version of this\n"
            "  gate matched a bare digit and accepted 'This does not trip\n"
            "  condition 4.' -- and accepted the PR template's own boilerplate,\n"
            "  which puts that digit in every body in the repo.",
            file=sys.stderr,
        )
        return EXIT_VIOLATION

    print(f"\ncheck-merge-rule-conditions: clean -- the body declares it: {why}")
    return EXIT_OK


if __name__ == "__main__":
    # A crash must NOT share an exit code with "violations found". Python exits 1
    # on an unhandled exception, which is this gate's "found something" code, so
    # an uncaught error would read as a verdict it never reached.
    #
    # `BaseException` with both propagating cases NAMED, rather than the
    # equivalent `except Exception`: a handler that says out loud what it
    # declines to swallow does not rely on the reader knowing the inheritance
    # tree. `SystemExit` is somebody's deliberate exit code. `KeyboardInterrupt`
    # is an operator who knows exactly what happened and is owed 130, not
    # "could not look".
    #
    # THE FIRST VERSION OF THIS BLOCK OMITTED `KeyboardInterrupt` and swallowed
    # Ctrl-C into exit 2. `tests/unit/test_gate_crash_exit_code.py` caught it on
    # the first run -- that harness doing exactly its job on the newest gate in
    # the repo, and the reason the block is duplicated verbatim in every gate
    # rather than shared: an import is one more thing that can fail BEFORE the
    # handler is installed, which is the defect it exists to close.
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-merge-rule-conditions: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(EXIT_COULD_NOT_LOOK) from exc
