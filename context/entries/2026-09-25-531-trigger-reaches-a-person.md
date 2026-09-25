# 2026-09-25: a failed scheduled-trigger run reaches a person (#531, #496)

Branch `track1/trigger-reaches-a-person`, branch-start base `c875d62`.

## Why

The weekly `Scheduled triggers` run failed on 2026-08-31, 09-07, 09-14 and
09-21. Each failure had the same cause: #145 wrote its date as
`` `Trigger-date: 2026-09-22` ``, and the pattern anchored on the bare key. The
message said the issue "has no `Trigger-date:` line" while the line was
visibly there. A scheduled workflow's red X is on no one's path, so nobody
looked for four weeks.

#145 has since been closed. The only open labelled issue is #118, which
parses, so the next run is expected green and will not open the tracking
issue.

## What changed

`apps/api/scripts/fire_scheduled_triggers.py`:

- **Decoration tolerated.** A bullet, a quote marker, backticks or emphasis
  around the key or the value is accepted. None of the patterns use `\s`,
  because it crosses newlines.
- **Messages name the cause.** There are four answers, each with its own
  message:
  - no line at all;
  - a line with no value;
  - a value that is only decoration;
  - the key mentioned mid-sentence.

  An empty `Trigger-reason:` used to take the NEXT line as the reason the
  comment would quote. It is now refused as empty.
- **A full page is refused (#496).** `gh issue list --limit` stops at the
  limit without saying so. A list that fills `LIST_LIMIT` (1000) raises
  instead of reading as complete.
- **Ignored triggers are reported.** An issue labelled `trigger-fired`, still
  open and untouched for `STALE_AFTER_DAYS` (14), is reported, and the run
  fails on it. An item that fires and is ignored is back to being untracked.
- **`--report-failure LOG` puts a failure in front of a person.** It comments
  on the open issue titled "Scheduled triggers: the weekly run failed". If
  none is open, it creates one with `mvp-blocking` and `tier-3`, so it is on
  the board. The comment carries the run URL and the tail of the run's log.
  A run that crashed before writing its log says so, rather than pasting
  nothing.
- **Arguments.** An unknown or incomplete argument exits 2.

`.github/workflows/scheduled-triggers.yml`: the run writes `TRIGGER_LOG`, and
an `if: failure()` step runs `--report-failure` on it.

## Verified

- The targeted file passes: 24 tests, in `docker run --rm` of
  `shield-v2-api:latest`.
- Red-on-revert, each mutation's anchor counted before it was applied. Each of
  these turned its named test red:
  - the decoration tolerance;
  - the mid-sentence cause message;
  - the full-page refusal;
  - the stale-fired report;
  - both `failure_report` branches;
  - the argument refusal;
  - `\s` restored after the key;
  - the empty-value check removed.
- `--report-failure` has not been run against GitHub. Its `gh` calls are
  exercised only through `failure_report`'s pure return value, so the first
  real failure is its first live run.

## Limits

- The stale-fired check reads `updatedAt`, which any edit, label or comment
  moves, including a bot's. It can under-report an ignored trigger, never
  over-report one.
- The tracking issue is matched by exact title. A retitled one is not found,
  and a second one is opened.
