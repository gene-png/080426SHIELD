# 2026-09-25: a failed scheduled-trigger run reaches a person (#531, #496)

Branch `track1/trigger-reaches-a-person`, branch-start base `c875d62`.

## Why

The weekly `Scheduled triggers` run failed on 2026-08-31, 09-07, 09-14 and
09-21. Each failure had the same cause: #145 wrote its date as
`` `Trigger-date: 2026-09-22` ``, and the pattern anchored on the bare key. The
message said the issue "has no `Trigger-date:` line" while the line was
visibly there. A scheduled workflow's red X is on no one's path, so nobody
looked for four weeks.

#145 has since been closed. On 2026-09-25,
`gh issue list --label scheduled-trigger --state open --json number,labels,updatedAt`
returned #118 only, labelled `scheduled-trigger` and `post-mvp`. It is NOT
`trigger-fired`, and it was updated 2026-09-24. So #118 has not fired, the
stale check has nothing to report on it, and its body parses. The next run is
expected green and will not open the tracking issue.

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
  limit without saying so. A list that fills `LIST_LIMIT` (1000) is
  could-not-look, and is not read as complete.
- **Ignored triggers are reported.** An issue labelled `trigger-fired`, still
  open and untouched for `STALE_AFTER_DAYS` (14), is reported, and the run
  fails on it. An item that fires and is ignored is back to being untracked.
- **The cause of every failure that raises reaches the log.** `main` catches
  any exception, writes its type and message to `TRIGGER_LOG`, and then:
  - exits 2 for could-not-look;
  - re-raises a finding, which exits 1.

  Every refusal raises, so every refusal reaches the log. That covers:
  - bad arguments;
  - an unset `REPO`;
  - the truncation refusal;
  - a `gh` failure.

  Before this, only `_log` wrote the log. A refusal or a `gh` failure reached
  stderr alone, so the tracking issue would have said "the weekly run failed"
  over a log with no cause in it. A process killed outright writes nothing,
  and the report then says the log is missing.
- **Findings survive a mid-run `gh` failure.** Stale findings are computed from
  the listing before any issue is acted on. If `gh` fails partway through the
  loop, the findings collected so far are logged before the run exits 2.
- **`--report-failure LOG` puts a failure in front of a person.** It comments
  on the open issue titled "Scheduled triggers: the weekly run failed". If
  none is open, it creates one with `mvp-blocking` and `tier-3`, so it is on
  the board. The comment carries the run URL and the tail of the log.
- **`--exercise-report LOG` only ever opens its own issue.** It is the same
  report, for the workflow's dispatch-only live test. While a tracking issue
  is open, it exits 2 and names that issue, instead of commenting "EXERCISE
  ... close this issue" on a real failure record.
- **Arguments.** An unknown or incomplete argument exits 2.

`.github/workflows/scheduled-triggers.yml`:

- The run writes `TRIGGER_LOG`, and an `if: failure()` step runs
  `--report-failure` on it.
- If that step itself fails, the run is red and reported to nobody, which was
  the state before this change. The workflow says so beside the step.
- A dispatch input, `exercise_failure_report`, runs `--exercise-report` once,
  live, with a log that says EXERCISE.

## Verified

- The targeted file passes: 36 tests, in `docker run --rm` of
  `shield-v2-api:latest`.
- Wiring is tested through `main()`, with `_gh` replaced by one serving
  `issue list`. The `gh`-failure case keeps the real `_gh` and replaces only
  `subprocess.run`.
- Red-on-revert: each mutation's anchor was counted before it was applied, and
  each turned its named test red. The mutations were:
  - the decoration tolerance;
  - the mid-sentence cause message;
  - the pure full-page refusal;
  - the pure stale-fired report;
  - both `failure_report` branches;
  - the argument refusal;
  - `\s` restored after the key;
  - the empty-value check removed;
  - the truncation refusal's call in `main`;
  - the stale check's call in `main`;
  - `--limit` drifting from the refusal;
  - the cause-logging lines, one for each branch;
  - could-not-look returning 1;
  - the exercise refusal;
  - the `--exercise-report` dispatch;
  - the board labels on create;
  - logging findings before a mid-loop failure;
  - bad arguments bypassing the log.
- The report has not been run against GitHub. Its `gh` calls have no live
  run behind them until someone dispatches `exercise_failure_report`, or a
  real failure happens.

## Limits

- The stale-fired check reads `updatedAt`, which any edit, label or comment
  moves, including a bot's. It can under-report an ignored trigger, never
  over-report one.
- The tracking issue is matched by exact title. A retitled one is not found,
  and a second one is opened.
- A `gh` failure while acting (commenting, labelling) exits 2, the same as one
  while reading. Some triggers may already have fired in that run. The log
  lists each `fired:` line and the findings written before the failure.
