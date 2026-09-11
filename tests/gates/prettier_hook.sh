#!/bin/sh
# Prove the prettier hook reads the right version and refuses when it cannot.
#
# The thing this replaced was `rev: v3.1.0` in a YAML file -- a version literal
# nothing checked, eight minors behind CI, on a hook that rewrites every commit.
# Replacing one unchecked literal with another would have changed nothing that
# matters, so the hook derives the version and this proves the derivation.
#
# `--print-version` does the read and stops, so every case here runs without
# invoking prettier or the network.

set -eu

HOOK="${HOOK:-$(cd "$(dirname "$0")/../.." && pwd)/scripts/prettier-hook.sh}"
[ -f "$HOOK" ] || { echo "FAIL: cannot find $HOOK"; exit 2; }

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
# A real repo, because `git rev-parse --show-toplevel` walks for a `.git` it can
# actually read -- a bare directory of that name is not one, and the hook's
# error then names git rather than the lockfile.
( cd "$ROOT" && git init -q . )

run() {
  ( cd "$ROOT" && sh "$HOOK" --print-version 2>&1 )
}

expect_ok() {
  want="$1"; label="$2"
  set +e
  out="$(run)"; code=$?
  set -e
  if [ "$code" -ne 0 ] || [ "$out" != "$want" ]; then
    echo "FAIL [$label]: exit $code, output '$out', wanted '$want'"
    exit 1
  fi
  echo "ok   [$label] -> $out"
}

expect_refusal() {
  want_text="$1"; label="$2"
  set +e
  out="$(run)"; code=$?
  set -e
  if [ "$code" -eq 0 ]; then
    echo "FAIL [$label]: exited 0. A hook that shrugs and runs an unpinned"
    echo "  prettier restarts the divergence silently -- that is #168."
    exit 1
  fi
  case "$out" in
    *"$want_text"*) echo "ok   [$label]" ;;
    *) echo "FAIL [$label]: refusal does not mention '$want_text'"; echo "$out"; exit 1 ;;
  esac
}

# --- THE READ. Without this the refusals could all be one broken pattern. ----
printf 'lockfileVersion: 9.0\npackages:\n  prettier@3.9.6:\n' > "$ROOT/pnpm-lock.yaml"
expect_ok "3.9.6" "reads the pinned version"

# --- A TRANSITIVE entry must not win. ---------------------------------------
# `eslint-plugin-prettier` and friends are real dependencies, and an unanchored
# grep picks whichever comes first -- silently running some other package's
# version number as prettier's.
printf 'lockfileVersion: 9.0\npackages:\n  eslint-plugin-prettier@5.0.0:\n  prettier@3.9.6:\n' \
  > "$ROOT/pnpm-lock.yaml"
expect_ok "3.9.6" "a transitive prettier-ish entry does not win"

# --- No lockfile. -----------------------------------------------------------
rm -f "$ROOT/pnpm-lock.yaml"
expect_refusal "not found" "no lockfile -> refuse"

# --- Lockfile with no prettier. ---------------------------------------------
printf 'lockfileVersion: 9.0\npackages:\n  react@19.0.0:\n' > "$ROOT/pnpm-lock.yaml"
expect_refusal "could not read a pinned prettier version" "no entry -> refuse"

# --- The version it reads must be the one CI resolves. ----------------------
# The whole point. Read from the REAL lockfile, and compared against the same
# file rather than a literal -- a literal here would be the fourth home for one
# fact, which is the defect this hook exists to end.
REPO="$(cd "$(dirname "$HOOK")/.." && pwd)"
real="$( cd "$REPO" && sh "$HOOK" --print-version )"
pinned="$(grep -oE '^  prettier@[0-9]+\.[0-9]+\.[0-9]+:' "$REPO/pnpm-lock.yaml" | head -1 | sed 's/^  prettier@//; s/:$//')"
if [ "$real" != "$pinned" ] || [ -z "$real" ]; then
  echo "FAIL: hook reads '$real', lockfile pins '$pinned'"
  exit 1
fi
echo "ok   [the repo's own lockfile reads back as $real]"

echo
echo "prettier-hook: version derived, transitive entry ignored, both refusals fire."
