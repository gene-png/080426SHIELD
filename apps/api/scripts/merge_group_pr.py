"""Resolve a merge-queue entry to its pull request, for the required body checks.

"Adversarial audit recorded" and "No accidental issue closes" read the PR's
title and description. On a `merge_group` event `github.event.pull_request` does
not exist, so both would check an empty body. The queue names the PR only in the
group's head ref:

    refs/heads/gh-readonly-queue/main/pr-<N>-<40-hex sha>

This parses N and fetches PR N's CURRENT title, body, author, changed files,
commits, closing references, diff and head sha, writing each to the path the
existing check step already reads. It deliberately does NOT trust the earlier
pull_request run: a description edited after that run and before the queue
merged it would otherwise land unchecked.

With `--base-sha` and `--group-head-sha` (the event's `merge_group.base_sha`
and `merge_group.head_sha`; both workflows always pass the pair) it also
confirms that the PR's CURRENT head is what the group merges:

    tree(group head) == git merge-tree --write-tree <base> <PR head>

A squash, a merge commit and a rebase each give the group's head the tree of
"base plus this PR", so the comparison does not depend on the merge method.
A PR pushed after it was queued, or a group carrying anything beyond base plus
this PR, fails it: the body just read would describe a head the queue is not
merging. Without the pair the head is NOT checked, and the clean line says so.

Exit codes, per this repo's gate convention (D-090):
  0  every requested output written, from the PR the ref names
  2  could not look: the ref does not parse, an argument is missing or unknown,
     nothing was asked for, a fetch failed, GitHub answered with a different
     PR than the ref names, only one of the group shas was given or either is
     not 40 lowercase hex, a commit is missing and cannot be fetched, or the
     PR's current head is not what the group merges

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

NL = chr(10)

#: The queue ref for `main`. `refs/heads/` is optional because the event's
#: `head_ref` is documented as the full ref and some callers strip it. N is a
#: positive integer with no leading zero; the sha is exactly 40 lowercase hex.
_QUEUE_REF = re.compile(r"(?:refs/heads/)?gh-readonly-queue/main/pr-([1-9][0-9]*)-[0-9a-f]{40}")

_OUTPUTS = ("title", "body", "author", "files", "commits", "linked", "diff", "head-sha")

#: A full commit sha as GitHub writes it in an event payload and the REST API.
_SHA = re.compile(r"[0-9a-f]{40}")

DEPENDABOT = "dependabot[bot]"


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


def _git(*args: str) -> tuple[int, str]:
    """Run `git` in the checkout with a fixed argv list; every variable part is
    a sha validated against `_SHA` first. Returns (exit code, output): stdout
    for 0 and 1 (merge-tree prints its tree on a conflict too), stderr else."""
    proc = subprocess.run(  # noqa: S603  # nosec B603
        ["git", *args],  # noqa: S607  # nosec B607
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
    )
    return proc.returncode, proc.stdout if proc.returncode in (0, 1) else proc.stderr


def _require_sha(what: str, value: object) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise ValueError(f"{what} is not a 40-character lowercase hex sha: {value!r}")
    return value


def _ensure_commit(sha: str) -> None:
    """The commit is in the clone, fetched by sha if not. A fork's head is not
    under refs/heads, so `fetch-depth: 0` does not bring it in."""
    if _git("cat-file", "-e", f"{sha}^{{commit}}")[0] == 0:
        return
    code, err = _git("fetch", "--no-tags", "--quiet", "origin", sha)
    if code != 0 or _git("cat-file", "-e", f"{sha}^{{commit}}")[0] != 0:
        raise RuntimeError(f"commit {sha} is not in the clone and could not be fetched: {err}")


def confirm_group_head(number: int, base: str, group: str, pr_head: str) -> None:
    """Raise unless the group's head tree is base plus PR `number`'s head."""
    for sha in (base, group, pr_head):
        _ensure_commit(sha)
    code, out = _git("merge-tree", "--write-tree", base, pr_head)
    if code == 1:
        raise ValueError(
            f"PR #{number}'s current head {pr_head} conflicts with the group's base {base}, "
            "so it is not what the group merges"
        )
    if code != 0:
        raise RuntimeError(f"git merge-tree --write-tree {base} {pr_head} failed: {out.strip()}")
    expected = out.split()[0] if out.split() else ""
    code, out = _git("rev-parse", f"{group}^{{tree}}")
    if code != 0:
        raise RuntimeError(f"git rev-parse {group}^{{tree}} failed: {out.strip()}")
    actual = out.strip()
    if not expected or expected != actual:
        raise ValueError(
            f"PR #{number}'s current head {pr_head} is NOT what merge group {group} merges: "
            f"base {base} plus that head is tree {expected or '(none)'}, the group's head is "
            f"tree {actual}. The PR was pushed after it was queued, or the group holds more "
            "than this PR, so the body just read does not describe the merged change"
        )


def _pages(raw: str) -> list[dict]:
    """`gh api --paginate --slurp` prints a list of pages; flatten it."""
    data = json.loads(raw)
    if not isinstance(data, list) or not all(isinstance(page, list) for page in data):
        raise ValueError("expected a list of pages from gh api --paginate --slurp")
    return [item for page in data for item in page]


def fetch(repo: str, number: int, wanted: set[str]) -> dict[str, str]:
    """Every wanted output's text for PR `number`, or an exception. "head-sha"
    is the PR's current head, a validated 40-hex sha plus a newline."""
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
    if "head-sha" in wanted:
        texts["head-sha"] = _require_sha(f"PR #{number}'s head.sha", pr["head"]["sha"]) + NL
    if "files" in wanted:
        files = _pages(
            _gh("api", "--paginate", "--slurp", f"repos/{repo}/pulls/{number}/files?per_page=100")
        )
        _require_all("changed files", len(files), pr["changed_files"])
        texts["files"] = "".join(f"{f['filename']}\n" for f in files)
    if "commits" in wanted:
        commits = _pages(
            _gh("api", "--paginate", "--slurp", f"repos/{repo}/pulls/{number}/commits?per_page=100")
        )
        _require_all("commits", len(commits), pr["commits"])
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
        # Only the Dependabot manifest guard reads the diff, and it runs only for
        # Dependabot. GitHub refuses the diff media type for very large PRs, so
        # fetching it for everyone would turn a big human PR red in the queue for
        # an input nothing reads (#659 round 1). Anyone else gets a line that is
        # not a diff, so a future reader that parses it fails rather than judging
        # an empty change.
        if pr["user"]["login"] == DEPENDABOT:
            texts["diff"] = _gh(
                "api", "-H", "Accept: application/vnd.github.diff", f"repos/{repo}/pulls/{number}"
            )
        else:
            texts["diff"] = f"# diff not fetched: the PR author is not {DEPENDABOT}\n"
    return texts


def _require_all(what: str, got: int, expected: object) -> None:
    """GitHub's list endpoints cap silently: `pulls/N/commits` at 250 and
    `pulls/N/files` at 3000. A body check fed a truncated list judges part of
    the PR as if it were all of it, so a count that does not match the PR's own
    is could-not-look, never a partial answer (#659 round 1)."""
    if not isinstance(expected, int) or got != expected:
        raise ValueError(
            f"fetched {got} {what} but the PR reports {expected!r} -- GitHub truncated "
            "the list or the PR changed during the fetch, so nothing is judged"
        )


def _parse(
    argv: list[str],
) -> tuple[str, str, dict[str, Path], tuple[str, str] | None]:
    head_ref: str | None = None
    repo: str | None = None
    group_shas: dict[str, str] = {}
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
        elif flag in ("--base-sha", "--group-head-sha"):
            group_shas[flag] = _require_sha(flag, value)
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
    if len(group_shas) == 1:
        raise ValueError("--base-sha and --group-head-sha go together; got only one")
    group = (group_shas["--base-sha"], group_shas["--group-head-sha"]) if group_shas else None
    return head_ref, repo, outs, group


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    try:
        head_ref, repo, outs, group = _parse(argv)
    except ValueError as exc:
        print(f"merge-group-pr: could not look -- {exc}", file=sys.stderr)
        return 2
    for path in outs.values():
        path.unlink(missing_ok=True)
    try:
        number = parse_pr_number(head_ref)
        # The head sha is fetched whenever the group is checked, written or not.
        texts = fetch(repo, number, set(outs) | ({"head-sha"} if group else set()))
        if group is not None:
            confirm_group_head(number, group[0], group[1], texts["head-sha"].strip())
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
    if group is None:
        print(
            "merge-group-pr: head NOT checked against a merge group "
            "(no --base-sha/--group-head-sha)"
        )
    else:
        print(
            f"merge-group-pr: head {texts['head-sha'].strip()} is what group {group[1]} "
            f"merges onto {group[0]}"
        )
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
