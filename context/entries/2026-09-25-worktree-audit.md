# 2026-09-25: which worktrees would give an agent stale rules (#439)

Branch `track1/worktree-audit`, branch-start base `2028f38`.

## Why

Every worktree carries its own `CLAUDE.md`, frozen where it was cut, and an
agent dispatched into one reads that copy. #439 measured 131 worktrees on
2026-09-22, most carrying a copy that hid rules fixed on `main`, and nothing
said which trees were stale.

## What changed

`scripts/worktree-audit.sh`, report-only. It removes, prunes and edits
nothing, because most worktrees belong to other sessions. Even `git status`
runs with `--no-optional-locks`, so it cannot write another session's index.

- **Report mode** (no arguments): one line per worktree. It compares the
  tree's committed `CLAUDE.md` blob with the main ref's and with the one at
  their merge base, and gives one of these states:
  - `SAME`;
  - `STALE`: the branch never touched it, and main moved;
  - `EDITED`: the branch changed it, and main did not move;
  - `EDITED+STALE`: both;
  - `MISSING`.

  Each line also gives how far behind main the tree is, its uncommitted
  changes, its size against the 150,000-byte limit, and whether it ends with
  the canary main currently ends with. That canary is read from main, not
  hardcoded.
- **`--check <path>`**: the pre-dispatch refusal #439 asks for. It exits 0
  for `SAME` or `EDITED`, 1 for `STALE`, `EDITED+STALE` or `MISSING`, and 2
  when it could not look.
- **`--self-test`** builds a throwaway repository with worktrees in each state
  and requires each exit code, the could-not-look case and the report's
  counts.

## Measured

The first read-only run was on 2026-09-25 against `origin/main` at
`2028f38`, and exited 0. It read 325 worktrees and could not read 0:

| state | worktrees |
| --- | --- |
| `STALE` | 220 |
| `EDITED+STALE` | 57 |
| `SAME` | 32 |
| `EDITED` | 16 |

So 277 would give an agent rules main no longer has.

## Limits

- It compares `CLAUDE.md` only. `.claude/agents/*.md` go stale the same way.
- A missing directory is reported as `GONE`, not compared.
- It reads the main ref as it is locally, so fetch first.
- Nothing calls `--check` automatically yet. Wiring it into agent dispatch is
  the part #439 still owes, and it is left open there.
