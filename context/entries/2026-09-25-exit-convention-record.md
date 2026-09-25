# 2026-09-25: the gates' exit convention gets its own record (D-090, #553)

Branch `track1/exit-convention-record`, branch-start base `2028f38`.

## Why

The gates' 0 / 1 / 2 convention (clean, a violation, could not look) was cited
as D-051 across the gate scripts, their fixtures and tests. D-051 is the #72
two-tier sweep and does not state it. A reader told to verify what they read
would open D-051, not find the rule, and could discard a rule that is right.

## What changed

- **D-090** records the convention, the silent-success step that goes with it,
  and why the record exists.
- **Citations meaning the convention now cite D-090**: gate docstrings, every
  crash handler's message, could-not-look messages, fail-closed fixture
  incidents, could-not-look unit tests, and two workflow and shell comments.
  CLAUDE.md's fail-closed bullet cites it.
- **Citations meaning what D-051 decided keep it** (tests that cannot fail,
  #72; a rule that depends on remembering needs a mechanism), and sentences
  recording that a gate once cited D-051 keep the history and name both.

## Measured

`git grep -c "D-051" -- ':!DECISIONS.md'`: 47 files and 79 lines on `main` at
`2028f38`; 17 files and 25 lines on this branch before its first commit
(this landing entry adds hits of its own; D-090 is in DECISIONS.md, which the
command excludes). A later re-run is below.

## Condition 5

This edits `apps/api/scripts/check_*.py`, `leave_row_oracle.py`,
`tests/gates/**`, `apps/api/tests/**` and `.github/workflows/**`: it comes
back to the owner. No behaviour changes; the edits are comments, docstrings,
fixture incident text and the wording of printed messages.

## After the first review (`e034c56`)

- D-090 now separates what is enforced from what is required. The crash half
  holds for the gates in `test_gate_crash_exit_code.GATES`
  (`check_gate_fixtures.py` excludes itself and prints its own crash line).
  "A clean result says what it read" is a requirement; the gates that do not
  meet it yet (`check_audit_evidence.py`, `check_issue_references.py`) are
  named and filed as #592.
- `context/entries/2026-09-24-540-ci-selection-gate.md` cited the convention
  as D-051; it cites D-090.
- `check_audit_evidence.py`'s docstring said the gate does not block a merge,
  false since D-054's correction. It now points at D-054 and states the
  admin setting as measured on 2026-09-25 (`enforce_admins` is `true`: no
  admin bypass of required checks), with the command. The first fix said
  `false`, which the owner had changed that week; the other present-tense
  copies of that claim predate this PR and are filed as #595.
  `DELIVERY_PLAN.md`'s #108 note is date-qualified to match.
- The DEFERRED example subject is a placeholder (`D-NNN -- supersedes
  D-MMM`), not a real-looking number.

**The sweep, re-run at `4c8e4d3`**, 2026-09-25:
`git grep -c "D-051" -- ':!DECISIONS.md'` gave 16 files and 28 lines, not
counting this paragraph's own hits. Every hit was read and classified:

- **D-051's own subject** (tests that cannot fail, #72; a rule that depends on
  remembering needs a mechanism; D-051's in-entry correction style):
  `CLAUDE.md`, `CONTEXT.md`, `DELIVERY_PLAN.md` (the W8a row, the W8b notes),
  `check_plan_totals.py`, `check_recalled_counts.py`,
  `scheduled-triggers.yml`, `fire_scheduled_triggers.py`, the
  `check_test_integrity` fixture, two test files, and `context/gene.md`.
- **History**, a sentence recording what was once cited: `audit-gate.yml`'s
  correction note, `DELIVERY_PLAN.md`'s #108 note, and the separator gate's
  comment, test docstring and fixture, each naming both records.
- **This change's own record**: this entry.

None cites D-051 for the exit convention.
