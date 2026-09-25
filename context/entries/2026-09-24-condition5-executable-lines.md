# 2026-09-24: condition 5 ignores a diff that changes nothing that runs

Branch `track1/cond5-executable-lines`, branch-start base `20f747f`.

## Why

#530's whole `docker-compose.yml` diff was comments, and it still came back to
the owner under condition 5. The owner's rule: a diff that changes no
EXECUTABLE line in a condition-5 path does not trip condition 5. Comments,
docstrings and landing entries almost never alter behaviour, and the exceptions
(tool directives, a gate that reads comments as wiring) are counted or named,
so the exception is mechanical and can be computed. The status-based narrowing measured earlier
could not be.

## What changed

This section describes the FIRST version. The review sections below supersede
it wherever they differ: YAML and JSON are no longer compared as parsed
objects, and the report is no longer a step of the merge-rule job.

- **`check_condition5.py`**, a new gate.
  - **The path list** is the indented list under `### Condition 5: the paths`
    in CLAUDE.md, which the bullets explain.
  - **Prose is not read.** The first draft read the bullets' backticked
    tokens, and the bullets name paths they EXCLUDE (`apps/web/**`,
    `alembic/`), so every web change would have tripped.
  - **What counts as executable, per file type:**
    - Python: the AST with docstrings removed; a tool-directive comment
      (`noqa`, `nosec`, `test-integrity:`, …) counts.
    - YAML and JSON: the parsed object.
    - Shell: code lines; every line counts if the file has a heredoc.
    - Data, docs, and anything under `gates/` or `fixtures/`: every line.
    - Anything else (TypeScript, binaries): unclassifiable, exit 2, read as
      tripped.
- **`audit-gate.yml`** runs it with `--report`, a step inside the merge-rule
  job. It prints the verdict to the job summary and exits 0 whether or not
  condition 5 trips, because tripping is routing, not a defect. It exits 2
  only when it could not look. There is no pipe into `tee`, which would lose
  the 2 (#213).
- **CLAUDE.md**:
  - condition 5 states the exception;
  - the section carries the list;
  - the measurement table has a column for the new rule;
  - the `_HSPACE` bullet shrinks to its rule plus a D-058 pointer, which pays
    for the additions under the size gate.

## The measurement, against both recorded windows (SUPERSEDED: under the shipped gate the windows are 4/11 and 3/12; see the round-2 section below)

The windows are the 15 most recent PR merges at each date. For 08-26 that is
at `fdfde7d^1`, the commit before D-059 landed; for 09-21 it is at `897eeae`,
with the selector CLAUDE.md records. Each window is scored under condition 5
as it stood that day.

| window | old rule | new rule | newly cleared |
| --- | --- | --- | --- |
| 2026-08-26 | 4 cleared / 11 back | 4 / 11 | none |
| 2026-09-21 | 2 cleared / 13 back | 4 / 11 | `b516891` (compose comments only), `7c2802c` (an `ai/engine.py` docstring only) |

**The old-rule column reproduces both recorded figures exactly**: 4/11 and
2/13. That reproduction is what licenses the new column. The first attempt at
09-21 gave 3/12, because it left out the compose files; they entered condition
5 in `b516891` itself, on 2026-09-19. Both newly cleared diffs were read by
eye: comments only, and a docstring only.

## Proof

- **Fixtures:** 10 cases, including adversarial ones (a `# nosec` edit, a
  heredoc `#` line, a fixture comment, a TypeScript comment, an empty diff).
- **Red-on-revert:** removing the directive check, the heredoc rule or the
  fixtures-are-data rule turns its named unit test red.
- **The list and the prose agree in BOTH directions**: every listed path is
  named in the bullets, and every path the bullets name is listed or is a
  recorded exclusion.

## After the adversarial review of `a9b4a77`

It found ten things, and all were real. What changed:
- **The list is read at the merge base AND the head**, from git. CLAUDE.md is
  not a listed path, so reading only the PR's checkout let one diff delete an
  entry and edit its file. A changed list trips. A base with no readable list
  (today's main) also trips, rather than turning this PR red.
- **The list must be one unbroken run.** A marker inside it used to end the
  read silently. Now an interruption or a split exits 2.
- **`--no-renames`**, so a moved file shows its old, listed path.
- **The workflow-derived set** (every `.py` / `.sh` a `run:` names) is judged
  too. It adds `scripts/red-on-revert.sh` and two others the list does not
  name. (Round 1: compose-invoked scripts were not yet derived. Round 2 derives
  them.)
- **YAML is compared as a node tree** and **JSON with numbers as text**.
  Python equality let `on` become `yes`, `1` become `1.0`, and `1` become
  `true`.
- **Directives** gain `ruff:`, `isort:`, `pyright:` and the encoding cookie,
  and each is compared with its line.
- **The report is its own job**, not a step of the condition-4 job.
- **D-095** records the rule and the refs (`fdfde7d^1`, `897eeae`). The
  classifier clears 4/11 in both windows. The shipped gate, which also trips a
  list change, gives **4/11 and 3/12**: `b516891` added compose to the list.
  The first version said 4/11 for both (corrected after re-review).

Round 1: eight red-on-revert checks, one per fix, each went red on its named test.
A first harness misread them as green: it grepped for a summary line this
pytest config does not print. Every run exited 1 and named its test FAILED.

## Limits

- Scripts reached from sourced files or other scripts, `$VAR` paths and
  lockfile changes are not derived, and no other check covers them (#572).
- A live prompt outside the listed paths still needs a diff read.
- TypeScript and JavaScript are always unclassifiable until there is a lexer.
- CLAUDE.md headroom: run `check_claude_md_size.py`; do not trust a figure here.

## After the re-review of `8cb5248`

- **The base's copy of the gate judges the PR in CI**, never the PR's own
  copy, which ran on the merge ref and could certify itself. With no copy at
  the base, the PR trips. (The round-2 test named for this could not fail:
  it ran the tree's own gate and only compared the base copy. See round 3.)
- **Compose is derived** by mapping command, entrypoint and healthcheck paths
  through the bind mounts, so `sh /app/web-install-if-stale.sh` is
  `scripts/web-install-if-stale.sh`. Compose's `!reset` tag reads as data. A
  dotted name counts as a module only after `-m`: `uvicorn app.main:app` is
  product code.
- **Gate configuration is derived**: the `package.json` files and the
  prettier, eslint, vitest and tsconfig files when a workflow runs a node tool,
  and `pyproject.toml` when one runs pytest, ruff, black or bandit. Twelve
  unlisted files in all.
- `# separator-class:` is a directive.
- **The windows under the SHIPPED gate: 4/11 and 3/12**, not 4/11 twice.
  `b516891` changed the list, which the gate trips. D-095 and the table are
  corrected.
- Filed as #572: the residuals no other check covers, the whitespace blind spot
  in `shell_changed`, and the merge rule's own conditions, which the list does
  not protect.

## After the re-review of `5a25a2a` (round 3)

- **What the base copy does NOT protect, now said plainly** in the workflow
  comment, the gate's docstring, D-095 and the printed report. The workflow is
  the PR's own (`on: pull_request`), so a PR editing that step or this gate is
  not protected by the report. Only branch protection can close that, and it
  is the owner's (#572).
- **The base-copy test now EXECUTES both copies** as subprocesses. The PR's
  rigged copy (`main` returns 0) certifies itself; the base's copy trips the
  same PR. Red on revert: a gate that skipped its own file turns it red.
- **Config is derived by name shape** at the top of the repo, apps/web and
  apps/api: package.json, pnpm-workspace.yaml, conftest.py, tsconfig*.json,
  *.config.*, *.setup.*, *.toml/.ini/.cfg, .prettier*, .eslintrc*. Deeper
  config is a stated residual.
- **Compose mounts are merged across files**, a relative long-syntax source
  resolves, and a command path under a mount that needs interpolation is exit
  2. The live `${GCLOUD_CONFIG_DIR...}` mount is irrelevant, because nothing
  runs from under it, so it does not make the gate refuse every PR.
- **The CI step names each cause**: an unresolvable base ref is exit 2, a base
  with no gate trips, and any other `git show` failure is exit 2.
- The CLAUDE.md marker says the last column was read from the diffs.
- Red on revert: six mutations, each red on its named test.

## After the re-review of `6f9a673` (round 4)

- **The CI step would have exited 2 on EVERY PR after merge.** It ran from
  `apps/api` with `--repo ..`, which names `apps/`, and `git ls-tree` without
  `--full-tree` lists cwd-relative paths, so it found zero workflows.
  Measured: 0 from `apps/`, 5 with `--full-tree`. #559's own CI could not show
  it, because its base has no gate, so that branch trips before python runs.
  Fixed at three layers: the gate resolves `--repo` to the top level, ls-tree
  uses `--full-tree`, and the step passes `--repo ../..`.
- **A test now EXECUTES the step's own script** against a repo whose base has
  the gate, run from `apps/api` as CI does. It gets a verdict both ways (not
  tripped, TRIPPED). Red on revert.
- CLAUDE.md, at condition 5: a PR changing a workflow or the gate is tripped
  whatever its report says (#572). The needs-a-human sentence now says "any
  gate input it does not derive".
- `.gitignore`, `Dockerfile*`, `.dockerignore` and `.babelrc*` are shapes. The
  printed residual is open-ended.
- A compose mount whose TARGET needs interpolation is could-not-look for any
  absolute path in that service.
- The base-copy test has a `--report` variant, asserting the TRIPPED text.
- Red on revert: five mutations, each red.
