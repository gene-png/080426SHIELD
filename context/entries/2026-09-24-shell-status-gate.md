# 2026-09-24: a gate's exit status must reach the result (#213)

Branch `track1/shell-status-gate`, base `20f747f`.

## Why

`set -e` has holes, and each one hides a red gate behind a green run:
- **#143:** the pre-push hook ran `pytest ... || echo "skipped"`, so a failing
  suite pushed.
- **#213 instance 1, twice on 2026-09-24:** a gate at the head of an `&&` list
  followed by `git commit` / `git push`. bash exempts the failing gate from
  `set -e`.
- **CLAUDE.md's opening table:** `| head` without pipefail.

The owner asked for this to be gated, not written up again.

## What changed

- **`check_shell_status.py`** flags three shapes wherever a gate command runs:
  - **R1:** the gate is piped without pipefail;
  - **R2:** `|| <anything but exit/return/false/$?>`;
  - **R3:** `&& ...` followed by more statements.

  Conditions (`if` / `while` / `until` / `!`) are exempt. It sees through `sh -c`
  / `bash -c` and `docker compose exec`. It reads every workflow `run:`, the
  pre-commit hooks, and CLAUDE.md's code blocks, and a workflow step with
  `shell: bash` counts as pipefail on.
- **Wired into `ci.yml`'s Python job**, next to the control-character sweep.
- **#143's hook is repaired.** The container check is the `if`, and pytest runs
  unguarded in the branch. With a stub `docker`:

  | case | old hook | new hook |
  | --- | --- | --- |
  | api up, suite passes | 0 | 0 |
  | api up, suite fails | **0, printing "skipped"** | **1** |
  | api down | 0 | 0 |

  The condition was also run against the live stack (`docker compose ps`,
  read-only): 0.

## What it found

The live instance it found, #143's hook, is repaired here. That is 68
scripts read, clean after the repair. Workflow pipes and `||` were checked by
hand to see whether any carried a gate; none did. `mutation_sweep.py`'s `| tee`
is deliberately outside the gate set, because its workflow is report-only by
design (#224).

## Proof

- **Fixtures:** 8 cases, two of them adversarial (a `| tee` on a gate, and
  `gate && echo ok` then `git push`). `check_gate_fixtures` passes: 70 cases
  across 12 gates.
- **Red-on-revert:** removing R1, the `$?`-capture rescue, the `docker exec`
  see-through, or the conditional exemption each turns its named test red. The
  last needed a test rewrite first: a gate FIRST in a condition carries `if` as
  its first word and is never read as a gate, so the original test could not
  reach the exemption. The case it decides is a gate in the MIDDLE of a
  condition.

## Limits

It is a quote-aware pass plus `shlex`, not a shell. It follows no functions,
sourced files or variables holding commands, and a gate behind a wrapper it
does not know is unseen. So it is a floor, not a census.
