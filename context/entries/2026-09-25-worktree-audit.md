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
  - `EDITED`: the branch changed it, and main has not changed it since the
    branch point. Every difference from main is the branch's own edit, which
    may add rules or remove them;
  - `EDITED+STALE`: both;
  - `MISSING`.

  Each line also gives how far behind main the tree is, its uncommitted
  changes, and its size against the 150,000-byte limit. It also says whether
  its last non-empty line matches main's (`last-line=same` or
  `differs-from-main`, with CR stripped). That is a comparison with main, not
  a truncation verdict. **Main's tip still ends with the v1 canary**
  (`<!-- CLAUDE-MD-CANARY: v1 -->`, at `c875d62`). Once #604 lands, every tree
  cut before it will read `differs-from-main` without being truncated.

  The closing count keeps trees read, `GONE` trees (not read) and trees it
  could not read apart.
- **`--check <path>`**: the pre-dispatch refusal #439 asks for. It exits 0 for
  `SAME` or `EDITED`, 1 for `STALE`, `EDITED+STALE` or `MISSING`, and 2 when it
  could not look. It resolves the main ref in the repository it is run from and
  prints that commit. It refuses with 2 when the target resolves the ref
  differently, so a separate, stale clone cannot read `SAME` against its own
  main.

  A tree whose `CLAUDE.md` history cannot be read is 2. It is never `MISSING`
  or `EDITED+STALE`: "absent" and "unreadable" are separate branches.
- **`--self-test`** builds throwaway repositories and requires each exit code
  and output for these cases:
  - each state;
  - an unreadable HEAD tree;
  - an unreadable merge-base tree;
  - a non-git path;
  - a clone with another main;
  - the report's counts.

  The merge-base case is the one that pins `blob()`. With HEAD's tree gone,
  `git status` fails first, so the HEAD case passes even with `blob()` folding
  errors away. Reverting `blob()` to that folding turns the merge-base case red
  as a confident `EDITED+STALE`, exit 1. Removing the main-ref comparison turns
  the clone case red as `SAME`.

## Measured

The first read-only run was on 2026-09-25 against `origin/main` at `2028f38`.
It read 325 worktrees.

The second run was the same day, against `c875d62`, with this revision. It
exited 0 and read 332 worktrees: 0 gone and 0 unreadable.

| state | at `2028f38` | at `c875d62` |
| --- | --- | --- |
| `STALE` | 220 | 220 |
| `EDITED+STALE` | 57 | 57 |
| `SAME` | 32 | 37 |
| `EDITED` | 16 | 18 |

So 277 would give an agent rules main no longer has. At `c875d62`, 132 trees
read `last-line=differs-from-main`.

## Limits

- It compares `CLAUDE.md` only. `.claude/agents/*.md` go stale the same way.
- `--check` judges the rules only, not the size or the last line.
- `--self-test` does not cover `MISSING`, `GONE`, `OVER-LIMIT` or the
  last-line comparison.
- No workflow runs the self-test.

  These last three are #614.
- It reads the main ref as it is locally, so fetch first.
- Nothing calls `--check` yet. Wiring it into agent dispatch is the part #439
  still owes, and it is left open there.
