"""Merge gate: a code PR must carry evidence that the adversarial audit ran.

Plan §14 — "every workstream merges on a clean adversarial-reviewer audit, not
on a green suite" — was skipped on three consecutive code PRs (#93, #94, #95).
Every one of them was green, and every one of them put a defect on `main` that
the audit found afterwards, including a client-facing fabricated gap.

**Why this is a CI check and not a line in CLAUDE.md.** The first proposed fix
was to document the gate in `CLAUDE.md` so it would be visible every session.
That is a discipline fix, and this repo has nine recorded instances (#72) of
discipline failing against exactly this shape — including one written minutes
after the rule was logged. A rule that depends on someone remembering it is the
thing that already failed; visibility was not the binding constraint.

**Why not the full W8b (run the reviewer agent in CI).** That was deferred for
reasons that still hold: it is non-deterministic and expensive per PR. This
check is neither: it runs in under a second and has no model in the loop.

**It does NOT block a merge on its own, and an earlier version of this docstring
claimed it did.** A workflow job only reports a status. It becomes blocking only
once "Adversarial audit recorded" is registered as a required status check in
the branch protection rules for `main` — a GitHub setting, not a file in this
repo, so nothing in the change that added this check could perform or verify it.
Until that registration happens this is a visible red X and nothing more, which
is weaker than "structural" and has to be said rather than assumed. Tracked in
DECISIONS.md D-051.

## What it can and cannot prove

It proves the author RECORDED an audit and its disposition. It cannot prove the
audit was performed, or that it was any good. That is deliberate: it is the same
honesty convention `SMOKE_TEST.md` already runs on, and overclaiming here would
be the #72 pattern one level up.

What it does change is that skipping becomes **deliberate and visible** instead
of silent. All three misses were silent — nothing anywhere said the gate had not
run, which is why three in a row was possible.

## The contract

A PR touching code must contain a block like:

    ## Adversarial audit
    Reviewer: adversarial-reviewer
    Findings: 3 confirmed, 2 plausible
    Disposition: 1-3 fixed in this PR; 4 filed as #101; 5 rejected — see below

`Findings:` and `Disposition:` are both required, and `Findings: none` is a
valid answer that still requires a disposition line saying so.

A PR touching only documentation is exempt and says so in its own output —
#88 and #91 were pure docs, and that is the one defensible skip.

Usage:
    python -m scripts.check_audit_evidence --changed-files <file> --body <file>
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Horizontal whitespace ONLY. A plain `\s*` after the colon crosses newlines, so
# an EMPTY "Findings:" line matched the text of the NEXT line and reported itself
# satisfied — the gate would have accepted a blank claim as evidence. Caught by
# `test_an_empty_findings_value_is_not_evidence`, which is the whole reason that
# test exists.
_H = r"[ \t]*"
# Markdown emphasis around the label. `**Findings:** none` is the dominant style
# in this repo's prose, and the first version REJECTED it — printing
# 'no "Findings:" line' over a body that visibly contained one, which is a check
# telling an author something false about their own text.
_EM = r"[*_]{0,2}"

# `{0,3}` indentation, NOT `_H`. Four spaces makes a markdown code block, so the
# indented example in this module's own docstring and in its stderr help text
# cannot satisfy the heading — an author pasting the error message back into a
# PR body does not thereby pass the gate. That property was accidental before it
# was noticed; it is pinned now by
# `test_the_error_messages_own_example_does_not_satisfy_the_gate`.
HEADING = re.compile(
    r"^[ \t]{0,3}#{1,6}[ \t]*[*_]{0,2}adversarial audit\b", re.IGNORECASE | re.MULTILINE
)


def _label(word: str) -> re.Pattern[str]:
    return re.compile(
        rf"^{_H}[-*]?{_H}{_EM}{word}{_EM}{_H}:{_EM}{_H}(\S.*)$",
        re.IGNORECASE | re.MULTILINE,
    )


FINDINGS = _label("findings")
DISPOSITION = _label("disposition")

#: Paths that cannot change behaviour. Everything else counts as code — the
#: default is deliberately "this needs an audit", so a new directory is covered
#: without anyone remembering to add it.
DOC_SUFFIXES = (".md", ".txt", ".rst")
DOC_PREFIXES = ("docs/", "context/")
#: `.md` under here is not prose. `.claude/agents/adversarial-reviewer.md` IS
#: the reviewer this gate exists to enforce, and CLAUDE.md governs how every
#: session behaves. Exempting them would let the mechanism that catches the next
#: #93 be rewritten with no audit — contradicting the principle
#: `test_a_workflow_change_needs_an_audit` states: changing the gates themselves
#: is when review matters most.
CODE_PREFIXES = (".claude/",)
CODE_PATHS = ("CLAUDE.md",)


def is_code_change(paths: list[str]) -> bool:
    for raw in paths:
        path = raw.strip()
        if not path:
            continue
        if path in CODE_PATHS or path.startswith(CODE_PREFIXES):
            return True
        if path.startswith(DOC_PREFIXES):
            continue
        if path.endswith(DOC_SUFFIXES):
            continue
        return True
    return False


def missing_evidence(body: str) -> list[str]:
    """Which required parts of the audit block are absent."""
    problems: list[str] = []
    if not HEADING.search(body):
        problems.append('no "## Adversarial audit" section')
    if not FINDINGS.search(body):
        problems.append('no "Findings:" line (use "Findings: none" if it found nothing)')
    if not DISPOSITION.search(body):
        problems.append('no "Disposition:" line (what happened to each finding)')
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--changed-files", required=True, help="file listing changed paths, one per line"
    )
    ap.add_argument("--body", required=True, help="file containing the PR body")
    args = ap.parse_args(argv)

    paths = Path(args.changed_files).read_text(encoding="utf-8").splitlines()
    # Fail CLOSED on no input. `is_code_change([])` is False, so an empty list
    # printed "documentation-only change, exempt" — a green gate with a
    # positive-sounding message, from input that supports neither reading. Not
    # reachable through the current workflow (`fetch-depth: 0` plus `bash -e`
    # turn a failed diff into a red step), but it is the shape that fails OPEN
    # the day someone changes the checkout depth or adds a `|| true`.
    if not [p for p in paths if p.strip()]:
        print(
            "audit gate: no changed paths were collected — refusing to guess "
            "whether this PR needs an audit.",
            file=sys.stderr,
        )
        return 2
    if not is_code_change(paths):
        print("audit gate: documentation-only change, exempt.")
        return 0

    body = Path(args.body).read_text(encoding="utf-8")
    problems = missing_evidence(body)
    if not problems:
        print("audit gate: adversarial audit recorded.")
        return 0

    print(
        "This PR changes code, so plan §14 requires a recorded adversarial audit.", file=sys.stderr
    )
    for p in problems:
        print(f"  - {p}", file=sys.stderr)
    print(
        "\nAdd a section to the PR description:\n\n"
        "    ## Adversarial audit\n"
        "    Reviewer: adversarial-reviewer\n"
        "    Findings: none\n"
        "    Disposition: nothing to act on\n\n"
        "This records that the audit ran; it cannot prove it was any good. The point\n"
        "is that skipping it becomes deliberate rather than silent — #93, #94 and #95\n"
        "each merged green with the gate silently skipped, and each put a defect on\n"
        "main that the audit found afterwards.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
