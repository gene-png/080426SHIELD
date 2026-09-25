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
- **Main is resolved once.** Report and `--check` resolve the main ref to a
  commit once, and every tree is classified against that SHA. A fetch landing
  mid-run cannot move main between two trees.
- **Inherited repository overrides are cleared, for every mode.** At the top
  of the script, beside `set -euo pipefail`, it unsets six variables:
  `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_COMMON_DIR`,
  `GIT_OBJECT_DIRECTORY` and `GIT_ALTERNATE_OBJECT_DIRECTORIES`. git gives
  them precedence over `-C`, and a hook exports `GIT_DIR`. From a hook, the
  self-test would otherwise have committed its scratch files into the
  repository `GIT_DIR` names, and every `-C <tree>` would have read that one
  repository.
- **`--self-test` runs in a clean environment.** Report and `--check` read
  other people's trees under their own config. The self-test builds its own
  scratch repositories, and must not run anyone's hooks, templates, signing,
  fsmonitor or `git config` target on them.

  So `--self-test` re-executes itself as `--self-test-inner` under `env -i`,
  passing only `PATH`, `HOME` and `TMPDIR` (both inside a fresh scratch root),
  `GIT_CONFIG_NOSYSTEM=1`, and its own two variables. That drops every
  inherited variable at once, including ones nobody has listed: this replaced
  an enumeration that each review round found one entry short. `SYSTEMROOT`
  was measured NOT needed (2026-09-25, Git Bash). If a platform does need
  something, the self-test fails loudly.

  **This clean environment, with `HOME` inside it, is the load-bearing
  layer.** The second layer is per command: `-c core.hooksPath=<an empty
  dir>`, `-c commit.gpgsign=false`, `--local` on every `config`, and
  `--template=` on `init` and `clone`. That covers hooks and signing only; it
  does nothing for `core.fsmonitor`.

  `--self-test-inner` refuses (exit 2) unless the re-exec set its marker.
  The scratch roots are removed by EXIT traps, so a `set -e` death still
  cleans up.

  Deliberate bare-git exceptions:
  - the hostile-config probe, which must run under the hostile `HOME`;
  - the script's own children (report and `--check`), which are the thing
    under test and run as a caller would.
- **`--self-test`** builds throwaway repositories and requires each exit code
  and output for these cases:
  - each state;
  - an unreadable HEAD tree;
  - an unreadable merge-base tree;
  - a non-git path;
  - a clone with another main;
  - the report's counts;
  - `--check` under an inherited `GIT_DIR` and `GIT_INDEX_FILE`;
  - a nested self-test under an inherited `GIT_DIR` and `GIT_INDEX_FILE`;
  - a nested self-test under a hostile global config;
  - a nested self-test under an inherited `GIT_CONFIG`.

  The merge-base case is the one that pins `blob()`. With HEAD's tree gone,
  `git status` fails first, so the HEAD case passes even with `blob()` folding
  errors away. Reverting `blob()` to that folding turns the merge-base case red
  as a confident `EDITED+STALE`, exit 1. Removing the main-ref comparison turns
  the clone case red as `SAME`.

  `--check` under an inherited `GIT_DIR` pins the `unset` at the top of the
  script. A sentinel scratch repository stands in for the hook's repository.
  With the `unset` removed, `--check` read the sentinel in place of the
  target.

  The nested `GIT_DIR` case requires the sentinel's HEAD, commit count, index
  bytes and status (read with `--no-optional-locks`) to be unchanged.

  The hostile global config sets four things:
  - `core.hooksPath` to hooks that create a marker file outside every scratch
    repo;
  - `init.templateDir` to the same hooks;
  - `core.fsmonitor` to a program that creates a second marker;
  - `commit.gpgsign` to true.

  The case first proves the fixture is live. A bare commit under that `HOME`,
  with the `-c` layer on, must still run the fsmonitor, which shows that `-c`
  alone does not cover it.

  The `GIT_CONFIG` case names a file that `git config` would write to, and
  requires it unchanged. The two are separate nested runs, so each signal is
  seen on its own.

  Red-on-revert, run on scratch copies:
  - with `env -i` removed, the hostile-config run passed while the fsmonitor
    ran, and the `GIT_CONFIG` run died at exit 129: both red;
  - with the `unset` removed, the `--check` case was red.

  The nested cases skip themselves inside a nested run, to avoid recursion. A
  caller exporting `WORKTREE_AUDIT_NESTED` gets the same skips, printed as
  `skip`, and they are left out of the closing `self-test ok` line. None is
  ever pointed at a real repository.

  Classifying against the resolved SHA is not pinned by a test, because the
  race needs a fetch to land mid-run.

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

So 277 would give an agent rules main no longer has.

A third run, with the `GIT_DIR` fix, went against `514e79c`. It exited 0 and
read 334 worktrees, with 0 gone and 0 unreadable. The stale count was still
277: `SAME` rose to 39, and the other states were unchanged. At `c875d62`, 132 trees
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
