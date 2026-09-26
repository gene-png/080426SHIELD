# 2026-09-25: check_decision_numbers reads the repository, not the working directory (#524)

Branch `track1/decision-numbers-cwd`, branch-start base `ebdd23d`.

## Why

`check_decision_numbers.py` resolved its `DECISIONS.md` pathspec against the
current directory. From `apps/api`, where every other gate runs, the path
matched nothing. The gate then reported "no commit touches DECISIONS.md" and
exited 0, over a real mismatch. That is the silent-success shape: "I could not
look" sharing a branch with "nothing to complain about".

It was latent, because `audit-gate.yml` runs the gate from the root. But
nothing pinned that. Moving the step to `working-directory: apps/api`, to
match its neighbours, would have made it pass everything.

## What changed

- Every git call now runs with `-C <toplevel>`, and `--file` is relative to
  the repository root.
- A `--file` that cannot be read at the head is exit 2 (could not look). No
  commit can touch a path that is not there. The message names both causes:
  the path is absent, or the head ref does not resolve.
- Not inside a repository, or no git, is exit 2 at the first call.
- The clean and no-commit lines name the root they read under.

## Verified

- Three new tests, red on the old code:
  - a mismatch caught from a subdirectory;
  - a consistent commit read (not skipped) from a subdirectory;
  - an absent `--file` giving exit 2.

  They need git, so they skip in the api container and run on the host and in
  CI.
- Red-on-revert, 2 of 2:
  - git running from the cwd again;
  - the existence check removed.
- `test_gate_crash_exit_code.py` passes for this gate, and
  `check_gate_fixtures` is clean.
- Run from the repo root and from `apps/api`, the gate gives the same line and
  the same root.
