# 2026-09-26: condition 5 names the web install guard's script

Branch `track1/cond5-web-install-script`, cut from `origin/main` at `36c242e`.
From #318's findings against #309: condition 5 covered none of the paths that
PR changed, so a later PR weakening the web install guard cleared every
condition. `docker-compose.yml` was already listed, and its bullet said compose
"defines ... the web install guard" — but the guard's logic lives in
`scripts/web-install-if-stale.sh`, which compose bind-mounts and runs as
`sh /app/web-install-if-stale.sh`. A script-only PR changed what CI's
containers install while touching neither compose file.

## What changed

`CLAUDE.md`'s condition-5 compose bullet now names
`scripts/web-install-if-stale.sh`. Nothing else in the rule changed.

**The merge-rule text gate goes red on this PR by design**: it compares the
merge rule section's bytes, and this PR changes them. That red is the gate
doing its job — a human reads the rule change.

## The D-059 measurement, re-derived because condition 5 changed

`CLAUDE.md` says to re-derive the table whenever condition 5 changes. Adding a
path can flip only a PR that currently clears, and only if it touched the added
path. So the question is whether any PR in either recorded window touched the
script.

- **2026-08-26 window:** cannot contain it. The script was added on 2026-09-11
  (`git log --diff-filter=A -- scripts/web-install-if-stale.sh` → `6df6cf4`,
  PR #309).
- **2026-09-21 window:** the recorded selector at its recorded ref,
  `git log --first-parent -40 --format='%H|%s' 897eeae | grep -E '\(#[0-9]+\)$' | head -15`,
  returns 15 PR merges; `git diff --name-only <sha>^1 <sha>` for each touches
  the script in **0** of them.
- **The loop can find hits** (the positive control, same window, same loop): 4
  PRs touch `CLAUDE.md`, 1 touches `docker-compose.yml`, and PR #309's own
  merge touches the script.

Both rows stand, 2/13 and 3/12, and the table's provenance comment now says so.
Run 2026-09-26, Git Bash, with `set -euo pipefail`.
