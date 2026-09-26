"""Resolve a merge-queue entry to its pull request, for the required body checks.

"Adversarial audit recorded" and "No accidental issue closes" read the PR's
title and description. On a `merge_group` event `github.event.pull_request` does
not exist, so both would check an empty body. The queue names the PR only in the
group's head ref:

    refs/heads/gh-readonly-queue/main/pr-<N>-<40-hex sha>

This parses N and fetches PR N's CURRENT title, body, author, changed files,
commits, closing references and diff, writing each to the path the existing
check step already reads. It deliberately does NOT trust the earlier
pull_request run: a description edited after that run and before the queue
merged it would otherwise land unchecked.

Exit codes, per this repo's gate convention (D-090):
  0  every requested output written, from the PR the ref names
  2  could not look: the ref does not parse, an argument is missing or unknown,
     nothing was asked for, a fetch failed, or GitHub answered with a different
     PR than the ref names

There is no 1: this resolves inputs and judges nothing. On 2, every requested
output path is DELETED, including one an earlier step wrote, so a later check
step fails on a missing file instead of reading a stale body as current. The
outputs are written only after every fetch has succeeded.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

#: The queue ref for `main`. `refs/heads/` is optional because the event's
#: `head_ref` is documented as the full ref and some callers strip it. N is a
#: positive integer with no leading zero; the sha is exactly 40 lowercase hex.
_QUEUE_REF = re.compile(r"(?:refs/heads/)?gh-readonly-queue/main/pr-([1-9][0-9]*)-[0-9a-f]{40}")

_OUTPUTS = ("title", "body", "author", "files", "commits", "linked", "diff")


class UnreadableRef(ValueError):
    """The merge group's head ref is not a queue ref for `main`."""


def parse_pr_number(head_ref: str) -> int:
    """PR number named by a merge-queue head ref, or UnreadableRef."""
    match = _QUEUE_REF.fullmatch(head_ref)
    if match is None:
        raise UnreadableRef(f"not a merge-queue ref for main: {head_ref!r}")
    return int(match.group(1))


def _gh(*args: str) -> str:
    """Run `gh` with a fixed argv list. The repo and PR number are the only
    variable parts, and both are validated before they get here, so no PR text
    reaches the command line (S603/S607, B603/B607)."""
    proc = subprocess.run(  # noqa: S603  # nosec B603
        ["gh", *args],  # noqa: S607  # nosec B607
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _pages(raw: str) -> list[dict]:
    """`gh api --paginate --slurp` prints a list of pages; flatten it."""
    data = json.loads(raw)
    if not isinstance(data, list) or not all(isinstance(page, list) for page in data):
        raise ValueError("expected a list of pages from gh api --paginate --slurp")
    return [item for page in data for item in page]


def fetch(repo: str, number: int, wanted: set[str]) -> dict[str, str]:
    """Every wanted output's text for PR `number`, or an exception."""
    pr = json.loads(_gh("api", f"repos/{repo}/pulls/{number}"))
    if pr.get("number") != number:
        raise ValueError(f"asked GitHub for PR {number}, got PR {pr.get('number')!r}")
    texts: dict[str, str] = {}
    if "title" in wanted:
        texts["title"] = pr["title"]
    if "body" in wanted:
        texts["body"] = pr.get("body") or ""
    if "author" in wanted:
        texts["author"] = pr["user"]["login"]
    if "files" in wanted:
        files = _pages(
            _gh("api", "--paginate", "--slurp", f"repos/{repo}/pulls/{number}/files?per_page=100")
        )
        texts["files"] = "".join(f"{f['filename']}\n" for f in files)
    if "commits" in wanted:
        commits = _pages(
            _gh("api", "--paginate", "--slurp", f"repos/{repo}/pulls/{number}/commits?per_page=100")
        )
        texts["commits"] = "\n\n".join(c["commit"]["message"] for c in commits) + "\n"
    if "linked" in wanted:
        texts["linked"] = _gh(
            "pr",
            "view",
            str(number),
            "--repo",
            repo,
            "--json",
            "closingIssuesReferences",
            "--jq",
            ".closingIssuesReferences[].number",
        )
    if "diff" in wanted:
        texts["diff"] = _gh(
            "api", "-H", "Accept: application/vnd.github.diff", f"repos/{repo}/pulls/{number}"
        )
    return texts


def _parse(argv: list[str]) -> tuple[str, str, dict[str, Path]]:
    head_ref: str | None = None
    repo: str | None = None
    outs: dict[str, Path] = {}
    args = list(argv[1:])
    while args:
        flag = args.pop(0)
        if not args:
            raise ValueError(f"{flag} has no value")
        value = args.pop(0)
        if flag == "--head-ref":
            head_ref = value
        elif flag == "--repo":
            repo = value
        elif flag.startswith("--") and flag.endswith("-out") and flag[2:-4] in _OUTPUTS:
            outs[flag[2:-4]] = Path(value)
        else:
            raise ValueError(f"unknown argument: {flag!r}")
    if head_ref is None or not repo:
        raise ValueError("--head-ref and --repo are both required")
    if not outs:
        raise ValueError(
            f"no output requested; name at least one of --{{{','.join(_OUTPUTS)}}}-out"
        )
    return head_ref, repo, outs


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    try:
        head_ref, repo, outs = _parse(argv)
    except ValueError as exc:
        print(f"merge-group-pr: could not look -- {exc}", file=sys.stderr)
        return 2
    for path in outs.values():
        path.unlink(missing_ok=True)
    try:
        number = parse_pr_number(head_ref)
        texts = fetch(repo, number, set(outs))
    except (UnreadableRef, RuntimeError, ValueError, KeyError, TypeError) as exc:
        print(
            f"merge-group-pr: could not look -- {exc}. No body was written, so the "
            "check that reads it fails; the earlier pull_request run is NOT a "
            "substitute, because the description can change after it.",
            file=sys.stderr,
        )
        return 2
    for name, path in outs.items():
        path.write_text(texts[name], encoding="utf-8")
    print(f"merge-group-pr: {head_ref} is PR #{number}; wrote {', '.join(sorted(outs))}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"merge-group-pr: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a resolved body, and nothing was written (D-090).{nl}")
        raise SystemExit(2) from exc
