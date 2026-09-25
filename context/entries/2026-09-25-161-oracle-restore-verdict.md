# 2026-09-25: the LEAVE-row oracle reports a failed restore on every exit (#161)

Branch `track1/oracle-restore-verdict`, branch-start base `ebdd23d`.

## Why

The oracle's default path writes mutated copies of `redact.py`, the single
LLM egress path, and restores it in a `finally`. It reads the restore back and
prints RESTORE FAILED on a mismatch. But three `return 2` sites sat inside the
`try`:
- an anchor-count mismatch;
- a mutation that will not compile;
- the all-guards-off variant not compiling.

A `return` runs the `finally` and computes the restore verdict, then leaves
before the block that reports it. So a restore that did not take exited 2
with only "did not compile", and said nothing about the redactor being left
mutated. #161 named two of the three sites; the all-guards-off one is the
third.

Not reachable from CI, which runs only the flag checks, and those return
before any write.

## What changed

The three early exits raise a private `_Abort` instead of returning. It is
caught before the `finally`, and control always reaches the restore check.
A failed restore is reported first. Then an aborted run exits 2 with the
cause it already printed where it arose.

## Verified

- `tests/unit/test_leave_row_oracle_restore.py` covers all three early exits,
  in two states each:
  - a restore that silently does not take must print RESTORE FAILED and exit
    2;
  - a restore that works must name only its cause.

  The tests replace `REDACT` with an in-memory fake and never write the real
  file. A fixture hashes the real `redact.py` before and after each test.
- Red-on-revert: with the script put back to `main`'s version, all three
  stuck-restore cases went red, each printing its cause and no RESTORE
  FAILED. The controls stayed green.
- The full oracle was run on this worktree only, end to end: 161 LEAVE rows,
  30 guards, 0/94 unrelated, exit 0. `--check-registry --check-anchors`
  exited 0.
- `redact.py` had the same SHA-256 before and after every run, and
  `git diff --quiet` held.
