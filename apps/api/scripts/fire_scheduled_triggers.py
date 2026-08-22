"""Post a comment on any `scheduled-trigger` issue whose date has passed.

Lives beside `check_audit_evidence.py` and `check_issue_references.py` rather
than under `.github/`, for the same reason they do: the api container mounts
only `apps/api`, so a script outside it cannot be unit-tested at all.

Stdlib + `gh` only, matching the other checks in this repo: no model in the loop,
no dependencies, and it does exactly one thing.

## Why this exists

"Post-MVP", "later" and "deferred" are not triggers. Nothing observes them, so
nothing fires, and the item is rediscovered by accident or not at all. This repo
already has several in that state, and the pattern that put them there is the one
D-051 recorded for the §14 gate: a rule depending on someone remembering has
failed here nine recorded times.

So an issue that is genuinely deferred carries its own alarm clock:

    Trigger-date: 2026-10-01
    Trigger-reason: MVP item 8 is the last one; this opens when it merges.

`Trigger-reason` is required and is not decoration. A date with no reason
produces a comment nobody can act on, which is how a reminder becomes noise and
then gets muted.

## What it deliberately does not do

It does not reopen, reprioritise, relabel-as-urgent, or block anything. It posts
once and applies `trigger-fired`, which is also the idempotency guard. A human
still decides. What changes is that the decision is put in front of them on a
known date instead of waiting to be stumbled over.

FAIL LOUDLY: a malformed `Trigger-date` raises rather than being skipped. A
silently ignored alarm clock is worse than none, because the label implies one is
set.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date

LABEL = "scheduled-trigger"
FIRED = "trigger-fired"

# Captures the REST OF THE LINE, not one token. `Trigger-date: October 1 2026`
# must be recognised as a trigger line with a bad value, not as no trigger
# line at all -- the second reads as "you forgot to set one" when it is
# sitting right there, and a natural-language date is exactly what someone
# writes when they mean "later". Found by the test, not by review.
_DATE = re.compile(r"^\s*Trigger-date:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_REASON = re.compile(r"^\s*Trigger-reason:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def _gh(*args: str) -> str:
    """Run `gh` with a fixed argv list.

    S603/S607 and bandit B603/B607 are suppressed with cause, not waved through:
    every argument comes from this file or from `REPO`, which GitHub Actions sets
    — never from issue text, which is the untrusted input those rules exist for.
    Issue bodies are only ever READ (`parse_trigger`) and passed as a single
    `--body` value, never interpolated into a command line. `shell=False` is the
    default here and is what makes that true.

    A full path is not pinned because `gh` is provided by the runner image and
    its location is not ours to assume. CLAUDE.md records that ruff's `noqa` does
    NOT suppress bandit, so both markers are present deliberately.
    """
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


def parse_trigger(body: str) -> tuple[date, str]:
    """The date and reason, or raise.

    Both are required. `Trigger-reason` is what makes the comment actionable --
    a bare "this issue is due" is the kind of reminder that gets muted.
    """
    dm = _DATE.search(body or "")
    if dm is None:
        raise ValueError(f"labelled `{LABEL}` but has no `Trigger-date:` line")
    rm = _REASON.search(body or "")
    if rm is None:
        raise ValueError(f"labelled `{LABEL}` but has no `Trigger-reason:` line")
    try:
        return date.fromisoformat(dm.group(1)), rm.group(1)
    except ValueError as exc:
        raise ValueError(f"`Trigger-date: {dm.group(1)}` is not an ISO date (YYYY-MM-DD)") from exc


def main() -> int:
    repo = os.environ.get("REPO")
    if not repo:
        print("REPO is not set — refusing to guess which repository.", file=sys.stderr)
        return 2

    raw = _gh(
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "open",
        "--label",
        LABEL,
        "--limit",
        "100",
        "--json",
        "number,title,body,labels",
    )
    issues = json.loads(raw)
    today = date.today()
    fired, problems = 0, []

    for issue in issues:
        number = issue["number"]
        names = {label["name"] for label in issue.get("labels", [])}
        if FIRED in names:
            continue
        try:
            due, reason = parse_trigger(issue.get("body") or "")
        except ValueError as exc:
            # Collected, not raised inline: one malformed issue must not stop the
            # others from firing. Raised at the end so it cannot pass silently.
            problems.append(f"#{number}: {exc}")
            continue
        if due > today:
            continue

        _gh(
            "issue",
            "comment",
            str(number),
            "--repo",
            repo,
            "--body",
            (
                f"**Scheduled trigger fired** — this was deferred to `{due.isoformat()}`, "
                f"which has passed.\n\n> {reason}\n\n"
                "Nothing has been reopened, reprioritised or blocked. This is the "
                "alarm clock the issue set for itself, so the decision lands on a "
                "known date instead of being rediscovered by accident.\n\n"
                "Act on it or push the date out deliberately by editing "
                "`Trigger-date:` and removing the `trigger-fired` label — but do "
                "one of the two, because an item that fires and is ignored is back "
                "to being untracked."
            ),
        )
        _gh("issue", "edit", str(number), "--repo", repo, "--add-label", FIRED)
        print(f"fired: #{number} ({issue['title'][:60]})")
        fired += 1

    print(f"scheduled triggers: {len(issues)} labelled, {fired} fired.")
    if problems:
        raise ValueError(
            "issues labelled `scheduled-trigger` with an unusable trigger:\n  "
            + "\n  ".join(problems)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
