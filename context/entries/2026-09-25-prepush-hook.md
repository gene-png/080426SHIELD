# 2026-09-25: the pre-push hook runs, fails closed, and names its bypass

Branch `track1/prepush-hook`, branch-start base `59484a9`. Split out of #563 at
the coordinator's recommendation: every change here alters every developer's
push, including on Windows and PowerShell, and the owner should see that on
its own rather than bundled into a gate PR.

## What changed in `.pre-commit-config.yaml`

- **#143 repaired.** `pytest ... || echo "skipped"` printed "skipped" over a
  FAILING suite and let the push through. The container check is now the `if`,
  and pytest runs unguarded in its branch, so a red suite fails the push.
- **The hook is installed.** `default_install_hook_types: [pre-commit,
  pre-push]`. Every documented install (`.devcontainer/post-create.sh`, the
  agent definitions) is a bare `pre-commit install`, which installs only the
  pre-commit stage, so this hook ran for nobody. **Existing clones must re-run
  `pre-commit install`**: the setting changes new installs only.
- **`default_stages: [pre-commit]`**, so installing the pre-push hook type does
  not also run every commit-time hook (formatters, mypy, gitleaks) over the
  push range. NOT RUN: pre-commit is not installed on the machine this was
  written on. The setting is pre-commit's documented default-stage control.
- **A skip fails closed**, my call and overturnable. pre-commit prints only
  "Passed" or "Failed" on the line people read, so a skip that exits 0 reads
  as Passed. The message names the cause (docker absent, the daemon
  unreachable, the api container down) and the per-hook bypass in both shells:
  Git Bash `SKIP=api-unit-tests git push`, PowerShell
  `$env:SKIP="api-unit-tests"; git push`. Never `--no-verify`, which skips
  every hook.
- **It says which tree it tests**: the one the shared api container mounts,
  which may not be the ref being pushed (#203).

## Measured

With a stub `docker` on PATH, running the hook's own entry:

| state | exit | output |
| --- | --- | --- |
| api up, suite passes | 0 | the #203 tree notice |
| api up, **suite fails** | **1** | the #203 tree notice |
| api container down | 1 | NOT RUN, with the cause and both bypasses |
| Docker daemon unreachable | 1 | NOT RUN, with the cause and both bypasses |
| docker not on PATH | 1 | NOT RUN, with the cause and both bypasses |

The first version printed the PowerShell bypass as `:SKIP=...`, because bash
expanded `$env`. The measurement caught it. The PowerShell form was then RUN
in PowerShell 5.1 on 2026-09-25, and it sets `SKIP` for the following
`git push`.

## Interaction with #563

#563 carries only the minimal #143 repair, because its own gate scans this
hook and would be red on main's `|| echo skipped`. Both PRs edit the same
`entry:` line. Whichever lands second resolves it by taking THIS PR's
version.
