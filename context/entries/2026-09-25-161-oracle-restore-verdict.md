# 2026-09-25: the LEAVE-row oracle never writes redact.py (#161)

Branch `track1/oracle-restore-verdict`, branch-start base `ebdd23d`.

## Why

The oracle's default path wrote each guard's mutation into `redact.py`, the
single LLM egress path. It reloaded the module and restored the file in a
`finally`. #161 found that three early `return 2` sites skipped the report of
a failed restore.

Review of the first fix (`c85465b`) found that a restore which RAISES was not
reported either, and that a truncating write could leave the file EMPTY. It
also found the root. `redact.py` is the file the api container bind-mounts,
and `uvicorn --reload` serves it live. In live LLM mode, a Run-AI during an
oracle run would egress through a redactor with a guard removed.

## What changed: the write is gone, not guarded

This is the coordinator's option 3, done in this PR because it proved small.
`_evaluate(rows, source)` compiles `source` into a module of its own (never
`app.ai.redact`), registered in `sys.modules` only while it runs. The default
path reads `redact.py` once and evaluates every variant from memory:
- the baseline;
- each guard;
- all guards off;
- all but one.

Nothing is written, so there is nothing to restore. The restore machinery and
the `_Abort` sentinel from the first fix are removed, and the early exits
return 2 directly. The coordinator's findings 1 and 2 (the raising restore,
and `read_text` against `read_bytes`) describe code that no longer exists.

## Verified

- **Equivalence.** I captured the full default-path output of the
  file-writing oracle (`c85465b`, 71 lines), then ran the in-memory version.
  `diff` found the two outputs IDENTICAL: every per-guard flip count, the
  all-off count (94), the classification and `0/94` unrelated.
- **New tests** (`test_leave_row_oracle_in_memory.py`, replacing the restore
  tests). `REDACT` is a read-only proxy whose `write_text` raises, and a
  fixture hashes the real file before and after. They check:
  - the whole default path over real rows makes zero writes;
  - a mutated variant is what gets evaluated, while `app.ai.redact` stays the
    same object and behaves the same;
  - a mutation that will not compile gives exit 2, with no write and no
    leftover module.
- **Red-on-revert.** All three new tests are red against BOTH file-writing
  versions (`main`'s and `c85465b`). `redact.py` stayed identical even then,
  because the proxy intercepted the writes.
- **The other paths.** The four oracle test files pass,
  `--check-registry --check-anchors` exits 0, and the crash-exit test passes.
- `redact.py` had the same SHA-256 and was clean by `git diff --quiet` after
  every run.

## A bad intermediate commit, recorded

Commit `66c7d36` on this branch deletes the old test file and nothing else,
under a message describing the whole change. A `git add` in the chain failed
on a path already staged by `git rm`, and the commit went ahead anyway. It was
caught by reading `git status` after the push, not by the exit code. The
following commit carries the change; the squash merge folds both together.
