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

## Two allow-lists, because two file classes carry different authority

`.github/dependabot.yml` declares pip, npm and github-actions.

**Manifests and lockfiles are judged by PATH.** A dependency manifest has no
authority over anything except which versions install, so matching the path is
enough.

**`.github/` files are judged by CONTENT**, and the first version of this file
got that wrong -- it put `.github/workflows/*.yml` on the path allow-list, which
meant a PR authored as `dependabot[bot]` could rewrite `audit-gate.yml`, delete
the very step this exemption lives in, and pass. In the file class that controls
every other gate. See `GITHUB_GLOBS`.

DELIBERATELY NOT DERIVED from `.github/dependabot.yml`. That file names
ecosystems and directories, not the files an updater writes, so deriving the
path set from it would mean encoding Dependabot's internal behaviour -- a
synchronisation with something this repo does not control, which is worse than a
list whose additions are visible in review.

## HOW THIS WAS VALIDATED, and how the first attempt validated the wrong half

The first run checked all four open bot PRs (#465-#468) and reported every one
clean. That establishes the allow-list is WIDE ENOUGH. It says nothing about
whether it is NARROW ENOUGH -- and #465 passed *precisely because* workflows were
permitted, so the run meant to validate the guard exercised the dangerous case
and recorded it as a pass.

**An allow-list validated only against benign traffic is certified for coverage,
never for restriction.** Same defect as sampling mutations only from inside the
region the tests already cover: both produce a confident green from a population
that could not have gone red.

So the validation now has both halves, and the second is the one that matters:

  * all four real PRs, with their real diffs -> exit 0;
  * #465's real diff with a single `continue-on-error: true` planted into it
    -> exit 1, naming the line.

## Silent-success branches, enumerated first

  * an EMPTY changed-file list -> exit 2. An empty diff on a bot PR is a
    checkout that did not resolve, and reading it as "no offending paths" is the
    `is_code_change([])` shape.
  * a MISSING or unreadable changed-file list -> exit 2.
  * a `.github/` path changed and NO `--diff` given -> exit 2. A path match
    cannot decide that file, and treating the match as approval is the hole
    above.
  * a `.github/` path in the changed-file list but ABSENT from the diff -> exit
    2. The two inputs disagree, and the direction that matters is that the file
    would otherwise be approved unexamined.
  * an author that is NOT the exempted bot -> exit 0 immediately, printing that
    it did not apply. A human PR is not this script's business, and it must not
    be able to fail one.
  * no `--author` given at all -> exit 2, never 0. A missing author would
    otherwise take the same path as a human author and report clean over a bot
    PR nobody checked.

Exit codes follow D-051: 0 clean, 1 a real violation, 2 could not look.
"""

from __future__ import annotations

import re
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

#: Manifests and lockfiles for the ecosystems `.github/dependabot.yml` declares.
#: A path match alone is enough here: a dependency manifest has no authority over
#: anything except which versions install.
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
)

#: `.github/` IS NOT ON THE PATH ALLOW-LIST, and the first version of this file
#: put it there. That was a hole in the file class that controls every other gate.
#:
#: `.github/workflows/*.yml` was permitted because the github-actions updater
#: legitimately rewrites workflows to bump `uses:` refs -- #465 does exactly
#: that. But a path match cannot tell a ref bump from a rewrite of the audit
#: gate itself, so a PR authored as `dependabot[bot]` could have edited
#: `audit-gate.yml` -- removing the very step this exemption lives in -- and
#: passed the manifest-only check. Anyone with write access can push to a
#: Dependabot branch, `enforce_admins` is false, and zero reviews are required.
#:
#: REMOVING THE GLOB WAS THE WRONG FIX because it re-breaks #465. So `.github/`
#: is judged by CONTENT: every added or removed line in such a file must be a
#: `uses: <owner>/<repo>@<ref>` bump. Anything else from a bot author is a
#: violation. Measured on #465 -- every changed line across three workflow files
#: is a `uses:` bump, so the real traffic passes and the dangerous edit does not.
GITHUB_GLOBS = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".github/actions/**",
)

#: A `uses:` line, with or without the leading list dash. Anchored on the owner
#: and repo so a bare `uses: ./local-action` does not qualify: a local action is
#: in-repo code, and pointing a workflow at a different one is not a version bump.
_USES_BUMP = re.compile(r"^[-+]\s*(?:-\s*)?uses:\s*[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@\S+\s*$")

#: Unified-diff file headers. `b/` is the post-image path, which is what a
#: changed-file list names.
_DIFF_FILE = re.compile(r"^diff --git a/(?P<a>\S+) b/(?P<b>\S+)$")


def offending_paths(changed: list[str]) -> list[str]:
    """Paths a version bump has no business touching at all."""
    allowed = MANIFEST_GLOBS + GITHUB_GLOBS
    return sorted(p for p in changed if not any(fnmatch(p, g) for g in allowed))


def changed_lines_by_file(diff: str) -> dict[str, list[str]]:
    """Added and removed lines, per post-image path, from a unified diff.

    `+++`/`---` headers are excluded -- they start with the same character as a
    content line and counting them would make every changed file look like it
    carries a non-bump line.
    """
    out: dict[str, list[str]] = {}
    current: str | None = None
    for line in diff.splitlines():
        header = _DIFF_FILE.match(line)
        if header:
            current = header.group("b")
            out.setdefault(current, [])
            continue
        if current is None:
            continue
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")):
            out[current].append(line)
    return out


def non_bump_lines(path: str, lines: list[str]) -> list[str]:
    """Changed lines in a `.github/` file that are not `uses:` ref bumps."""
    return [ln for ln in lines if not _USES_BUMP.match(ln)]


def main(argv: list[str]) -> int:
    author: str | None = None
    changed_path: str | None = None
    diff_path: str | None = None
    args = argv[1:]
    index = 0
    while index < len(args):
        if args[index] == "--author" and index + 1 < len(args):
            author = args[index + 1]
            index += 2
        elif args[index] == "--changed-files" and index + 1 < len(args):
            changed_path = args[index + 1]
            index += 2
        elif args[index] == "--diff" and index + 1 < len(args):
            diff_path = args[index + 1]
            index += 2
        else:
            print(
                f"check-bot-pr-manifest-only: unknown argument {args[index]!r}.\n"
                "  Usage: --author <login> --changed-files <file> [--diff <file>]\n"
                "  `--diff` is REQUIRED when the PR touches `.github/`; see the\n"
                "  module docstring for why a path match is not enough there.\n"
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

    bad = offending_paths(changed)
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

    # `.github/` FILES ARE JUDGED BY CONTENT, not by their path. See GITHUB_GLOBS:
    # a path match cannot tell a `uses:` ref bump from a rewrite of the audit
    # gate this exemption lives in.
    github_paths = [p for p in changed if any(fnmatch(p, g) for g in GITHUB_GLOBS)]
    if github_paths:
        if diff_path is None:
            print(
                f"check-bot-pr-manifest-only: this PR touches {len(github_paths)} "
                f"file(s) under `.github/` and no --diff was given.\n"
                "  Exit 2, not a pass. Those files are permitted only when every\n"
                "  changed line is a `uses:` ref bump, and that cannot be decided\n"
                "  from a file list. Reading the path match alone as approval is\n"
                "  the hole this check was extended to close.",
                file=sys.stderr,
            )
            return EXIT_COULD_NOT_LOOK
        try:
            diff_text = Path(diff_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(
                f"check-bot-pr-manifest-only: could not read {diff_path} ({exc}).\n"
                "  Exit 2, not a pass.",
                file=sys.stderr,
            )
            return EXIT_COULD_NOT_LOOK

        per_file = changed_lines_by_file(diff_text)
        violations: list[tuple[str, list[str]]] = []
        for path in github_paths:
            if path not in per_file:
                print(
                    f"check-bot-pr-manifest-only: {path} is in the changed-file "
                    f"list and NOT in the diff.\n"
                    "  Exit 2. The two inputs disagree, so neither can be trusted\n"
                    "  about this file -- and the direction that matters is that a\n"
                    "  `.github/` change would otherwise be approved unexamined.",
                    file=sys.stderr,
                )
                return EXIT_COULD_NOT_LOOK
            extra = non_bump_lines(path, per_file[path])
            if extra:
                violations.append((path, extra))

        if violations:
            print(
                "check-bot-pr-manifest-only: FAILED -- this bot PR changes "
                "`.github/` content that is not a `uses:` ref bump:",
                file=sys.stderr,
            )
            for path, lines in violations:
                print(f"    {path}", file=sys.stderr)
                for line in lines[:6]:
                    print(f"        {line}", file=sys.stderr)
                if len(lines) > 6:
                    print(f"        ... and {len(lines) - 6} more", file=sys.stderr)
            print(
                "\n  A workflow file is permitted on an audit-exempt PR ONLY for a\n"
                "  version bump of an action, because that is what the\n"
                "  github-actions updater does. Anything else there is a change to\n"
                "  the machinery that enforces every other gate -- including the\n"
                "  audit step this PR is exempt from -- and it must be reviewed\n"
                "  under a human author with an audit recorded.",
                file=sys.stderr,
            )
            return EXIT_VIOLATION

    manifests = len(changed) - len(github_paths)
    detail = f"{manifests} manifest/lockfile path(s)"
    if github_paths:
        detail += f" and {len(github_paths)} `.github/` file(s) whose every changed line is a `uses:` bump"
    print(
        f"check-bot-pr-manifest-only: clean -- {detail}, so the audit exemption "
        f"still describes what this PR does."
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
