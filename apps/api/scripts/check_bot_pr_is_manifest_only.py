#!/usr/bin/env python3
"""A PR exempted from the audit gate BY AUTHOR must be manifest-only BY CONTENT.

`audit-gate.yml` skips "Require recorded audit evidence" when the PR author is
`dependabot[bot]`. That exemption is justified by CONTENT -- "there are no
findings to record about a lockfile bump" -- and keyed on AUTHOR, and the gap
between those two is reachable:

**A maintainer can push commits to a Dependabot branch.** The routine case is a
bump that breaks something and a human fixing it in place. `pull_request.user.login`
stays `dependabot[bot]`, so the exemption follows the branch rather than the
content, and arbitrary human-authored code -- in `app/ai/`, in a scoring engine,
anywhere -- would merge with the required audit check green and no audit block
anywhere in the record. That is the class #93/#94/#95 record putting a
client-facing fabricated gap on `main`.

So this closes it from the other side. It runs ONLY for the exempted author, and
it fails when that PR touches anything outside the manifest and lockfile set. A
human pushing code onto a bot branch is then blocked -- loudly, by name, with the
offending paths printed -- instead of inheriting an exemption written for a
version bump.

## Why a separate step rather than folding it into the condition

`check_audit_evidence.py` stays author-blind: it is handed a changed-file list
and a body, and giving it an identity would turn a text checker into an
authorisation checker. This script is the opposite -- deciding an exemption is
its whole job, so it is the right place for an author to appear.

Keeping them separate also keeps the two failures distinguishable. "You did not
record an audit" and "this bot PR is not a version bump any more" are different
sentences, and a reader needs to know which one they are looking at.

## The allow-list is what Dependabot is configured to touch

`.github/dependabot.yml` declares pip, npm and github-actions. So the set is the
manifests and lockfiles those three ecosystems rewrite, plus the workflow files
the github-actions updater edits. Anything else on a bot PR is, by definition,
not the thing the exemption was written for.

DELIBERATELY NOT DERIVED from `.github/dependabot.yml`. That file names
ecosystems and directories, not the files an updater writes, so deriving the
path set from it would mean encoding Dependabot's internal behaviour -- a
synchronisation with something this repo does not control, which is worse than a
list whose additions are visible in review. The list is stated, and the reason
it is a list is stated with it.

## Silent-success branches, enumerated first

  * an EMPTY changed-file list -> exit 2. An empty diff on a bot PR is a
    checkout that did not resolve, and reading it as "no offending paths" is the
    `is_code_change([])` shape.
  * a MISSING or unreadable changed-file list -> exit 2.
  * an author that is NOT the exempted bot -> exit 0 immediately, printing that
    it did not apply. A human PR is not this script's business, and it must not
    be able to fail one.
  * no `--author` given at all -> exit 2, never 0. A missing author would
    otherwise take the same path as a human author and report clean over a bot
    PR nobody checked.

Exit codes follow D-051: 0 clean, 1 a real violation, 2 could not look.
"""

from __future__ import annotations

import sys
from fnmatch import fnmatch
from pathlib import Path

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_COULD_NOT_LOOK = 2

#: The author the audit gate exempts. One login, matching the `if:` in
#: `audit-gate.yml` -- if these two ever disagree the exemption is unguarded,
#: which is why `test_bot_pr_manifest_guard.py` asserts they are the same string.
EXEMPTED_AUTHOR = "dependabot[bot]"

#: What a version bump is allowed to touch. Manifests and lockfiles for the
#: three ecosystems `.github/dependabot.yml` declares, plus the workflow files
#: the github-actions updater rewrites.
MANIFEST_GLOBS = (
    # pip
    "**/pyproject.toml",
    "pyproject.toml",
    "**/requirements*.txt",
    "requirements*.txt",
    "**/poetry.lock",
    "**/uv.lock",
    # npm / pnpm
    "**/package.json",
    "package.json",
    "**/package-lock.json",
    "package-lock.json",
    "**/pnpm-lock.yaml",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "**/yarn.lock",
    # github-actions
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".github/actions/**",
)


def offending(changed: list[str]) -> list[str]:
    """Paths a version bump has no business touching."""
    return sorted(p for p in changed if not any(fnmatch(p, g) for g in MANIFEST_GLOBS))


def main(argv: list[str]) -> int:
    author: str | None = None
    changed_path: str | None = None
    args = argv[1:]
    index = 0
    while index < len(args):
        if args[index] == "--author" and index + 1 < len(args):
            author = args[index + 1]
            index += 2
        elif args[index] == "--changed-files" and index + 1 < len(args):
            changed_path = args[index + 1]
            index += 2
        else:
            print(
                f"check-bot-pr-manifest-only: unknown argument {args[index]!r}.\n"
                "  Usage: --author <login> --changed-files <file>\n"
                "  Refusing to report on input it could not parse: an ignored\n"
                "  flag is how a gate reports clean having read nothing (#343).",
                file=sys.stderr,
            )
            return EXIT_COULD_NOT_LOOK

    # A MISSING author is exit 2, never the human path. Falling through to
    # "not the exempted bot, nothing to do" would report clean over a bot PR
    # nobody checked -- the could-not-look branch wearing the clean one's
    # clothes, which is the whole defect this repo's exit-2 convention exists
    # for.
    if author is None:
        print(
            "check-bot-pr-manifest-only: no --author given.\n"
            "  Exit 2, not 0. Without an author this cannot tell an exempted\n"
            "  bot PR from a human one, and the human path exits 0.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    if author != EXEMPTED_AUTHOR:
        print(
            f"check-bot-pr-manifest-only: not applicable -- author is {author!r}, "
            f"not {EXEMPTED_AUTHOR!r}. A human PR keeps the audit requirement and "
            f"is not this check's business."
        )
        return EXIT_OK

    if changed_path is None:
        print(
            "check-bot-pr-manifest-only: --changed-files is required.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    try:
        raw = Path(changed_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(
            f"check-bot-pr-manifest-only: could not read {changed_path} ({exc}).\n"
            "  Exit 2, not a pass.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    changed = [line.strip() for line in raw.splitlines() if line.strip()]
    if not changed:
        print(
            "check-bot-pr-manifest-only: the changed-file list is EMPTY on a bot PR.\n"
            "  A PR changes something, so this is a diff that did not resolve --\n"
            "  and reading it as 'no offending paths' would exempt a PR nobody\n"
            "  looked at. See check_audit_evidence.py's is_code_change([]).",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    bad = offending(changed)
    if bad:
        print(
            f"check-bot-pr-manifest-only: FAILED -- this PR is authored by "
            f"{EXEMPTED_AUTHOR} and is exempt from the audit gate, but it touches "
            f"{len(bad)} path(s) outside the manifest and lockfile set:",
            file=sys.stderr,
        )
        for path in bad:
            print(f"    {path}", file=sys.stderr)
        print(
            "\n  The audit exemption is justified by CONTENT -- there are no\n"
            "  adversarial findings to record about a version bump -- and keyed\n"
            "  on AUTHOR. A human pushing commits onto a Dependabot branch keeps\n"
            "  that author, so without this check arbitrary code would merge with\n"
            "  the required audit check green and no audit block anywhere.\n"
            "\n"
            "  If these paths belong here, the PR is no longer a version bump:\n"
            "  open it under a human author and record an audit.",
            file=sys.stderr,
        )
        return EXIT_VIOLATION

    print(
        f"check-bot-pr-manifest-only: clean -- all {len(changed)} changed path(s) "
        f"are manifests or lockfiles, so the audit exemption still describes what "
        f"this PR does."
    )
    return EXIT_OK


if __name__ == "__main__":
    # A crash must NOT share an exit code with "violations found". Python exits 1
    # on an unhandled exception, which is this gate's "found something" code, so
    # an uncaught error would read as a verdict it never reached.
    #
    # `BaseException` with both propagating cases NAMED rather than the
    # equivalent `except Exception`: a handler that says out loud what it
    # declines to swallow does not rely on the reader knowing the inheritance
    # tree. `SystemExit` is somebody's deliberate exit code. `KeyboardInterrupt`
    # is an operator who knows exactly what happened and is owed 130, not
    # "could not look".
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-bot-pr-manifest-only: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(EXIT_COULD_NOT_LOOK) from exc
