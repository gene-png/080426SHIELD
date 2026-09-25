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
- **Git config is isolated, in `--self-test` only.** Report and `--check` read
  other people's trees under their own config.

  Inside `self_test`, the script:
  - sets `HOME` to a directory under the scratch dir, which drops the global
    config (`GIT_CONFIG_GLOBAL=/dev/null` is rewritten by MSYS under Git
    Bash);
  - exports `GIT_CONFIG_NOSYSTEM=1`;
  - unsets `GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`, `GIT_CONFIG_GLOBAL`,
    `GIT_CONFIG_SYSTEM`, `XDG_CONFIG_HOME` and every
    `GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n`.

  Every git command in the self-test also runs with
  `-c core.hooksPath=<an empty dir>` and `-c commit.gpgsign=false`. Every
  `init` and `clone` passes `--template=`.
- **`--self-test`** builds throwaway repositories and requires each exit code
  and output for these cases:
  - each state;
  - an unreadable HEAD tree;
  - an unreadable merge-base tree;
  - a non-git path;
  - a clone with another main;
  - the report's counts;
  - an inherited `GIT_DIR` and `GIT_INDEX_FILE`;
  - a hostile global git config.

  The merge-base case is the one that pins `blob()`. With HEAD's tree gone,
  `git status` fails first, so the HEAD case passes even with `blob()` folding
  errors away. Reverting `blob()` to that folding turns the merge-base case red
  as a confident `EDITED+STALE`, exit 1. Removing the main-ref comparison turns
  the clone case red as `SAME`.

  The inherited-override case runs a nested self-test with `GIT_DIR` and
  `GIT_INDEX_FILE` pointed at a sentinel scratch repository. It then requires
  the sentinel's HEAD, commit count, index bytes and status (read with
  `--no-optional-locks`) to be unchanged. Reverting the `unset` in a scratch
  copy turned it red: the sentinel gained a commit.

  The hostile-config case runs a nested self-test under a `HOME` whose
  `.gitconfig` sets three things:
  - `core.hooksPath` to hooks that create a file outside every scratch repo;
  - `init.templateDir` to the same hooks;
  - `commit.gpgsign` to true.

  It requires the nested run to pass and the file never to appear. It first
  proves the fixture is live: a plain commit under that `HOME` must fire the
  hook.

  The isolation has two layers, `HOME`/`GIT_CONFIG_NOSYSTEM` and the
  per-command `-c` and `--template=`, and each suffices on its own. Reverting
  either alone left the case green. Reverting both turned it red: the hook ran,
  and signing was attempted and failed.

  Both nested cases skip themselves inside a nested run, to avoid recursion.
  A caller exporting `WORKTREE_AUDIT_NESTED` gets the same skips, printed as
  `skip`, and they are left out of the closing `self-test ok` line. Neither
  case is ever pointed at a real repository.

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
