"""Every OPEN issue is on the board, in exactly one place, or says why it is not.

CLAUDE.md's filing rule: every new issue carries `mvp-blocking` plus one of
`tier-1` / `tier-2` / `tier-3`, OR `unowned-with-reason` with the reason in the
body. The board is `is:issue is:open label:mvp-blocking` ordered by tier, so an
issue without `mvp-blocking` is not on it, and one with it and no tier "has no
place in the ordering". Either way it is invisible to the only view used to
decide what to work on. The rule was written down and nothing enforced it.

`post-mvp` is a third state the rule does not name. Until it does, an issue that
carries `post-mvp` and nothing else is reported as off the board, with the label
named in the message so the reader knows which case it is.

Exit codes, per this repo's gate convention:
  0  every open issue satisfies the rule
  1  at least one does not (each is listed)
  2  could not look: REPO unset, `gh` failed, or zero issues came back

Lives under `apps/api/scripts` for the reason `fire_scheduled_triggers.py`
does: the api container mounts only `apps/api`, so it can be unit-tested.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

BOARD = "mvp-blocking"
UNOWNED = "unowned-with-reason"
TIERS = ("tier-1", "tier-2", "tier-3")

_MESSAGES = {
    "no_tier": f"carries `{BOARD}` but no tier, so it has no place in the ordering",
    "several_tiers": f"carries `{BOARD}` and more than one tier",
    "off_board": f"carries neither `{BOARD}` + a tier nor `{UNOWNED}`, so it is not on the board",
}


def classify(labels: set[str]) -> str | None:
    """The rule's verdict on one issue's labels: None, or the fault's key."""
    if UNOWNED in labels:
        return None
    if BOARD not in labels:
        return "off_board"
    tiers = [t for t in TIERS if t in labels]
    if not tiers:
        return "no_tier"
    if len(tiers) > 1:
        return "several_tiers"
    return None


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


def _open_issues(repo: str) -> list[dict]:
    """Every open issue, every page. `--paginate --slurp` returns one JSON array
    of pages; the REST endpoint includes pull requests, which are dropped."""
    raw = _gh("api", "--paginate", "--slurp", f"repos/{repo}/issues?state=open&per_page=100")
    pages = json.loads(raw)
    return [i for page in pages for i in page if "pull_request" not in i]


def main() -> int:
    # Issue titles are arbitrary Unicode. On a Windows console the default
    # codec is cp1252, and one title containing an arrow crashed the first
    # live run mid-report -- exit 1, which reads as a verdict. Measured
    # 2026-09-23. The runner is Linux, where this is a no-op.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    repo = os.environ.get("REPO")
    if not repo:
        print("check-issue-labels: REPO is not set -- could not look.", file=sys.stderr)
        return 2
    try:
        issues = _open_issues(repo)
    except (RuntimeError, ValueError) as exc:
        print(f"check-issue-labels: could not read the open issues: {exc}", file=sys.stderr)
        return 2
    if not issues:
        print(
            "check-issue-labels: read ZERO open issues -- could not look, not a clean "
            "board. This repository has open issues; an empty read is a failed read.",
            file=sys.stderr,
        )
        return 2

    faults = []
    for issue in sorted(issues, key=lambda i: i["number"]):
        labels = {label["name"] for label in issue.get("labels", [])}
        fault = classify(labels)
        if fault is not None:
            extra = (
                " (carries `post-mvp`, a state the rule does not name)"
                if "post-mvp" in labels
                else ""
            )
            faults.append(f"  #{issue['number']}: {_MESSAGES[fault]}{extra} -- {issue['title']}")

    if faults:
        print(
            f"check-issue-labels: {len(faults)} of {len(issues)} open issue(s) break the filing rule:"
        )
        print("\n".join(faults))
        return 1
    print(
        f"check-issue-labels: clean -- {len(issues)} open issue(s), each on the board or unowned-with-reason."
    )
    return 0


if __name__ == "__main__":
    # Duplicated verbatim from the other gates (see check_audit_evidence.py for
    # why it is not shared); tests/unit/test_gate_crash_exit_code.py runs it.
    try:
        raise SystemExit(main())
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-issue-labels: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(2) from exc
