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

## And the failure has to reach someone (#531)

Failing loudly was not enough: a scheduled workflow's red X is on no one's
path, and this one was red every week for a month over #145's backticked date.
So a failed run files (or comments on) an issue titled
"Scheduled triggers: the weekly run failed", with the board labels
(`--report-failure`, run by the workflow's `if: failure()` step). And a trigger
that FIRED and then sat untouched for `STALE_AFTER_DAYS` is a problem too: an
item that fires and is ignored is back to being untracked.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import traceback
from datetime import date

LABEL = "scheduled-trigger"
FIRED = "trigger-fired"

# Captures the REST OF THE LINE, not one token. `Trigger-date: October 1 2026`
# must be recognised as a trigger line with a bad value, not as no trigger
# line at all -- the second reads as "you forgot to set one" when it is
# sitting right there, and a natural-language date is exactly what someone
# writes when they mean "later". Found by the test, not by review.
#
# The prefix tolerates markdown decoration before the key -- a bullet, a quote
# marker, backticks, emphasis -- and after the colon (`**Trigger-date:** x`).
# #145's backticked date never matched the bare-key pattern (#531).
# Never \s, on either side of the key: it crosses newlines, so a key would
# match across lines and an empty value would borrow the next line.
_DECOR = r"[ \t>*_`\-]*"
_DATE = re.compile(rf"^{_DECOR}Trigger-date:[*_`]*[ \t]*(.+?)[ \t]*$", re.IGNORECASE | re.MULTILINE)
_REASON = re.compile(
    rf"^{_DECOR}Trigger-reason:[*_`]*[ \t]*(.+?)[ \t]*$", re.IGNORECASE | re.MULTILINE
)
# Anywhere, to name the cause when the key is present but not as a line.
_MENTIONS_DATE = re.compile(r"Trigger-date", re.IGNORECASE)
_MENTIONS_REASON = re.compile(r"Trigger-reason", re.IGNORECASE)

# `gh` stops at `--limit` without saying so (#496). A full page is refused.
LIST_LIMIT = 1000
# A fired trigger untouched this long is reported as ignored (#531).
STALE_AFTER_DAYS = 14
FAILURE_TITLE = "Scheduled triggers: the weekly run failed"


class CouldNotLook(RuntimeError):
    """The run could not read or act on what it needed: exit 2, never 1.

    1 is a finding (an unusable or ignored trigger); 2 is "I could not look",
    the distinction every gate in this repo keeps apart."""


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
        # `encoding` WITHOUT `PYTHONIOENCODING`, which the three sibling sites
        # (`check_gate_fixtures`, `mutation_sweep`, `test_gate_crash_exit_code`)
        # call worse than neither. Stated here because an unexplained
        # difference from three twins reads as an oversight.
        #
        # The remedy does not transfer, because the CHILD decides it:
        #
        #   Python child on Windows  -> writes cp1252, so decoding utf-8 raises
        #                               inside subprocess's reader thread and
        #                               returns an EMPTY capture with a normal
        #                               return code. Both ends must be pinned.
        #   `gh` (a Go binary)       -> writes UTF-8 on every platform. There is
        #                               no writer to pin, and PYTHONIOENCODING
        #                               reaches nothing in a non-Python child.
        #
        # So here `encoding="utf-8"` is the CORRECT read and `text=True` alone
        # is the broken one -- the reverse of the sibling sites. Measured
        # 2026-09-09 on Windows against `gh issue view --json title`, by
        # codepoint rather than by eye, because a console renders both wrongly:
        #
        #   text=True only    -> U+00E2 U+20AC U+201D  (E2 80 94 read as cp1252)
        #   encoding=utf-8    -> U+2014                (EM DASH, correct)
        #
        # This script runs only on `ubuntu-latest`
        # (`.github/workflows/scheduled-triggers.yml`), where UTF-8 is already
        # the default, so the line is belt-and-braces there and load-bearing
        # only for a developer running it on Windows.
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise CouldNotLook(f"gh {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def parse_trigger(body: str) -> tuple[date, str]:
    """The date and reason, or raise.

    Both are required. `Trigger-reason` is what makes the comment actionable --
    a bare "this issue is due" is the kind of reminder that gets muted.

    Markdown decoration around the line is tolerated: a list bullet, a quote
    marker, backticks or emphasis (`` `Trigger-date: 2026-09-22` ``,
    `**Trigger-date:** 2026-09-22`). #145 wrote its date in backticks, the
    old pattern anchored on the bare key, and the weekly run failed on it for
    four weeks with a message that named the check, not the cause (#531).
    """
    body = body or ""
    value = _field(body, "Trigger-date", _DATE, _MENTIONS_DATE, "YYYY-MM-DD")
    reason = _field(body, "Trigger-reason", _REASON, _MENTIONS_REASON, "<why>")
    try:
        return date.fromisoformat(value), reason
    except ValueError as exc:
        raise ValueError(f"`Trigger-date: {value}` is not an ISO date (YYYY-MM-DD)") from exc


def _field(body: str, key: str, line: re.Pattern, mention: re.Pattern, shape: str) -> str:
    """The undecorated value of `key`'s line, or raise naming the CAUSE: no
    line, a line with nothing on it, or the key mentioned only mid-sentence."""
    m = line.search(body)
    if m is not None:
        value = _undecorate(m.group(1))
        if value:
            return value
        raise ValueError(f"`{key}:` has no value on its line: write `{key}: {shape}`")
    if _empty_line(key).search(body):
        raise ValueError(f"`{key}:` has no value on its line: write `{key}: {shape}`")
    if mention.search(body):
        raise ValueError(
            f"mentions `{key}` but not as a line of its own: write "
            f"`{key}: {shape}` on a line by itself"
        )
    raise ValueError(f"labelled `{LABEL}` but has no `{key}:` line")


def _empty_line(key: str) -> re.Pattern:
    return re.compile(rf"^{_DECOR}{key}:[*_`]*[ \t]*$", re.IGNORECASE | re.MULTILINE)


def not_truncated(issues: list[dict], limit: int = LIST_LIMIT) -> list[dict]:
    """The list, or raise if it filled the page: `gh` stops at `--limit` without
    saying so, and an issue past it would never fire (#496)."""
    if len(issues) >= limit:
        raise CouldNotLook(
            f"`gh issue list` returned {len(issues)} issues, the limit: the list may be "
            "truncated, so some triggers would never be read. Raise LIST_LIMIT."
        )
    return issues


def _undecorate(value: str) -> str:
    """The value with markdown decoration stripped from both ends."""
    return value.strip().strip("`*_").strip()


def stale_fired(issues: list[dict], today: date, days: int = STALE_AFTER_DAYS) -> list[str]:
    """Fired triggers nobody has acted on: still open, `trigger-fired`, and with
    no activity for `days` days (#531).

    `updatedAt` moves on any comment, label or edit, and firing itself sets it,
    so an issue last updated `days` ago has seen nothing since it fired. An
    item that fires and is then ignored is back to being untracked, which is
    what the trigger existed to end.
    """
    out = []
    for issue in issues:
        names = {label["name"] for label in issue.get("labels", [])}
        if FIRED not in names:
            continue
        updated = date.fromisoformat(str(issue["updatedAt"])[:10])
        idle = (today - updated).days
        if idle >= days:
            out.append(f"#{issue['number']}: fired and untouched for {idle} days")
    return out


def failure_report(existing: list[dict], log: str | None, run_url: str) -> tuple[str, list[str]]:
    """What to post when a run fails: ("comment", [number, body]) on the open
    tracking issue, or ("create", [title, body]) when there is none (#531).

    A scheduled workflow's red X is on no one's path, which is how this one
    stayed red for four weeks. An issue carrying the board labels is.
    """
    tail = (log or "").strip()
    detail = (
        f"```\n{tail[-3000:]}\n```"
        if tail
        else "The run failed before it wrote its log; the run page has the rest."
    )
    body = f"The weekly scheduled-trigger run failed: {run_url}\n\n{detail}"
    open_ones = [i for i in existing if i.get("title") == FAILURE_TITLE]
    if open_ones:
        return "comment", [str(open_ones[0]["number"]), body]
    return "create", [
        FAILURE_TITLE,
        body + "\n\nOpened by `.github/workflows/scheduled-triggers.yml` on a failed run. "
        "Fix the cause it names, then close this; the next failure opens it again.",
    ]


def _log(line: str) -> None:
    print(line)
    path = os.environ.get("TRIGGER_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def report_failure(log_path: str, *, exercise: bool = False) -> int:
    """`--report-failure LOG`: file or update the tracking issue (#531).

    `exercise=True` (`--exercise-report LOG`, the workflow's dispatch-only
    live test) only ever OPENS its own issue. While a tracking issue is open it
    refuses: commenting "EXERCISE ... close this issue" on a real failure
    record is how a real failure gets closed by someone following instructions.
    """
    repo = os.environ.get("REPO")
    run_url = os.environ.get("RUN_URL", "(run URL not set)")
    if not repo:
        raise CouldNotLook("REPO is not set — refusing to guess which repository.")
    try:
        with open(log_path, encoding="utf-8") as f:
            log = f.read()
    except OSError:
        log = None  # stated in the body rather than inventing a log
    existing = json.loads(
        _gh(
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--search",
            f'in:title "{FAILURE_TITLE}"',
            "--json",
            "number,title",
        )
    )
    action, args = failure_report(existing, log, run_url)
    if exercise and action == "comment":
        raise CouldNotLook(
            f"tracking issue #{args[0]} is open, so the exercise will not run: it only "
            "opens its own issue, and would otherwise comment on a real failure record. "
            f"Resolve and close #{args[0]} first."
        )
    if action == "comment":
        _gh("issue", "comment", args[0], "--repo", repo, "--body", args[1])
        print(f"commented on #{args[0]}")
    else:
        # The board labels at creation: an issue without them is invisible to
        # the only view used to decide what to work on (CLAUDE.md).
        _gh(
            "issue",
            "create",
            "--repo",
            repo,
            "--title",
            args[0],
            "--body",
            args[1],
            "--label",
            "mvp-blocking",
            "--label",
            "tier-3",
        )
        print("opened the tracking issue")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run, and make the CAUSE of every failure that raises reach `TRIGGER_LOG`
    (#531).

    The failure report quotes that log, and `_log` is the only writer to it. So
    without this, a truncation refusal or a `gh` failure reached stderr only,
    and the tracking issue said "the weekly run failed" over a log of success
    lines, or over none. Every refusal in `_main` raises, bad arguments and an
    unset `REPO` included, so each reaches the log. Could-not-look exits 2; a
    finding re-raises (exit 1). A process killed outright writes nothing, and
    the report says the log is missing.
    """
    try:
        return _main(argv)
    except CouldNotLook as exc:
        _log(f"could not look -- {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 2
    except Exception as exc:
        _log(f"{type(exc).__name__}: {exc}")
        raise


def _main(argv: list[str] | None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "--report-failure":
        return report_failure(args[1])
    if len(args) == 2 and args[0] == "--exercise-report":
        return report_failure(args[1], exercise=True)
    if args:
        raise CouldNotLook(f"unknown or incomplete arguments: {args!r}")
    repo = os.environ.get("REPO")
    if not repo:
        raise CouldNotLook("REPO is not set — refusing to guess which repository.")

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
        str(LIST_LIMIT),
        "--json",
        "number,title,body,labels,updatedAt",
    )
    issues = not_truncated(json.loads(raw))
    today = date.today()
    # Stale findings first: they read only the listing, and computing them up
    # front means a `gh` failure mid-loop cannot drop them.
    fired, problems = 0, stale_fired(issues, today)

    try:
        for issue in issues:
            if _fire_if_due(issue, repo, today, problems):
                fired += 1
    except CouldNotLook:
        # Findings already collected are not lost with the run: logged, then
        # the could-not-look goes on to `main`.
        if problems:
            _log("findings collected before the failure:\n  " + "\n  ".join(problems))
        raise

    _log(f"scheduled triggers: {len(issues)} labelled, {fired} fired.")
    if problems:
        message = (
            "issues labelled `scheduled-trigger` with an unusable or ignored trigger:\n  "
            + "\n  ".join(problems)
        )
        raise ValueError(message)  # `main` logs it, once
    return 0


def _fire_if_due(issue: dict, repo: str, today: date, problems: list[str]) -> bool:
    """Comment on and label one issue if its trigger has passed. A malformed
    trigger is appended to `problems`, not raised: one bad issue must not stop
    the others from firing, and `_main` raises them all at the end."""
    number = issue["number"]
    names = {label["name"] for label in issue.get("labels", [])}
    if FIRED in names:
        return False
    try:
        due, reason = parse_trigger(issue.get("body") or "")
    except ValueError as exc:
        problems.append(f"#{number}: {exc}")
        return False
    if due > today:
        return False

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
    _log(f"fired: #{number} ({issue['title'][:60]})")
    return True


if __name__ == "__main__":
    raise SystemExit(main())
