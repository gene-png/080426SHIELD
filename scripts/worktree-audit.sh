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
# rules).
#
# ## What it compares
#
# Blob ids, not text: a tree's `HEAD:CLAUDE.md` against the main ref's, and
# against the one at their merge base.
#
#   SAME    the tree's CLAUDE.md IS main's.
#   STALE   the tree's branch never changed CLAUDE.md, and main has since.
#   EDITED  the branch changed CLAUDE.md, and main has not changed it since the
#           branch point -- the tree has every rule main has, plus its own.
#   EDITED+STALE  both: the branch changed it AND main moved on, so the tree
#           lacks main's newer rules.
#   MISSING the tree's HEAD has no CLAUDE.md at all.
#
# Also per tree: how far behind main, uncommitted changes, the file's size
# against the 150,000-byte reader limit, and whether its last non-empty line is
# the canary main currently ends with (read from main, not hardcoded).
#
# ## Usage
#
#     scripts/worktree-audit.sh                      # report every worktree
#     scripts/worktree-audit.sh --check <path>       # one tree, before dispatch
#     scripts/worktree-audit.sh --self-test          # prove both states
#     SHIELD_MAIN_REF=main scripts/worktree-audit.sh # compare against another ref
#
# `--check` is the pre-dispatch refusal #439 asks for: exit 0 for SAME or
# EDITED, 1 for STALE, EDITED+STALE or MISSING (the agent would read rules main
# no longer has, or none), 2 when it could not look. The report mode exits 0
# when it read every tree and 2 when it could not look at one. The committed
# CLAUDE.md is what is compared; uncommitted edits are flagged, not judged.
#
# LIMITS: it compares CLAUDE.md only, not `.claude/agents/*.md`, which go stale
# the same way. A tree whose directory is gone is reported as such and not
# compared. It reads the main ref as it is locally: fetch first, or "SAME" means
# "same as a stale main".
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

blob() { # <dir> <rev> -> the CLAUDE.md blob id at <rev>, or empty if none
  git -C "$1" rev-parse --verify -q "$2:CLAUDE.md" 2>/dev/null || true
}

last_line() { # <file> -> its last non-empty line
  awk 'NF { l = $0 } END { print l }' "$1"
}

# classify <dir> -> prints "STATE behind dirty bytes canary", or returns 2
classify() {
  local dir="$1" head main_blob head_blob base base_blob state behind dirty bytes canary want
  head="$(git -C "$dir" rev-parse --verify -q HEAD 2>/dev/null)" || return 2
  main_blob="$(blob "$dir" "$MAIN")"
  [ -n "$main_blob" ] || return 2
  head_blob="$(blob "$dir" HEAD)"
  base="$(git -C "$dir" merge-base HEAD "$MAIN" 2>/dev/null)" || return 2
  base_blob="$(blob "$dir" "$base")"
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
    bytes="$(wc -c < "$dir/CLAUDE.md" | tr -d ' ')"
    want="$(git -C "$dir" show "$MAIN:CLAUDE.md" | awk 'NF { l = $0 } END { print l }')" || return 2
    if [ "$(last_line "$dir/CLAUDE.md")" = "$want" ]; then canary=ok; else canary=MISSING; fi
  else
    bytes=0
    canary=MISSING
  fi
  echo "$state $behind $dirty $bytes $canary"
}

report_one() { # <dir> <branch> -> one line; returns 2 if it could not look
  local dir="$1" branch="$2" out state behind dirty bytes canary over=""
  if [ ! -d "$dir" ]; then
    printf '%-13s %s  (%s)\n' "GONE" "$dir" "$branch"
    return 0
  fi
  if ! out="$(classify "$dir")"; then
    printf '%-13s %s  (%s)\n' "COULD-NOT-LOOK" "$dir" "$branch"
    return 2
  fi
  read -r state behind dirty bytes canary <<<"$out"
  if [ "$bytes" -gt "$LIMIT" ]; then over=" OVER-LIMIT"; fi
  printf '%-13s behind=%-4s dirty=%-3s bytes=%s%s canary=%s  %s  (%s)\n' \
    "$state" "$behind" "$dirty" "$bytes" "$over" "$canary" "$dir" "$branch"
}

report() {
  local rc=0 path="" branch="" line total=0 stale=0 could_not=0 row
  git rev-parse --verify -q "$MAIN" >/dev/null || {
    echo "worktree-audit: could not look -- no ref '$MAIN'. Fetch first." >&2
    return 2
  }
  echo "worktree-audit: each worktree's CLAUDE.md against $MAIN ($(git rev-parse --short "$MAIN"))"
  # `git worktree list --porcelain`: a block per tree, `worktree <path>` first.
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      "worktree "*) path="${line#worktree }"; branch="detached" ;;
      "branch "*) branch="${line#branch refs/heads/}" ;;
      "")
        if [ -n "$path" ]; then
          total=$((total + 1))
          if row="$(report_one "$path" "$branch")"; then :; else could_not=$((could_not + 1)); fi
          echo "$row"
          case "$row" in STALE* | EDITED+STALE* | MISSING*) stale=$((stale + 1)) ;; esac
          path=""
        fi
        ;;
    esac
  done < <(git worktree list --porcelain; echo)
  echo "worktree-audit: $total worktree(s) read; $stale would give an agent rules main no longer has (STALE, EDITED+STALE or MISSING); $could_not could not be read."
  if [ "$total" -eq 0 ] || [ "$could_not" -gt 0 ]; then rc=2; fi
  return "$rc"
}

check() {
  local out state
  git -C "$TARGET" rev-parse --verify -q "$MAIN" >/dev/null 2>&1 || {
    echo "worktree-audit: could not look -- '$TARGET' is not a git tree, or has no ref '$MAIN'." >&2
    return 2
  }
  out="$(classify "$TARGET")" || {
    echo "worktree-audit: could not look -- cannot classify '$TARGET'." >&2
    return 2
  }
  state="${out%% *}"
  echo "worktree-audit: $TARGET: $state ($out)"
  case "$state" in
    SAME | EDITED) return 0 ;;
    *)
      echo "  This tree's CLAUDE.md lacks rules $MAIN has. Do not dispatch an agent into it" >&2
      echo "  without merging $MAIN first." >&2
      return 1
      ;;
  esac
}

self_test() {
  local tmp r rc fail=0
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
  expect() { # <path> <want exit> <want state>
    local got out
    got=0
    out="$(SHIELD_MAIN_REF=main "$SELF" --check "$1" 2>&1)" || got=$?
    case "$out" in *": $3 "*) ;; *) got="wrong-state" ;; esac
    if [ "$got" = "$2" ]; then echo "ok   [$3] exit $2"; else echo "FAIL [$3]: got $got, wanted exit $2 with state $3; output: $out"; fail=1; fi
  }
  expect "$tmp/same" 0 SAME
  expect "$tmp/stale" 1 STALE
  expect "$tmp/edited" 0 EDITED
  expect "$tmp/edited-behind" 1 EDITED+STALE
  rc=0
  SHIELD_MAIN_REF=main "$SELF" --check "$tmp" >/dev/null 2>&1 || rc=$?
  if [ "$rc" = 2 ]; then echo "ok   [not a git tree] exit 2"; else echo "FAIL [not a git tree]: exit $rc, wanted 2"; fail=1; fi
  rc=0
  out="$(cd "$r" && SHIELD_MAIN_REF=main "$SELF")" || rc=$?
  case "$out" in
    *"5 worktree(s) read; 2 would give"*) echo "ok   [report] counts every tree and the two stale ones" ;;
    *) echo "FAIL [report]: exit $rc; output: $out"; fail=1 ;;
  esac
  [ "$fail" -eq 0 ] || return 1
  echo "worktree-audit: self-test ok -- SAME, STALE, EDITED, EDITED+STALE and could-not-look each observed."
}

case "$MODE" in
  report) report ;;
  check) check ;;
  self-test) self_test ;;
esac
