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
`2028f38`; 17 files and 25 lines on this branch, each read and classified.

## Condition 5

This edits `apps/api/scripts/check_*.py`, `leave_row_oracle.py`,
`tests/gates/**`, `apps/api/tests/**` and `.github/workflows/**`: it comes
back to the owner. No behaviour changes; the edits are comments, docstrings,
fixture incident text and the wording of printed messages.
