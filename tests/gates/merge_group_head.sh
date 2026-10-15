#!/usr/bin/env bash
# Prove, against REAL git, that the merge-queue resolver confirms the queued
# PR's current head is what the group merges (#659, #736 item C).
#
# `apps/api/scripts/merge_group_pr.py --base-sha B --group-head-sha G` requires
#
#     tree(G) == git merge-tree --write-tree B <PR head>
#
# Its unit tests replace git with a table, which proves the branching and
# cannot prove the premise: that a squash group's tree, and a merge-commit
# group's tree, are what `merge-tree` computes. This builds both shapes in a
# throwaway repository and runs the resolver against a stub `gh` that answers
# with the PR's head. Both directions: the two real shapes pass; a PR pushed
# after it was queued, a group holding a second PR, a head that conflicts with
# the base, and a head that cannot be fetched each exit 2; and a head missing
# from the clone is fetched by sha and then passes.
#
#     bash tests/gates/merge_group_head.sh
#
# Exit codes (D-090): 0 every case behaved; 1 a case did not; 2 could not look
# (an argument given, no git or python, or the resolver missing).

set -euo pipefail

if [ "$#" -gt 0 ]; then
  echo "FAIL: this script takes no arguments; got: $*" >&2
  exit 2
fi

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
RESOLVER="$ROOT/apps/api/scripts/merge_group_pr.py"
[ -f "$RESOLVER" ] || { echo "FAIL: cannot find $RESOLVER"; exit 2; }
command -v git >/dev/null || { echo "FAIL: git is not on PATH -- could not look"; exit 2; }
PY=$(command -v python3 || command -v python || true)
[ -n "$PY" ] || { echo "FAIL: no python on PATH -- could not look"; exit 2; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# The stub answers `gh api repos/o/r/pulls/42` with a PR whose head is
# $STUB_PR_HEAD, and refuses anything else, so an unexpected call is loud.
mkdir "$WORK/bin"
cat > "$WORK/bin/gh" <<'EOF'
#!/usr/bin/env bash
if [ "$1 $2" = "api repos/o/r/pulls/42" ]; then
  printf '{"number": 42, "title": "t", "body": "b", "user": {"login": "u"}, "head": {"sha": "%s"}}\n' "$STUB_PR_HEAD"
  exit 0
fi
echo "stub gh: unexpected call: $*" >&2
exit 99
EOF
chmod +x "$WORK/bin/gh"

R="$WORK/origin"
git init -q -b main "$R"
git -C "$R" config user.email gate@example.invalid
git -C "$R" config user.name gate
git -C "$R" config core.autocrlf false
c() { git -C "$R" commit -q -m "$1"; git -C "$R" rev-parse HEAD; }

printf 'a\n' > "$R/f"; git -C "$R" add f; ROOT0=$(c root)
# The PR: branched from the root, adds g in two commits.
git -C "$R" checkout -q -b pr "$ROOT0"
printf 'g1\n' > "$R/g"; git -C "$R" add g; c pr-1 >/dev/null
printf 'g2\n' >> "$R/g"; git -C "$R" add g; PR_HEAD=$(c pr-2)
# main moves on after the branch point: the group's base is NOT the fork point.
git -C "$R" checkout -q main
printf 'h\n' > "$R/h"; git -C "$R" add h; BASE=$(c main-1)

# Squash-shaped group: one commit on the base, tree = base + the PR.
git -C "$R" checkout -q -b q-squash "$BASE"
git -C "$R" merge -q --squash pr >/dev/null
SQUASH=$(c "squashed (#42)")
# Merge-commit-shaped group: parents are the base and the PR head.
git -C "$R" checkout -q -b q-merge "$BASE"
git -C "$R" merge -q --no-ff --no-edit pr >/dev/null
MERGE=$(git -C "$R" rev-parse HEAD)
# The PR is pushed AFTER the squash group was built.
git -C "$R" checkout -q pr
printf 'late\n' >> "$R/g"; git -C "$R" add g; PR_LATE=$(c pr-late)
# A group carrying a second PR's change on top of this one.
git -C "$R" checkout -q -b q-two "$SQUASH"
printf 'other\n' > "$R/o"; git -C "$R" add o; TWO=$(c "another PR (#43)")
# A head that conflicts with the base: it edits f, and so does main-2.
git -C "$R" checkout -q -b pr-conflict "$ROOT0"
printf 'mine\n' > "$R/f"; git -C "$R" add f; CONFLICT=$(c conflict)
git -C "$R" checkout -q -b base-2 "$BASE"
printf 'theirs\n' > "$R/f"; git -C "$R" add f; BASE2=$(c main-2)
git -C "$R" checkout -q main
# The PR head is published as GitHub publishes a fork's: refs/pull/42/head.
git -C "$R" update-ref refs/pull/42/head "$PR_HEAD"

REF="refs/heads/gh-readonly-queue/main/pr-42-$(printf 'a%.0s' $(seq 40))"
failures=0

# run CASE EXPECT DIR BASE GROUP PR_HEAD
run() {
  local name=$1 expect=$2 dir=$3 base=$4 group=$5 head=$6 rc=0
  (cd "$dir" && STUB_PR_HEAD=$head PATH="$WORK/bin:$PATH" "$PY" "$RESOLVER" \
    --head-ref "$REF" --repo o/r --base-sha "$base" --group-head-sha "$group" \
    --body-out "$WORK/body.txt" --head-sha-out "$WORK/head.txt") > "$WORK/out.txt" 2>&1 || rc=$?
  if [ "$rc" -eq "$expect" ]; then
    echo "ok   $name: exit $rc"
  else
    echo "FAIL $name: exit $rc, expected $expect"; sed 's/^/     /' "$WORK/out.txt"
    failures=$((failures + 1))
  fi
  if [ "$expect" -ne 0 ] && [ -e "$WORK/body.txt" ]; then
    echo "FAIL $name: a body was written on a refusal"; failures=$((failures + 1))
  fi
  rm -f "$WORK/body.txt" "$WORK/head.txt"
}

run "squash-shaped group passes"                  0 "$R" "$BASE"  "$SQUASH" "$PR_HEAD"
run "merge-commit-shaped group passes"            0 "$R" "$BASE"  "$MERGE"  "$PR_HEAD"
run "PR pushed after it was queued is refused"    2 "$R" "$BASE"  "$SQUASH" "$PR_LATE"
run "group holding a second PR is refused"        2 "$R" "$BASE"  "$TWO"    "$PR_HEAD"
run "head conflicting with the base is refused"   2 "$R" "$BASE2" "$SQUASH" "$CONFLICT"

# A clone with main only: the PR head must be FETCHED by sha before it is compared.
C="$WORK/clone"
git init -q -b main "$C"
git -C "$C" remote add origin "$R"
git -C "$C" fetch -q --no-tags origin "+refs/heads/main:refs/remotes/origin/main" "+refs/heads/q-squash:refs/remotes/origin/q-squash"
if git -C "$C" cat-file -e "$PR_HEAD^{commit}" 2>/dev/null; then
  echo "FAIL setup: the clone already has the PR head, so the fetch case proves nothing"; exit 2
fi
run "head missing from the clone is fetched, then passes" 0 "$C" "$BASE" "$SQUASH" "$PR_HEAD"
git -C "$C" cat-file -e "$PR_HEAD^{commit}" || { echo "FAIL fetch case: the head was not fetched"; failures=$((failures + 1)); }
run "head that cannot be fetched is refused"      2 "$C" "$BASE"  "$SQUASH" "$(printf 'e%.0s' $(seq 40))"

if [ "$failures" -ne 0 ]; then
  echo "merge_group_head: $failures case(s) misbehaved"
  exit 1
fi
echo "merge_group_head: all cases behaved"
