#!/usr/bin/env bash
#
# Which worktrees carry a CLAUDE.md older than main's? (#439)
#
# Every worktree is a full checkout with its own CLAUDE.md, frozen at whatever
# commit it was cut from, and an agent dispatched into one reads THAT copy. On
# 2026-09-22, 113 of 131 worktrees carried a copy over the reader limit, and 100
# still hid condition 5's test glob past the cut -- #347, fixed on main and live
# in every stale tree. Nothing said which trees were stale.
#
# This REPORTS. It never removes, prunes or edits anything: most worktrees
# belong to other sessions, and `refs/stash` and the object store are shared,
# so deleting is a decision for whoever made them (CLAUDE.md's shared-tree
# rules). NOTHING CALLS `--check` YET: wiring it into agent dispatch is the
# part #439 still owes.
#
# ## What it compares
#
# Blob ids, not text: a tree's `HEAD:CLAUDE.md` against the main ref's, and
# against the one at their merge base.
#
#   SAME    the tree's CLAUDE.md IS main's.
#   STALE   the tree's branch never changed CLAUDE.md, and main has since.
#   EDITED  the branch changed CLAUDE.md, and main has not changed it since the
#           branch point, so every difference from main is the branch's own
#           edit -- which may add rules or remove them.
#   EDITED+STALE  both: the branch changed it AND main moved on, so the tree
#           lacks main's newer rules.
#   MISSING the tree's HEAD has no CLAUDE.md at all.
#
# Also per tree: how far behind main, uncommitted changes, the file's size
# against the 150,000-byte reader limit, and whether its last non-empty line
# matches main's (`last-line=same` or `last-line=differs-from-main`). That is a
# comparison with main, not a truncation verdict: a tree cut before the canary
# changed form differs from main without being truncated.
#
# ## Usage
#
#     scripts/worktree-audit.sh                      # report every worktree
#     scripts/worktree-audit.sh --check <path>       # one tree, before dispatch
#     scripts/worktree-audit.sh --self-test          # prove every state it tests
#     SHIELD_MAIN_REF=main scripts/worktree-audit.sh # compare against another ref
#
# `--check` exits 0 for SAME or EDITED, 1 for STALE, EDITED+STALE or MISSING
# (the agent would read rules main no longer has, or none), 2 when it could not
# look. It resolves the main ref in the repository it is RUN from, names that
# commit in its output, and refuses (2) when the target resolves the ref to a
# different commit -- a separate clone would otherwise compare against its own,
# possibly stale, main and read SAME. The report mode exits 0 when it read every
# tree and 2 when it could not read one. The committed CLAUDE.md is what is
# compared; uncommitted edits are flagged, not judged.
#
# LIMITS: it compares CLAUDE.md only, not `.claude/agents/*.md`, which go stale
# the same way. `--check` judges the rules only, not the size or the last line
# (#614). A tree whose directory is gone is reported as GONE and not read. It
# reads the main ref as it is locally: fetch first, or "SAME" means "same as a
# stale main".
set -euo pipefail

LIMIT=150000
# Absolute, because --self-test re-invokes this script from another directory.
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
MAIN="${SHIELD_MAIN_REF:-origin/main}"

usage() {
  echo "usage: $0 [--check <path> | --self-test]" >&2
}

# Arity on $#, not ${1:-}: an explicit "" must not run as no argument.
MODE=report
TARGET=""
if [ "$#" -gt 0 ]; then
  case "$1" in
    --check)
      if [ "$#" -ne 2 ] || [ -z "$2" ]; then
        echo "FAIL: --check takes exactly one non-empty path." >&2
        usage
        exit 2
      fi
      MODE=check
      TARGET="$2"
      ;;
    --self-test)
      if [ "$#" -ne 1 ]; then
        echo "FAIL: --self-test takes no other argument." >&2
        exit 2
      fi
      MODE=self-test
      ;;
    *)
      echo "FAIL: unknown argument '$1'." >&2
      usage
      exit 2
      ;;
  esac
fi

# blob <dir> <rev> -> the CLAUDE.md blob id at <rev>; empty when the path is
# ABSENT there; returns 2 when <rev>'s tree cannot be read. Absent and
# unreadable are different answers and must not share a branch.
blob() {
  local line
  git -C "$1" cat-file -e "$2^{tree}" 2>/dev/null || return 2
  line="$(git -C "$1" ls-tree "$2" -- CLAUDE.md)" || return 2
  # `<mode> blob <id><TAB>CLAUDE.md`, or nothing when the path is absent.
  set -- $line
  printf '%s' "${3:-}"
}

last_line() { # stdin -> its last non-empty line, CR stripped
  tr -d '\r' | awk 'NF { l = $0 } END { print l }'
}

# classify <dir> -> prints "STATE behind dirty bytes last-line", or returns 2
classify() {
  local dir="$1" main_blob head_blob base base_blob state behind dirty bytes last want have
  git -C "$dir" rev-parse --verify -q HEAD >/dev/null 2>&1 || return 2
  main_blob="$(blob "$dir" "$MAIN")" || return 2
  [ -n "$main_blob" ] || return 2
  head_blob="$(blob "$dir" HEAD)" || return 2
  base="$(git -C "$dir" merge-base HEAD "$MAIN" 2>/dev/null)" || return 2
  base_blob="$(blob "$dir" "$base")" || return 2
  if [ -z "$head_blob" ]; then
    state=MISSING
  elif [ "$head_blob" = "$main_blob" ]; then
    state=SAME
  elif [ "$head_blob" = "$base_blob" ]; then
    state=STALE
  elif [ "$base_blob" = "$main_blob" ]; then
    state=EDITED
  else
    state=EDITED+STALE
  fi
  behind="$(git -C "$dir" rev-list --count "HEAD..$MAIN")" || return 2
  # --no-optional-locks: `status` would otherwise refresh the index, i.e. WRITE
  # into a worktree that may belong to another session. This reads only.
  dirty="$(git --no-optional-locks -C "$dir" status --porcelain | wc -l | tr -d ' ')" || return 2
  if [ -f "$dir/CLAUDE.md" ]; then
    bytes="$(wc -c < "$dir/CLAUDE.md" | tr -d ' ')" || return 2
    [ -n "$bytes" ] || return 2
    want="$(git -C "$dir" cat-file blob "$main_blob" | last_line)" || return 2
    have="$(last_line < "$dir/CLAUDE.md")" || return 2
    if [ "$have" = "$want" ]; then last=same; else last=differs-from-main; fi
  else
    bytes=0
    last=differs-from-main
  fi
  echo "$state $behind $dirty $bytes $last"
}

report_one() { # <dir> <branch> -> one line; returns 3 if gone, 2 if it could not look
  local dir="$1" branch="$2" out state behind dirty bytes last over=""
  if [ ! -d "$dir" ]; then
    printf '%-13s %s  (%s)\n' "GONE" "$dir" "$branch"
    return 3
  fi
  if ! out="$(classify "$dir")"; then
    printf '%-13s %s  (%s)\n' "COULD-NOT-LOOK" "$dir" "$branch"
    return 2
  fi
  read -r state behind dirty bytes last <<<"$out"
  if [ "$bytes" -gt "$LIMIT" ]; then over=" OVER-LIMIT"; fi
  printf '%-13s behind=%-4s dirty=%-3s bytes=%s%s last-line=%s  %s  (%s)\n' \
    "$state" "$behind" "$dirty" "$bytes" "$over" "$last" "$dir" "$branch"
}

report() {
  local path="" branch="" line row got read_ok=0 gone=0 could_not=0 stale=0
  git rev-parse --verify -q "$MAIN" >/dev/null || {
    echo "worktree-audit: could not look -- no ref '$MAIN'. Fetch first." >&2
    return 2
  }
  echo "worktree-audit: each worktree's CLAUDE.md against $MAIN ($(git rev-parse --short=12 "$MAIN"))"
  # `git worktree list --porcelain`: a block per tree, `worktree <path>` first.
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      "worktree "*) path="${line#worktree }"; branch="detached" ;;
      "branch "*) branch="${line#branch refs/heads/}" ;;
      "")
        if [ -n "$path" ]; then
          got=0
          row="$(report_one "$path" "$branch")" || got=$?
          echo "$row"
          case "$got" in
            0) read_ok=$((read_ok + 1)) ;;
            3) gone=$((gone + 1)) ;;
            *) could_not=$((could_not + 1)) ;;
          esac
          case "$row" in STALE* | EDITED+STALE* | MISSING*) stale=$((stale + 1)) ;; esac
          path=""
        fi
        ;;
    esac
  done < <(git worktree list --porcelain; echo)
  echo "worktree-audit: $read_ok worktree(s) read, $gone gone (not read), $could_not could not be read; $stale of those read would give an agent rules main no longer has (STALE, EDITED+STALE or MISSING)."
  if [ "$read_ok" -eq 0 ] || [ "$could_not" -gt 0 ]; then return 2; fi
  return 0
}

check() {
  local out state mine theirs
  mine="$(git rev-parse --verify -q "$MAIN" 2>/dev/null)" || {
    echo "worktree-audit: could not look -- no ref '$MAIN' in the repository this was run from." >&2
    return 2
  }
  theirs="$(git -C "$TARGET" rev-parse --verify -q "$MAIN" 2>/dev/null)" || {
    echo "worktree-audit: could not look -- '$TARGET' is not a git tree, or has no ref '$MAIN'." >&2
    return 2
  }
  if [ "$mine" != "$theirs" ]; then
    echo "worktree-audit: could not look -- '$TARGET' resolves $MAIN to ${theirs:0:12}, the repository this was run from to ${mine:0:12}." >&2
    echo "  It is a separate clone comparing against its own $MAIN. Fetch both, or run this from the clone." >&2
    return 2
  fi
  out="$(classify "$TARGET")" || {
    echo "worktree-audit: could not look -- cannot read '$TARGET''s CLAUDE.md or its history." >&2
    return 2
  }
  state="${out%% *}"
  echo "worktree-audit: $TARGET: $state against $MAIN at ${mine:0:12} ($out)"
  case "$state" in
    SAME | EDITED) return 0 ;;
    *)
      echo "  This tree's CLAUDE.md lacks rules $MAIN has. Before dispatching an agent into it," >&2
      echo "  merge $MAIN into its branch -- or, for a detached review tree, cut a fresh one" >&2
      echo "  at the head you mean to review once that head has $MAIN merged in." >&2
      return 1
      ;;
  esac
}

self_test() {
  local tmp r rc fail=0 out tree
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  r="$tmp/repo"
  mkdir "$r"
  git -C "$r" init -q -b main
  git -C "$r" config user.email t@example.invalid
  git -C "$r" config user.name t
  git -C "$r" config core.autocrlf false
  printf 'rules v1\n\nCANARY\n' > "$r/CLAUDE.md"
  git -C "$r" add -A && git -C "$r" commit -q -m v1
  git clone -q "$r" "$tmp/old-clone"
  git -C "$r" worktree add -q "$tmp/stale" -b stale
  git -C "$r" worktree add -q "$tmp/edited-behind" -b edited-behind
  printf 'rules v1, edited on a branch\n\nCANARY\n' > "$tmp/edited-behind/CLAUDE.md"
  git -C "$tmp/edited-behind" commit -q -am edit
  printf 'rules v2\n\nCANARY\n' > "$r/CLAUDE.md"
  git -C "$r" commit -q -am v2
  git -C "$r" worktree add -q "$tmp/same" -b same
  git -C "$r" worktree add -q "$tmp/edited" -b edited
  printf 'rules v2, edited on a branch\n\nCANARY\n' > "$tmp/edited/CLAUDE.md"
  git -C "$tmp/edited" commit -q -am edit
  # A tree whose HEAD commit's tree object is gone: readable ref, unreadable tree.
  git -C "$r" worktree add -q "$tmp/unreadable" -b unreadable
  printf 'rules v2, a commit whose tree is then deleted\n\nCANARY\n' > "$tmp/unreadable/CLAUDE.md"
  git -C "$tmp/unreadable" commit -q -am unreadable
  tree="$(git -C "$tmp/unreadable" rev-parse "HEAD^{tree}")"
  rm -f "$r/.git/objects/${tree:0:2}/${tree:2}"
  if git -C "$r" cat-file -e "$tree" 2>/dev/null; then
    echo "FAIL [setup]: the tree object $tree is still readable after deleting it"
    return 1
  fi
  # --check runs FROM the temp repository: it resolves main where it is run.
  expect() { # <path> <want exit> <want text>
    local got=0 out
    out="$(cd "$r" && SHIELD_MAIN_REF=main "$SELF" --check "$1" 2>&1)" || got=$?
    case "$out" in *"$3"*) ;; *) got="wrong-output" ;; esac
    if [ "$got" = "$2" ]; then echo "ok   [$3] exit $2"; else echo "FAIL [$3]: got $got, wanted exit $2; output: $out"; fail=1; fi
  }
  expect "$tmp/same" 0 ": SAME against main at"
  expect "$tmp/stale" 1 ": STALE against main at"
  expect "$tmp/edited" 0 ": EDITED against main at"
  expect "$tmp/edited-behind" 1 ": EDITED+STALE against main at"
  expect "$tmp/unreadable" 2 "cannot read"
  expect "$tmp" 2 "is not a git tree"
  expect "$tmp/old-clone" 2 "resolves main to"
  # Only the MERGE BASE's tree unreadable: HEAD, main, status and rev-list all
  # still work, so blob() is the one reader standing between an unreadable
  # tree and a confident EDITED+STALE. The HEAD case above fails earlier, in
  # `status`, and would pass with blob() folding errors away.
  local r2="$tmp/repo2" b2 got2=0 out2
  mkdir "$r2"
  git -C "$r2" init -q -b main
  git -C "$r2" config user.email t@example.invalid
  git -C "$r2" config user.name t
  git -C "$r2" config core.autocrlf false
  printf 'base rules\n' > "$r2/CLAUDE.md"
  git -C "$r2" add -A && git -C "$r2" commit -q -m base
  git -C "$r2" worktree add -q "$tmp/base-unreadable" -b base-unreadable
  printf 'base rules, edited on a branch\n' > "$tmp/base-unreadable/CLAUDE.md"
  git -C "$tmp/base-unreadable" commit -q -am edit
  printf 'newer rules\n' > "$r2/CLAUDE.md"
  git -C "$r2" commit -q -am newer
  b2="$(git -C "$r2" rev-parse "main~1^{tree}")"
  rm -f "$r2/.git/objects/${b2:0:2}/${b2:2}"
  out2="$(cd "$r2" && SHIELD_MAIN_REF=main "$SELF" --check "$tmp/base-unreadable" 2>&1)" || got2=$?
  case "$got2:$out2" in
    "2:"*"cannot read"*) echo "ok   [merge base unreadable] exit 2" ;;
    *) echo "FAIL [merge base unreadable]: exit $got2; output: $out2"; fail=1 ;;
  esac
  rc=0
  out="$(cd "$r" && SHIELD_MAIN_REF=main "$SELF")" || rc=$?
  case "$rc:$out" in
    "2:"*"5 worktree(s) read, 0 gone (not read), 1 could not be read; 2 of those read"*)
      echo "ok   [report] counts read, gone and unreadable trees apart, and exits 2 over the unreadable one" ;;
    *) echo "FAIL [report]: exit $rc; output: $out"; fail=1 ;;
  esac
  [ "$fail" -eq 0 ] || return 1
  echo "worktree-audit: self-test ok -- SAME, STALE, EDITED, EDITED+STALE, an unreadable tree, a non-git path and a clone with another main each observed."
}

case "$MODE" in
  report) report ;;
  check) check ;;
  self-test) self_test ;;
esac
