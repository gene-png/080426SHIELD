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

# The resolved version, read from the ROOT IMPORTER -- `importers:` -> `.:` ->
# `devDependencies:` -> `prettier:` -> `version:`. That is the entry pnpm
# installs for the root workspace, which is what `pnpm format:check` runs.
#
# It used to read the `packages:` section and take `head -1`, and that is a
# SILENT DOWNGRADE, not a stylistic difference. `packages:` is a flat,
# ALPHABETICALLY SORTED list, so a second entry does not append -- it sorts by
# string, and `prettier@2.8.8` sorts before `prettier@3.9.6`. `head -1` then
# takes the LOWEST version in the file. A transitive dependency pulling any
# older prettier would have silently rolled the hook back, reformatting every
# commit with a version CI rejects: the #168 defect, arriving through the fix
# for #168.
#
# The old anchor's comment defended a key shape pnpm 9 never writes
# (`foo/prettier@...`), while the form that CAN occur sorted first and was
# undefended. The authoritative entry was in the same file, unread.
#
# Parsed with awk rather than grep because the value is positional: the same
# `version:` key appears under every dependency of every importer, so what
# identifies this one is the path `. -> (dev)dependencies -> prettier`, not the
# line's own text. Both `dependencies` and `devDependencies` are accepted, and
# `optionalDependencies` deliberately is NOT -- the pattern is anchored
# `^    (dev)?[Dd]ependencies:`, so an optional section closes `in_deps` and
# the hook REFUSES rather than reading from it. Loud, not silent, which is
# why it is an exclusion rather than a defect; stated because an unstated
# one reads as an oversight to whoever finds it. No fixture exercises a
# plain `dependencies:` section either, so that half of the claim is
# asserted rather than tested -- and its failure is also a refusal.
#
# Both are accepted because the root has prettier under dev today and which
# section a tool lives in is not this hook's business.
#
# A `(peer)` suffix is stripped: pnpm writes
# `version: 3.9.6(typescript@5.x)` for packages with peers, and prettier has
# none today, so that is a ratchet rather than a live case.
VERSION="$(
  awk '
    # STATE IS CLEARED ON EVERY KEY LINE, not only on the one that sets it.
    # Without the resets below, `in_deps` and `want` set inside the root
    # importer survived into the NEXT importer: a root with dependencies but no
    # prettier, followed by `apps/web` pinning its own, returned the web
    # version with a zero exit -- indistinguishable from a correct read, and
    # #168 restored through the fix for #168. Measured before the reset:
    # returns 2.0.0 where the answer is the refusal.
    /^importers:/            { in_imp = 1; in_root = 0; in_deps = 0; want = 0; next }
    in_imp && /^[^ ]/        { in_imp = 0; in_root = 0; in_deps = 0; want = 0 }
    in_imp && /^  [^ ]/      { in_root = ($0 ~ /^  \.:[[:space:]]*$/); in_deps = 0; want = 0; next }
    in_root && /^    [^ ]/   { in_deps = ($0 ~ /^    (dev)?[Dd]ependencies:[[:space:]]*$/); want = 0; next }
    in_deps && /^      [^ ]/ { want = ($0 ~ /^      prettier:[[:space:]]*$/); next }
    want && /^        version:/ {
      sub(/^        version:[[:space:]]*/, "")
      sub(/\(.*/, "")
      print
      exit
    }
  ' "$LOCK"
)"

if [ -z "$VERSION" ]; then
  echo "prettier hook: could not read prettier's resolved version from $LOCK." >&2
  echo "  Looked for importers -> '.' -> (dev)dependencies -> prettier -> version," >&2
  echo "  which is the entry pnpm installs for the root workspace and therefore" >&2
  echo "  the one CI runs. If pnpm changed its lockfile format, fix this parser" >&2
  echo "  rather than falling back to an unpinned 'npx prettier' -- an unpinned" >&2
  echo "  run is the defect (#168)." >&2
  echo "  Do NOT go back to reading 'packages:' and taking head -1: that list is" >&2
  echo "  alphabetically sorted, so a second prettier entry silently wins with" >&2
  echo "  the LOWEST version." >&2
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
