# 2026-09-24: worktree ESLint verification runs again

Branch `track1/verify-eslint-format`, base `20f747f`. Reported by track 2.

`scripts/verify-in-worktree.sh eslint` passed `--format unix`. ESLint 9 (the
repo pins 9.39.5) removed that formatter from core, so every run exited 2 with
"The unix formatter is no longer part of core ESLint". It then printed that it
had run "the same invocation `pnpm -F web lint` uses", so the web-lint half of
worktree verification checked nothing on every branch since the flag arrived
(`0519df7`, 2026-09-10). Tracked in #450, and in #383, its duplicate.

## The fix is a derivation, not a corrected copy

The first version of this fix dropped the flag and kept a hand-written
`eslint .` beside a sentence claiming parity with the gate. That is the same
synchronization that broke, the adversarial review said so, and it was right.
Now all three arms (`typecheck`, `test`, `lint`) run the script of that name
from `apps/web/package.json`, read inside the container: the thing
`pnpm -F web <name>` runs in CI. A missing script or an unreadable
package.json exits 2. ESLint's own exit 2 prints as could-not-look.

## And the self-test can now fail on it

`--self-test` used to probe only tsc, so nothing ever exercised the lint arm,
and that is how a lint arm that could not run survived two weeks. It now plants
a parse error and requires exit **1 exactly**. "Non-zero" would have passed on
the broken arm's exit 2.

| run | result |
| --- | --- |
| `--self-test`, this tree | exit 0: tsc 0 then 1, lint 0 then 1 |
| `--self-test`, `--format unix` put back on the lint script only | **exit 2**, lint baseline 2 |
| `eslint`, package.json's lint given `--max-warnings 0` | **exit 1** on the 3 warnings: the change reached the harness |

The first red-on-revert attempt put the flag on every script, so tsc failed
first and the lint arm was never reached. It was re-run scoped to `lint`, and
that re-run is the one recorded above.

Two present-tense "is broken" statements are date-qualified: one paragraph of
`context/gene.md` (with the coordinator's explicit leave for that paragraph
only) and the 2026-09-22 #209 entry.

## Re-review of `7ed5f7f`

- **Could-not-look reached the bound line.** A missing script exited 2, and
  `tsc` then printed "0 error(s)" over it; tsc's own exit 2 means real errors,
  so the two collided. WEB_SCRIPT now prints a `NO-WEB-SCRIPT` marker, and each
  arm refuses on it before printing any bound. Measured with the `lint` and
  `typecheck` scripts deleted: each arm exits 2 with COULD NOT LOOK and no
  bound. With the refusal reverted, the defect is back.
- **The probes are cleaned up on any exit.** My first trap put `rm` on
  INT/TERM, and that SWALLOWS the signal: a TERM mid-probe ran the cleanup and
  then the self-test carried on to PASS, exit 0 (measured). Now EXIT cleans up
  and the signals exit. A TERM mid-probe gives exit 143 with no probe left.
- The tsc comment's "CI runs `pnpm -F web exec tsc`" is corrected to what
  ci.yml runs, `pnpm -F web typecheck`.
- The derivation copies the scripts' TEXT, not pnpm's executor. The comment
  says so, and the divergence is filed as #570.
