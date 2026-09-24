"""Every OPEN issue carries `mvp-blocking` plus exactly one tier, `unowned-with-reason`, or `post-mvp`.

CLAUDE.md's filing rule: every new issue carries `mvp-blocking` plus one of
`tier-1` / `tier-2` / `tier-3`, OR `unowned-with-reason` with the reason in the
body, OR `post-mvp` -- deliberately deferred past the MVP (D-086). The board is `is:issue is:open label:mvp-blocking` ordered by tier, so an
issue without `mvp-blocking` is not on it, and one with it and no tier "has no
place in the ordering". Either way it is invisible to the only view used to
decide what to work on. The rule was written down and nothing enforced it.

What this checks is LABELS only. It does not read the body, so an
`unowned-with-reason` issue whose body gives no reason passes -- a residual,
stated here because "or says why" would be the natural misreading of the rule's
second half.

`mvp-blocking` triggers the tier check whether or not `unowned-with-reason` is
also present: the board query returns the issue either way, so it needs a place
in the ordering either way. An unowned blocker is a coherent state.

`mvp-blocking` together with `post-mvp` is NOT: "blocks the MVP" and "deferred
past it" contradict each other, whatever the tiers, so the pair is its own
fault and is reported before any tier check. The case it catches is a half-done
move to `post-mvp` that forgot to remove `mvp-blocking`. Off the board,
`post-mvp` allows a tier and does not require one.

Two modes:
  * FULL (default): every open issue. Exit 1 if any breaks the rule.
  * EVENT (`--issue N`): judge only issue N, and print the standing total as
    information. A new unlabelled issue must be visible as a change, and with a
    standing backlog a full check is red on every run, so the new one would not
    be.

Input: `gh api` against `$REPO`, or `--issues-file PATH` holding the same JSON
(a list of pages, as `gh api --paginate --slurp` prints, or a flat list). The
file form exists so the fixture harness can run real cases without a network.

Exit codes, per this repo's gate convention (D-051):
  0  the rule holds (for every open issue, or for issue N)
  1  it does not (each fault listed)
  2  could not look: no REPO and no file, `gh` or the file unreadable, zero
     issues read, or issue N not among the open issues read
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

BOARD = "mvp-blocking"
UNOWNED = "unowned-with-reason"
DEFERRED = "post-mvp"
TIERS = ("tier-1", "tier-2", "tier-3")

_MESSAGES = {
    "no_tier": f"carries `{BOARD}` but no tier, so it has no place in the ordering",
    "several_tiers": f"carries `{BOARD}` and more than one tier",
    "deferred_on_board": (
        f"carries both `{BOARD}` and `{DEFERRED}`: on the board and deferred past "
        "the MVP at once -- remove one"
    ),
    "off_board": (
        f"carries neither `{BOARD}` + a tier, nor `{UNOWNED}`, nor `{DEFERRED}`, "
        "so it is not on the board"
    ),
}


def classify(labels: set[str]) -> str | None:
    """The rule's verdict on one issue's labels: None, or the fault's key."""
    if BOARD in labels and DEFERRED in labels:
        return "deferred_on_board"
    if BOARD in labels:
        tiers = [t for t in TIERS if t in labels]
        if not tiers:
            return "no_tier"
        if len(tiers) > 1:
            return "several_tiers"
        return None
    if UNOWNED in labels or DEFERRED in labels:
        return None
    return "off_board"


def _gh(*args: str) -> str:
    """Run `gh` with a fixed argv list; see `fire_scheduled_triggers._gh` for why
    the S603/S607 and B603/B607 suppressions are safe (no issue text reaches the
    command line) and why `encoding="utf-8"` is the correct read for `gh`."""
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


def _flatten(data: object) -> list[dict]:
    """A list of pages or a flat list of issues, minus pull requests."""
    if not isinstance(data, list):
        raise ValueError(f"expected a JSON list, got {type(data).__name__}")
    items = [i for page in data for i in page] if data and isinstance(data[0], list) else data
    return [i for i in items if isinstance(i, dict) and "pull_request" not in i]


def _read_issues(issues_file: str | None) -> list[dict]:
    if issues_file is not None:
        return _flatten(json.loads(Path(issues_file).read_text(encoding="utf-8")))
    repo = os.environ.get("REPO")
    if not repo:
        raise ValueError("REPO is not set and no --issues-file was given")
    raw = _gh("api", "--paginate", "--slurp", f"repos/{repo}/issues?state=open&per_page=100")
    return _flatten(json.loads(raw))


def _fault_line(issue: dict) -> str | None:
    labels = {label["name"] for label in issue.get("labels", [])}
    fault = classify(labels)
    if fault is None:
        return None
    return f"  #{issue['number']}: {_MESSAGES[fault]} -- {issue.get('title', '')}"


def _parse(argv: list[str]) -> tuple[str | None, int | None]:
    issues_file, issue = None, None
    args = list(argv[1:])
    while args:
        flag = args.pop(0)
        if flag == "--issues-file" and args:
            issues_file = args.pop(0)
        elif flag == "--issue" and args:
            issue = int(args.pop(0))
        else:
            raise ValueError(f"unknown or incomplete argument: {flag!r}")
    return issues_file, issue


def main(argv: list[str]) -> int:
    # Issue titles are arbitrary Unicode. On a Windows console the default
    # codec is cp1252, and one title containing an arrow crashed the first
    # live run mid-report -- exit 1, which reads as a verdict. Measured
    # 2026-09-23. The runner is Linux, where this is a no-op.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # Parsed OUTSIDE the read's `try`: a bad argument is a different cause from
    # a failed read, and a guard's message names the cause, not the check.
    try:
        issues_file, only = _parse(argv)
    except ValueError as exc:
        print(f"check-issue-labels: bad argument, nothing was read: {exc}")
        return 2
    try:
        issues = _read_issues(issues_file)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"check-issue-labels: could not read the open issues: {exc}")
        return 2
    if not issues:
        print(
            "check-issue-labels: read ZERO open issues -- could not look, not a clean "
            "board. This repository has open issues; an empty read is a failed read."
        )
        return 2

    ordered = sorted(issues, key=lambda i: i["number"])
    faults = [line for line in (_fault_line(i) for i in ordered) if line]

    if only is not None:
        mine = [i for i in issues if i["number"] == only]
        if not mine:
            print(
                f"check-issue-labels: issue #{only} is not among the {len(issues)} "
                "open issues read -- could not look."
            )
            return 2
        line = _fault_line(mine[0])
        print(
            f"check-issue-labels: standing total, for information: {len(faults)} of "
            f"{len(issues)} open issue(s) break the rule."
        )
        if line:
            print(f"check-issue-labels: issue #{only} breaks the filing rule:\n{line}")
            return 1
        print(f"check-issue-labels: issue #{only} satisfies the filing rule.")
        return 0

    if faults:
        print(
            f"check-issue-labels: {len(faults)} of {len(issues)} open issue(s) "
            "break the filing rule:"
        )
        print("\n".join(faults))
        return 1
    print(
        f"check-issue-labels: clean -- {len(issues)} open issue(s), each on the "
        "board, unowned-with-reason, or post-mvp."
    )
    return 0


if __name__ == "__main__":
    # Duplicated verbatim from the other gates (see check_audit_evidence.py for
    # why it is not shared); tests/unit/test_gate_crash_exit_code.py runs it.
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-issue-labels: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(2) from exc
