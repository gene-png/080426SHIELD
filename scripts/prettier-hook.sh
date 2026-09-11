#!/usr/bin/env bash
# Run prettier at the version the LOCKFILE pins, on the files pre-commit staged.
#
# ## What this replaces
#
# `pre-commit/mirrors-prettier` at `rev: v3.1.0`, whose `prettier` hook id
# defaults to `--write`. CI checks 3.9.6 -- eight minors ahead -- so the
# mandatory pre-commit step rewrote every commit into a state CI then rejected.
# Measured 2026-08-30: `prettier@3.1.0 --check` reported issues in 46 files of a
# tree `prettier@3.9.6 --check` calls clean.
#
# Not fixable by bumping `rev`: that mirror is ARCHIVED upstream, v3.1.0 is its
# newest stable tag, and everything above it is a v4 alpha.
#
# ## Why the version is READ rather than written down
#
# `package.json` holds a RANGE (`^3.9.6`) that names no version and admits
# 3.10.x. CI runs `pnpm install --frozen-lockfile` and then `pnpm format:check`,
# so `pnpm-lock.yaml` is what the machine actually reads -- and `CLAUDE.md`
# records the cost of getting that operand wrong: three documents were once
# repointed at `package.json` "to give the requirement one home", and two of
# them had been correct before the edit.
#
# Hardcoding `3.9.6` here would be a THIRD home for one fact, and the one that
# nothing checks. Reading it from the lockfile means a dependency bump moves the
# hook with CI, in the same commit, by construction.
#
# ## Fail closed
#
# If the version cannot be read, this REFUSES. A hook that shrugged and ran
# `npx prettier` would resolve whatever npm happens to serve -- which is how the
# divergence started, and it would restart it silently. An unreadable lockfile
# is "I could not look", and that must not share an outcome with "formatted".

set -euo pipefail

LOCK="$(git rev-parse --show-toplevel)/pnpm-lock.yaml"

if [ ! -f "$LOCK" ]; then
  echo "prettier hook: $LOCK not found." >&2
  echo "  The version CI uses is the one the lockfile resolves, so without it" >&2
  echo "  this hook cannot know what to run -- and guessing is what put the" >&2
  echo "  hook eight minors behind CI in the first place (#168)." >&2
  exit 1
fi

# The resolved version, from the package entry pnpm writes as `prettier@X.Y.Z:`
# at the top level of `packages:` / `snapshots:`. Anchored to two leading
# spaces so a transitive `foo/prettier@...` cannot match.
#
# `|| true` is load-bearing, and the fixture is what found that out. Under
# `set -euo pipefail` a `grep` that matches nothing exits 1, the pipeline fails,
# and the script DIES before reaching the check below -- so the refusal exited 1
# with no message at all, and the reader got a bare failure from the step whose
# only job is to say what is wrong. `CLAUDE.md` records this exact shape: a
# legitimate zero-count grep exiting the script.
VERSION="$( (grep -oE '^  prettier@[0-9]+\.[0-9]+\.[0-9]+:' "$LOCK" || true) | head -1 | sed 's/^  prettier@//; s/:$//')"

if [ -z "$VERSION" ]; then
  echo "prettier hook: could not read a pinned prettier version from $LOCK." >&2
  echo "  Looked for a line matching '  prettier@X.Y.Z:'. If pnpm changed its" >&2
  echo "  lockfile format, fix this pattern rather than falling back to an" >&2
  echo "  unpinned 'npx prettier' -- an unpinned run is the defect (#168)." >&2
  exit 1
fi

# `--print-version` reads and stops. It exists so every branch of the derivation
# can be exercised without invoking prettier or the network --
# `tests/gates/prettier_hook.sh` uses it, and a version read that nothing could
# test is the state this hook replaced.
if [ "${1:-}" = "--print-version" ]; then
  echo "$VERSION"
  exit 0
fi

# `--write`, matching what the hook has always done, and what `pnpm format`
# does. The point of #168 is not that rewriting is wrong; it is that rewriting
# at the WRONG version produces a diff CI rejects.
exec npx -y "prettier@${VERSION}" --write "$@"
