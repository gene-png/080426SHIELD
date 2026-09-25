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

## What changed (as of `a62f41e`; the review sections below supersede it)

- **`check_shell_status.py`** flags three shapes wherever a gate command runs:
  - **R1:** the gate is piped without pipefail;
  - **R2:** `|| <anything but exit/return/false/$?>`;
  - **R3:** `&& ...` followed by more statements.

  Conditions (`if` / `while` / `until` / `!`) were exempt (at round 1;
  superseded for `if` in round 5, below). It sees through `sh -c`
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

## After the adversarial review of `a62f41e`

The review found twelve problems. Five of them (groups, `2>&1`, heredocs,
`set +o`, `|| { ...; exit 1; }`) had one root cause: a flattening token split
standing in for a shell parser. Adding patterns would keep losing. My call,
overturnable: no parser dependency. The gate is now an honest line-level
FLOOR. Its banner says what it read and what it does not model, and it
never says "every gate's status reaches the result" again.

Fixed:
- **Groups:** a `( )`, `{ }` or `$( )` is ONE element with a body, so
  `(cd x && gate) && git push` is R3. This is #213 instance 1's exact shape,
  now a fixture.
- **Redirections:** `2>&1`, `&>` and `|&` no longer split a statement, so
  #143 with its usual redirect is R2 (a fixture).
- **Wrappers:** `sh -c "...gate..." || echo` is judged from outside.
- **R2 exceptions:** `|| { echo; exit 1; }` is not a swallow (a fixture), and
  a bare `! gate` is.
- **Heredocs:** comments are stripped before `<<` is read, and an
  unterminated heredoc is exit 2 (a fixture). `"$( ... )"` gets its own quote
  context.
- **`set +o pipefail`** turns pipefail off.
- **R4, no errexit:** a gate that is not the last statement of an unattended
  script without `set -e` (a `-c` body, a hook entry, a `.sh` file). The last
  command of an if/case branch counts as terminal.
- **Gate spellings:** `env`, `timeout`, `time`, `docker compose run`,
  `.venv/bin/pytest`, `python3.12`, `python -X` and `pnpm format:check` are
  looked through.
- **`.sh` files are scanned** (13 today).
- **Could-not-look:** an indented CLAUDE.md block that names a gate and does
  not parse is exit 2, not "prose", and so is a missing CLAUDE.md.
- **The hook's skip is visible:** `verbose: true`, and "docker is not on
  PATH" is named. Measured with a stub `docker`: pass 0, **fail 1**, down 0
  with "SKIPPED, NOT PASSED", no docker 0 with its cause.

Red-on-revert, one mutation per fix, 13 of 13 red. Two tests first stayed
green under their mutation: one ended in a newline, so a different raise
fired, and one had inner quotes that balanced naively. Both were
strengthened, and the second then exposed a real defect (shlex re-reading a
substitution's quotes), fixed in the same pass. Self-scan (at that round's
head): 65 workflow steps, 2 hook entries, 13 `.sh` files, 1 CLAUDE.md block;
none of R1-R4.

## Limits

Listed in the gate's docstring and filed as #568: functions, sourced files and
command variables; loops; code after an if/case compound; a gate inside
`"$( )"`; keywords used as words; `docker run`; unlisted wrappers; scoped
`set -e`; and no committed test of the hook itself.

## After round 2 of the review (`57b0499`)

- **The round-1 rescue reopened #143.** Any `exit` counted, so `|| exit 0` and
  `|| { echo skipped; exit 0; }` passed clean. A rescue now has to keep the
  failure: `false`, a `$?` capture, `exit`/`return` with no argument, with
  `$?`, with a variable, or with a non-zero literal. `exit 0` is a fixture.
- **R4 applies to workflows**, using each step's real shell flags. A custom
  `shell: bash -euo pipefail {0}` is read for its own flags, and so is
  `bash {0}` (no -e). A next statement that reads `$?` is a rescue, which is
  the repo's own set +e / capture idiom.
- **A brace group's end is not terminal unless the group is.** bash does not
  exit on a failed `{ pytest && echo ok; }`; a failed `( ... )` does exit.
- **The could-not-look word list is `is_gate` itself.** The old list missed
  `tests/gates/*.sh`, bandit and the rest.
- **The hook fails closed**, my call, overturnable: exit 1 with its cause
  named (docker absent, daemon unreachable, container down) and the per-hook
  bypass `SKIP=api-unit-tests git push`. **`default_install_hook_types:
  [pre-commit, pre-push]`**: until now the bare `pre-commit install` everyone
  documents never installed this hook, so "#143 repaired" was true of the
  file and false of pushes.
- **False positives removed:** a trailing `||` continues onto the next line,
  `pytest` then `rc=$?` is kept, and a `#!/bin/bash -e` shebang counts as
  errexit.

Red-on-revert: eight new mutations, each red on its named test. The self-scan
stays clean, with R4 now reading every workflow step.

## After round 3 of the review (`2eb2ac4`)

- **The hook moved out.** Fail-closed, `default_install_hook_types`,
  `default_stages`, the two-shell bypass and the tested-tree notice change
  every developer's push, so they are #576, for the owner to decide on its own.
  This PR keeps only the minimal #143 repair (the `if` form), because its own
  gate scans the hook and would be red on main's `|| echo skipped`. Both edit
  the same `entry:` line; whichever lands second takes #576's.
- **The rescue model is conservative**, because it grew a new hole in each
  round: `|| exit 0` in round 1, then `|| { echo skipped; exit; }` and
  `|| { rc=$?; echo failed; exit 0; }` in round 2. A rescue now counts only if
  the FIRST thing after the failure visibly keeps it: `false`; `exit`/`return`
  bare, with `$?`, or with a non-zero literal; or `var=$?` that a later
  exit/return/[/test/if decides on. In a `{ }` group, the first exit it reaches
  being a non-zero literal also counts, which keeps the fail-loud
  `|| { echo msg; exit 1; }` (my refinement, overturnable). A printed `$?` is
  not kept. The trade is stated in the docstring: a false positive costs a
  rewrite, a false negative costs the next #143.
- Two old tests encoded the lenient rule (`|| rc=$?` never read, and
  `exit "$rc"` with no visible capture). They were said to be wrong before
  being changed, and now pin the opposite.
- Red on revert: five mutations, each red. The self-scan stays clean.

## After round 4 of the review (`9701c47`): a whitelist

Round 4 found #143 reopened a fourth time, through my own refinement: the
"first exit it reaches" rule read the first exit in TEXT order, not the one
executed (`docker ps || exit 0` or an `if` inside the group). A capture
"decided on" anywhere later counted, including a warn-only `if`. `exit 256`
counted as non-zero, and `|| false` counted with errexit off. The
coordinator's direction: stop refining and use an explicit whitelist.

- **The right side of `||` must be EXACTLY one of:** `exit N` / `return N`
  with N % 256 != 0; `exit $?` / `return $?`; `false` while errexit is on;
  `{ echo/printf...; exit N; }` with one exit, last, at top level, and no
  if/then/&&/||/nested group/$( inside; or `var=$?` whose NEXT statement is
  exactly `exit $var`, `return $var`, `[ "$var" -ne 0 ] && exit "$var"` or
  `[ "$var" -eq 0 ] || exit "$var"`. Any other right side of `||` is a
  finding. (Round 4 called this a whitelist and said "everything else is a
  finding"; that overclaimed, because it is a whitelist only for the shapes
  the gate recognizes. Round 5, below, restates it as a floor.) The
  "reaches" and "decides" machinery is deleted.
- **Two real repo scripts failed it, and the SCRIPTS were rewritten**, not the
  rule. audit-gate's D-NUMBERS step now runs the gate as its only command,
  with a separate `if: failure()` step printing the banner (naming both exit
  codes' meanings). ci.yml's advisory recalled-counts step uses the
  whitelisted `|| { echo...; exit 2; }`. `close_guard_linked_file.sh`, which
  reads audit-gate.yml, still passes.
- Four tests and one fixture encoded the wider model (bare `exit`,
  `{ exit $?; }`, a `set -e` or `cat` between capture and exit). That was said
  before they were changed. Each reviewer case, plus three boundary cases, is a
  finding test.
- Red on revert: seven mutations, one per whitelist rule, each red. Two rules
  (echo-only, forbidden tokens) overlapped on the reviewer's cases, so each got
  a case only it catches.

## After round 5 of the review: a floor, not a whitelist

At the coordinator's direction the gate stops claiming to be a whitelist. What
it does: it checks the shapes it recognizes, and the shapes it does not
recognize are listed as limits rather than judged. (This paragraph said "it is
strict about those" at `8f57741`, and round 6 showed the `if` rule was not; see
below.)

- **The first `||` after the gate is the rescue.** When the gate fails, `&&`
  short-circuits to the first `||`, so the element after THAT one is what runs,
  and it must be the statement's last element. `gate || exit 0 || exit 1`
  exits 0, and is now a finding.
- **A gate as an `if` condition is checked** (at `8f57741`; tightened in
  rounds 6 and 7 below). Only the plain `if gate` / `if ! gate` shape is
  modelled. The branch that runs on failure must end in a literal failing `exit N` / `return N`, or `exit $?` in the else-branch of
  `if gate` only: in the then-branch of `if ! gate`, `$?` is the negation's
  status, 0. No such branch, an `elif` chain, or a compound condition
  (`if pytest || true`) is a finding. The repo's own scripts pass unchanged.
- **A capture across `else` / `fi` / `done` / `;;` is refused.** The flat
  statement list read `pytest || rc=$?` then `exit "$rc"` as adjacent across a
  `fi`, where `rc` can be unset.
- **Limits, stated rather than modelled**, in the docstring and in the clean
  banner, so every green run prints them: unquoted `$(gate)` in `echo` /
  `export` / `local`, a backgrounded gate and `wait`, heredoc bodies fed to a
  shell, `trap ... EXIT`, and `while` / `until` conditions (#586). Missing
  inputs are asymmetric, `package.json` scripts are not scanned, and a `pwsh` /
  `python` step is read as shell (#587, which also carries the missing
  CLAUDE.md gate-suite line and D-record).
- A test encoded the old spec (`if` conditions exempt); that was said before it
  was changed, and it is replaced by
  `test_an_if_condition_no_longer_consumes_the_status_for_free`.
- Red on revert: five mutations, each red on its named test (any `||` may
  rescue, the if-condition check removed, a compound condition accepted, `$?`
  accepted after a negation, a capture across `fi` accepted). The compound one
  first stayed green, because its only case had no else-branch; a
  discriminating case (`if pytest || true; then :; else exit 1; fi`) was added.
- Self-scan at `8f57741`: 66 workflow steps, 2 hook entries, 13 `.sh` files,
  1 CLAUDE.md block; none of R1-R4.

## After round 6 of the review (`89bbdc8`)

Round 6 ran `analyse()` and found the round-5 `if` rule looser than R2's: it
checked only the failure branch's LAST statement. So
`else echo "tests failed"; exit $?` passed (the `$?` is echo's 0), and so did
a failure branch whose exit sat inside a nested `if` or `while`.

- **The failure branch now uses R2's grammar, from the same function**
  (`_echoes_then_failure`; at `be5f823`, and `return` was dropped in round 7): zero or more simple `echo` / `printf` statements,
  then a literal failing `exit N` / `return N`, last. `exit $?` / `return $?`
  is allowed only as the SOLE statement of the else-branch of `if gate`. Any
  nested compound in the failure branch is a finding. With that, the gate is
  strict about the `if` shapes it recognizes, and the sentence above is true
  of the tree at this round's head.
- New finding tests, in `test_the_failure_branch_is_the_closed_echo_then_exit_grammar`:
  the reviewer's cases and `if ! pytest; then while false; do exit 1; done;
  fi`. The kept cases `if ! pytest; then echo x; exit 1; fi` and
  `if pytest; then :; else exit $?; fi` still pass.
- Red on revert: five mutations, each red on its named test (the round-5
  last-statement rule restored, `exit $?` after another statement, `exit $?`
  under `if !`, echoes refused before the exit, the sole `exit $?` refused).
  Round 5's mutations still go red where their anchors survive; the `$?`
  after a negation anchor was rewritten by this round and is replaced by the
  `if !` mutation above.
- Self-scan on the merged tree (`89bbdc8` plus this round): 66 workflow steps,
  2 hook entries, 14 `.sh` files, 1 CLAUDE.md block; none of R1-R4.

## After round 7 of the review (`be5f823`)

Round 7 ran bash: `bash -c 'false || return 1; echo after'` prints "can only
`return' from a function", then runs `echo after`, and exits 0 (2 under
`-e`). So `return` at a script's top level does not exit, and every form that
accepted it was a hole, PRE-EXISTING since round 2.

- **`return` is dropped from every accepted form**: the `||` rescue, the
  `{ ...; }` group, the `if` failure branch, `exit $?`, and the capture's next
  statement. Functions are already an unmodelled limit, so no in-scope shape
  needed it.
- **Three pinned expectations were WRONG, not strict**, and were said to be
  before they changed: `return 2` in `test_r2_is_not_a_capture`, `return 1` in
  `test_whitelisted_rescues`, and `return $rc` in the capture test. They move
  to `test_return_is_never_a_rescue` as findings, with
  `if ! pytest; then echo x; return 1; fi` and the other return forms.
- Red on revert: three mutations (`return N`, `return $?`, `return $var`
  accepted again), each red on that test. Round 6's mutations still go red.
- Limits added to the docstring: a keyword used as an argument (`exit 1 fi`)
  can make a branch look like it ends in an exit; a backtick substitution is
  read as a word (only `$(` is refused).
- Self-scan at this round's head: clean.
