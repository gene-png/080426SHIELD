#!/bin/sh
# Prove `verify-in-worktree.sh` resolves the PRIMARY TREE correctly, and
# refuses when it cannot.
#
# NOT #175, though the script used to say so. #175 is a `docker-compose.yml`
# defect -- the line `- ./packages:/app/packages`, bind-mounted with no
# node_modules overlay. The bug this gate covers is the PRIMARY_TREE
# derivation in `verify-in-worktree.sh`, which shares #175's symptoms and
# none of its cause. Conflating them is what sent every reader to the
# compose file to look for a fault in this script.
#
# ## What went wrong
#
# The primary tree was derived from the script's OWN LOCATION:
#
#     PRIMARY_TREE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
#
# Every worktree carries its own copy of the script, so from a worktree that
# resolved to the WORKTREE -- the one tree guaranteed NOT to have
# `packages/*/node_modules`, which is the entire reason the mount exists. The
# mount then named a host path that does not exist, and Docker creates a
# missing bind source as an EMPTY directory rather than failing, shadowing the
# real modules.
#
# Measured 2026-09-21, same commit content, primary tree vs worktree:
#
#   primary   tsc 0 errors     vitest 53/53 files, 575 tests, exit 0
#   worktree  tsc 139 errors   vitest 33/53 files, 414 tests, exit 2
#
# ## Why this test creates a real worktree
#
# A test that only exercised the refusal would stay GREEN with the derivation
# reverted -- the refusal is downstream of the bug. The discriminating input is
# "run from a linked worktree whose own packages/ is empty", so the test builds
# a throwaway git repo and a real worktree and runs the real script in it.
#
# It never starts a container: `--check-mounts` validates and stops.
#
#     sh tests/gates/verify_in_worktree_mounts.sh

set -eu

if [ "$#" -gt 0 ]; then
  echo "FAIL: this script takes no arguments; got: $*" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$ROOT/scripts/verify-in-worktree.sh"
[ -f "$SCRIPT" ] || { echo "FAIL: cannot find $SCRIPT" >&2; exit 2; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# A synthetic repo standing in for the primary tree: it HAS the modules.
REPO="$TMP/shield-primary-fixture"
mkdir -p "$REPO/scripts" "$REPO/packages/design-system"
cp "$SCRIPT" "$REPO/scripts/verify-in-worktree.sh"
git -C "$REPO" init -q
git -C "$REPO" config core.autocrlf false
git -C "$REPO" config user.email gate@example.invalid
git -C "$REPO" config user.name gate
git -C "$REPO" add -A
git -C "$REPO" -c commit.gpgsign=false commit -qm "gate fixture"

# Created AFTER the commit and left untracked, because that is what the real
# thing is: `node_modules` is gitignored, so it exists in the tree `pnpm
# install` ran in and in no other. Committing it would hand every worktree a
# copy and the fixture could not tell the two derivations apart.
mkdir -p "$REPO/packages/design-system/node_modules"
: > "$REPO/packages/design-system/node_modules/.keep"

# A linked worktree, which -- like every real one -- has NO node_modules.
WT="$TMP/shield-linked-fixture"
git -C "$REPO" worktree add -q --detach "$WT" HEAD
[ ! -d "$WT/packages/design-system/node_modules" ] || {
  echo "FAIL: the fixture worktree has node_modules, so it cannot discriminate" >&2
  exit 2
}

fail=0

# 1. THE REGRESSION TEST. Run from the worktree, with no override.
#    Reverting the derivation makes this exit 2.
out="$(cd "$WT" && bash scripts/verify-in-worktree.sh --check-mounts 2>&1)" && rc=0 || rc=$?
if [ "$rc" -ne 0 ]; then
  echo "FAIL: --check-mounts from a linked worktree exited $rc, expected 0." >&2
  # WHICH CAUSE. This assertion fires for two unrelated reasons and they are
  # debugged in opposite directions, so it must not name only the likelier one.
  case "$out" in
    *"Illegal option"*|*"pipefail"*)
      echo "      CAUSE: the script was run by a shell that is not bash." >&2
      echo "      verify-in-worktree.sh is '#!/usr/bin/env bash' and sets" >&2
      echo "      'set -euo pipefail'; dash rejects that and exits 2 before" >&2
      echo "      reading any argument. Invoke it with 'bash', not 'sh' --" >&2
      echo "      on a CI runner /bin/sh is dash, while Git Bash's sh IS bash," >&2
      echo "      so this passes locally and fails there." >&2
      ;;
    *)
      echo "      CAUSE: the primary tree is being derived from the script's own" >&2
      echo "      location, which in a worktree is the worktree, so the mount" >&2
      echo "      named a source that does not exist and Docker created it" >&2
      echo "      empty. The bug is in verify-in-worktree.sh, NOT in" >&2
      echo "      docker-compose.yml -- this is not #175." >&2
      ;;
  esac
  echo "$out" | sed 's/^/      | /' >&2
  fail=1
fi

# 2. It must name the PRIMARY tree, not the worktree. Exit 0 alone does not
#    prove which path it resolved -- only that the path it picked had modules.
#
#    Matched on the LEAF name rather than the full path. `git rev-parse
#    --path-format=absolute` prints a native Windows path (`C:/Users/...`)
#    while `mktemp -d` under MSYS gives `/tmp/...`; the two name the same
#    directory and no string comparison of them succeeds. On a Linux runner
#    they happen to agree, so a full-path compare would pass in CI and fail
#    only on the machine the script is FOR. The leaf names are distinctive and
#    the two fixtures differ in exactly that component.
primary_line="$(printf '%s
' "$out" | grep 'primary tree' || true)"
case "$primary_line" in
  *shield-primary-fixture*) : ;;
  *shield-linked-fixture*)
    echo "FAIL: resolved the LINKED WORKTREE as the primary tree." >&2
    echo "      That is the PRIMARY_TREE derivation bug in verify-in-worktree.sh," >&2
    echo "      not #175, which is a docker-compose.yml mount defect." >&2
    echo "      $primary_line" >&2
    fail=1
    ;;
  *)
    echo "FAIL: could not tell which tree was resolved as primary." >&2
    echo "$out" | sed 's/^/      | /' >&2
    fail=1
    ;;
esac

# 3. The refusal fires when the primary tree genuinely has no modules. A guard
#    observed only in its passing state is not observed.
empty="$TMP/empty"
mkdir -p "$empty"
out2="$(cd "$WT" && SHIELD_PRIMARY_TREE="$empty" bash scripts/verify-in-worktree.sh --check-mounts 2>&1)" && rc2=0 || rc2=$?
if [ "$rc2" -ne 2 ]; then
  echo "FAIL: a primary tree with no node_modules exited $rc2, expected 2." >&2
  echo "      Docker would mount the missing path as an empty directory and the" >&2
  echo "      failure would surface as errors in packages/*, blamed on the branch." >&2
  fail=1
fi
case "$out2" in
  *"$empty"*) : ;;
  *)
    echo "FAIL: the refusal does not name the path it rejected." >&2
    echo "$out2" | sed 's/^/      | /' >&2
    fail=1
    ;;
esac

# 4. An unrecognised mode is still exit 2, not a silent success.
#
#    THE MESSAGE IS ASSERTED, NOT ONLY THE CODE. Exit 2 is also what the
#    script produces when it dies before reading any argument at all -- under
#    `dash`, `set -o pipefail` on line 59 is an illegal option and kills it
#    with exactly 2, no refusal printed. So a code-only assertion here passes
#    for a run that never reached the mode check, which is the same "a
#    selector that selects nothing passes" shape this gate exists to close.
#    Checks 1 and 3 above are covered because each asserts on output too.
out3="$(cd "$WT" && bash scripts/verify-in-worktree.sh --not-a-real-mode 2>&1)" && rc3=0 || rc3=$?
if [ "$rc3" -ne 2 ]; then
  echo "FAIL: unknown mode exited $rc3, expected 2." >&2
  fail=1
fi
case "$out3" in
  *"unknown mode"*) : ;;
  *)
    echo "FAIL: unknown mode exited 2 without refusing -- nothing names the mode." >&2
    echo "      An exit 2 with no message is what a crash produces, so this" >&2
    echo "      run does not show the argument check was ever reached." >&2
    echo "$out3" | sed 's/^/      | /' >&2
    fail=1
    ;;
esac

git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1 || true

if [ "$fail" -ne 0 ]; then
  echo "verify_in_worktree_mounts: FAIL" >&2
  exit 1
fi
echo "verify_in_worktree_mounts: PASS -- derivation, refusal, and arg guard all hold"
