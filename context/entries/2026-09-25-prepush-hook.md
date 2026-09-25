# 2026-09-25: the pre-push hook runs, fails closed, and names its bypass

Branch `track1/prepush-hook`, branch-start base `59484a9`. Split out of #563 at
the coordinator's recommendation: every change here alters every developer's
push, including on Windows and PowerShell, and the owner should see that on
its own rather than bundled into a gate PR.

## What changed in `.pre-commit-config.yaml` (at `2d1da6a`, superseded below)

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

## Measured (at `2d1da6a`, superseded below)

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

## After the first review (`2d1da6a`)

- **Three hooks run at push anyway.** At the pinned pre-commit-hooks v4.6.0,
  the manifest declares `stages: [commit, push, manual]` for
  `trailing-whitespace`, `end-of-file-fixer` and `check-added-large-files`, and
  `default_stages` does not override a manifest's own stages. Each now has
  `stages: [pre-commit]`. Every other hook's manifest was read at its pinned
  rev and declares none.
- **Each failure names its own cause.** A compose failure (a missing plugin,
  an unsupported flag, a compose-file error) and a `docker info` refusal
  (permission denied) used to read as "container not running" and "daemon
  unreachable". Each branch now quotes the tool's own first line. The compose
  call is captured, not piped into grep, so grep cannot mask its status.
- **Skips exit 2**, the repo's could-not-look code, distinct from pytest's 1.
- **The PowerShell bypass clears itself**:
  `$env:SKIP="api-unit-tests"; git push; Remove-Item Env:SKIP`. The earlier
  form left `SKIP` set for the rest of the session. It was RUN exactly as
  printed in PowerShell 5.1.26100 on 2026-09-25, with `git push` replaced by a
  child process that reported `SKIP`: the child saw it, and the session did not
  keep it.
- **CLAUDE.md now says** that every push runs the suite in the shared
  container, with its duration, the meaning of NOT RUN, both bypasses and the
  reinstall. Agents push with SKIP (my call).
- The tree notice is still vague: filed as #578.

Stub-measured, running the hook's own entry:

| state | exit | message |
| --- | --- | --- |
| suite passes | 0 | the #203 tree notice |
| **suite fails** | **1** | the #203 tree notice |
| container down | 2 | NOT RUN - the api container is not running |
| compose missing | 2 | NOT RUN - docker compose failed - (its error) |
| `docker info` denied | 2 | NOT RUN - docker info failed ... - (its error) |
| docker not on PATH | 2 | NOT RUN - docker is not on PATH |

## After the second review (`23353a4`)

- **The hook's behaviour is a committed gate**, `tests/gates/prepush_hook_status.sh`,
  run in `ci.yml`'s shell-gates step with its `--self-test`. It parses
  `.pre-commit-config.yaml`, checks the registration (`stages: [pre-push]`,
  `always_run: true`, `pass_filenames: false`), and runs the hook's own
  `bash -c` body against a stub `docker` in six states: suite passes 0, suite
  fails 1, and 2 with the cause and both bypasses for the container down,
  compose failing, `docker info` failing and docker absent. The self-test
  puts #143's `|| echo skipped` back, and separately makes the container-down
  branch exit 0; each must turn exactly its named check red, and does.
  Deleting `always_run` was also run once and went red on the registration
  check.
- **`always_run: true`**, so a push whose files match no pattern still runs the
  suite.
- **pre-commit itself was run**, 4.6.2 in a venv, from Git Bash on 2026-09-25,
  with docker taken off PATH so nothing touched the shared stack:
  `pre-commit run --hook-stage pre-push --from-ref origin/main --to-ref HEAD`.
  Exactly one hook ran at the pre-push stage, `api-unit-tests`: it printed
  "NOT RUN - docker is not on PATH" with both bypasses, the hook exited 2,
  and pre-commit exited 1, which is the status a `pre-push` git hook returns
  to refuse a push. With `SKIP=api-unit-tests` it printed "Skipped" and
  pre-commit exited 0. NOT RUN: a real `git push` through an installed hook,
  because installing one writes the `.git/hooks` every worktree shares.
- **CLAUDE.md's bypass marker** now says each form was run in its own shell,
  with a child process standing in for `git push`. The Git Bash form was run
  that way on 2026-09-25 (GNU bash 5.2.37): the child saw `SKIP`, the session
  did not keep it.
- Advisories (a compose WARN standing in for the cause; CLAUDE.md not saying
  NOT RUN blocks the push, nor that Git Bash refuses every push by default)
  are filed as #589.

## After the third review (`6158252`)

- **The stub answers only the exact argv** the hook should send
  (`info`, `compose ps --status running --services`,
  `compose exec -T api pytest -m unit`) and exits 99 on any other, so an edit
  to `--collect-only`, `-T web` or `-m integration` cannot pass as the suite.
  A `--collect-only` self-test mutation turns both suite checks red.
- **The `docker info` state requires the tool's own stderr** in the message,
  and a self-test mutation flipping the redirects turns it red.
- **Could-not-look is 2.** A config that cannot be read or parsed, is empty,
  whose entry does not split as shell words, or has no such hook, exits 2
  before any state runs. Each of those inputs was run once by editing the
  config and restoring it. Two more branches exit 2 but were NOT run, because
  no config edit reaches them: an unexpected crash of the extractor (a
  Ctrl-C propagates rather than being relabelled 2), and a self-test mutation
  that does not land (all four land). None of these branches is pinned by a
  committed test.
- #563's gate over this tree finds nothing in the new script; its two
  findings are in `main`'s workflow steps that #563 itself rewrites.

