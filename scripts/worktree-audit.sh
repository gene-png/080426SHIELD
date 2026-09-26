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
# git gives these precedence over `-C`. Inherited from a hook (hooks export
# GIT_DIR), they would point every `-C <tree>` below at ONE repository, so
# report and --check would read it for every tree. (--self-test goes further
# and re-runs itself under `env -i`; see self_test.)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES

LIMIT=150000
# Absolute, because --self-test re-invokes this script from another directory.
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
MAIN="${SHIELD_MAIN_REF:-origin/main}"
# $MAIN resolved ONCE, by report or check. classify reads this, never the ref:
# a fetch landing mid-run must not move main between two trees, or between
# --check's comparison of the two repositories and its classification.
MAIN_SHA=""

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
    --self-test-inner)
      # Internal: only the clean-environment re-exec in self_test() may run
      # it. Run by hand it would test under whatever environment you have.
      if [ "$#" -ne 1 ] || [ "${WORKTREE_AUDIT_CLEAN_ENV:-}" != 1 ]; then
        echo "FAIL: --self-test-inner is internal; run --self-test." >&2
        exit 2
      fi
      MODE=self-test-inner
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
  main_blob="$(blob "$dir" "$MAIN_SHA")" || return 2
  [ -n "$main_blob" ] || return 2
  head_blob="$(blob "$dir" HEAD)" || return 2
  base="$(git -C "$dir" merge-base HEAD "$MAIN_SHA" 2>/dev/null)" || return 2
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
  behind="$(git -C "$dir" rev-list --count "HEAD..$MAIN_SHA")" || return 2
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
  MAIN_SHA="$(git rev-parse --verify -q "$MAIN^{commit}")" || {
    echo "worktree-audit: could not look -- no ref '$MAIN'. Fetch first." >&2
    return 2
  }
  echo "worktree-audit: each worktree's CLAUDE.md against $MAIN (${MAIN_SHA:0:12})"
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
  mine="$(git rev-parse --verify -q "$MAIN^{commit}" 2>/dev/null)" || {
    echo "worktree-audit: could not look -- no ref '$MAIN' in the repository this was run from." >&2
    return 2
  }
  theirs="$(git -C "$TARGET" rev-parse --verify -q "$MAIN^{commit}" 2>/dev/null)" || {
    echo "worktree-audit: could not look -- '$TARGET' is not a git tree, or has no ref '$MAIN'." >&2
    return 2
  }
  if [ "$mine" != "$theirs" ]; then
    echo "worktree-audit: could not look -- '$TARGET' resolves $MAIN to ${theirs:0:12}, the repository this was run from to ${mine:0:12}." >&2
    echo "  It is a separate clone comparing against its own $MAIN. Fetch both, or run this from the clone." >&2
    return 2
  fi
  MAIN_SHA="$mine"
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

# --self-test re-runs itself in a CLEAN environment rather than listing what
# to clear. Four review rounds each found the next variable or config key an
# enumeration had missed (GIT_DIR, the global config, GIT_CONFIG, fsmonitor);
# `env -i` drops every inherited variable at once, including ones nobody has
# named yet. What it passes through is the minimal set measured to run here
# (2026-09-25, Git Bash): PATH to find bash and git, HOME and TMPDIR inside a
# fresh scratch root, and its own variables. SYSTEMROOT was measured NOT
# needed; if a platform needs it, the self-test fails loudly, not silently.
self_test() {
  local rc=0
  # A GLOBAL, and EXIT rather than RETURN: a `set -e` death anywhere must still
  # remove it, and an EXIT trap runs after every function's locals are gone.
  ST_ROOT="$(mktemp -d)"
  trap 'rm -rf "$ST_ROOT"' EXIT
  mkdir "$ST_ROOT/home"
  env -i PATH="$PATH" HOME="$ST_ROOT/home" TMPDIR="$ST_ROOT" \
    GIT_CONFIG_NOSYSTEM=1 WORKTREE_AUDIT_CLEAN_ENV=1 \
    WORKTREE_AUDIT_NESTED="${WORKTREE_AUDIT_NESTED:-}" \
    "${BASH:-bash}" "$SELF" --self-test-inner || rc=$?
  return "$rc"
}

self_test_inner() {
  local tmp r rc fail=0 out tree observed
  ST_TMP="$(mktemp -d)"
  trap 'rm -rf "$ST_TMP"' EXIT  # a global, for the reason given in self_test
  tmp="$ST_TMP"
  # The second layer, per command: an empty hooks dir, no signing, `--local`
  # on every `config`, and `init --template=`. It covers hooks and signing
  # only; the clean environment above is what drops the global config.
  mkdir "$tmp/no-hooks"
  tg() { git -c core.hooksPath="$tmp/no-hooks" -c commit.gpgsign=false "$@"; }
  r="$tmp/repo"
  mkdir "$r"
  tg -C "$r" init -q --template= -b main
  tg -C "$r" config --local user.email t@example.invalid
  tg -C "$r" config --local user.name t
  tg -C "$r" config --local core.autocrlf false
  printf 'rules v1\n\nCANARY\n' > "$r/CLAUDE.md"
  tg -C "$r" add -A && tg -C "$r" commit -q -m v1
  tg clone -q --template= "$r" "$tmp/old-clone"
  tg -C "$r" worktree add -q "$tmp/stale" -b stale
  tg -C "$r" worktree add -q "$tmp/edited-behind" -b edited-behind
  printf 'rules v1, edited on a branch\n\nCANARY\n' > "$tmp/edited-behind/CLAUDE.md"
  tg -C "$tmp/edited-behind" commit -q -am edit
  printf 'rules v2\n\nCANARY\n' > "$r/CLAUDE.md"
  tg -C "$r" commit -q -am v2
  tg -C "$r" worktree add -q "$tmp/same" -b same
  tg -C "$r" worktree add -q "$tmp/edited" -b edited
  printf 'rules v2, edited on a branch\n\nCANARY\n' > "$tmp/edited/CLAUDE.md"
  tg -C "$tmp/edited" commit -q -am edit
  # A tree whose HEAD commit's tree object is gone: readable ref, unreadable tree.
  tg -C "$r" worktree add -q "$tmp/unreadable" -b unreadable
  printf 'rules v2, a commit whose tree is then deleted\n\nCANARY\n' > "$tmp/unreadable/CLAUDE.md"
  tg -C "$tmp/unreadable" commit -q -am unreadable
  tree="$(tg -C "$tmp/unreadable" rev-parse "HEAD^{tree}")"
  rm -f "$r/.git/objects/${tree:0:2}/${tree:2}"
  if tg -C "$r" cat-file -e "$tree" 2>/dev/null; then
    echo "FAIL [setup]: the tree object $tree is still readable after deleting it"
    return 1
  fi
  # --check runs FROM the temp repository: it resolves main where it is run.
  # These children are deliberately BARE (no `tg`): they are the script under
  # test, and run report and --check exactly as a caller would.
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
  tg -C "$r2" init -q --template= -b main
  tg -C "$r2" config --local user.email t@example.invalid
  tg -C "$r2" config --local user.name t
  tg -C "$r2" config --local core.autocrlf false
  printf 'base rules\n' > "$r2/CLAUDE.md"
  tg -C "$r2" add -A && tg -C "$r2" commit -q -m base
  tg -C "$r2" worktree add -q "$tmp/base-unreadable" -b base-unreadable
  printf 'base rules, edited on a branch\n' > "$tmp/base-unreadable/CLAUDE.md"
  tg -C "$tmp/base-unreadable" commit -q -am edit
  printf 'newer rules\n' > "$r2/CLAUDE.md"
  tg -C "$r2" commit -q -am newer
  b2="$(tg -C "$r2" rev-parse "main~1^{tree}")"
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
  # A SENTINEL repository for the override cases. Never a real one.
  local s="$tmp/sentinel" before after got3=0 out3
  mkdir "$s"
  tg -C "$s" init -q --template= -b main
  tg -C "$s" config --local user.email t@example.invalid
  tg -C "$s" config --local user.name t
  printf 'sentinel\n' > "$s/file"
  tg -C "$s" add -A && tg -C "$s" commit -q -m sentinel
  # --check itself, with GIT_DIR and GIT_INDEX_FILE inherited as a hook would
  # export them. They outrank `-C`, so without the `unset` at the top of the
  # script every read goes to the sentinel, which is SAME against itself.
  out3="$(cd "$r" && GIT_DIR="$s/.git" GIT_INDEX_FILE="$s/.git/index" SHIELD_MAIN_REF=main \
    "$SELF" --check "$tmp/stale" 2>&1)" || got3=$?
  case "$got3:$out3" in
    "1:"*": STALE against main at"*) echo "ok   [--check under an inherited GIT_DIR and GIT_INDEX_FILE] still reads the target: STALE, exit 1" ;;
    *) echo "FAIL [--check under an inherited GIT_DIR and GIT_INDEX_FILE]: exit $got3; output: $out3"; fail=1 ;;
  esac
  observed="SAME, STALE, EDITED, EDITED+STALE, an unreadable tree, a non-git path, a clone with another main and --check under an inherited GIT_DIR"
  # The two cases below each run a NESTED self-test, which skips them (no
  # recursion) and says so. A caller exporting WORKTREE_AUDIT_NESTED gets the
  # same skips, printed, and they are left out of the closing claim.
  if [ -n "${WORKTREE_AUDIT_NESTED:-}" ]; then
    echo "skip [self-test under an inherited GIT_DIR and GIT_INDEX_FILE] WORKTREE_AUDIT_NESTED is set"
    echo "skip [self-test under a hostile global config] WORKTREE_AUDIT_NESTED is set"
    echo "skip [self-test under an inherited GIT_CONFIG] WORKTREE_AUDIT_NESTED is set"
  else
    local nested=0
    # --no-optional-locks: a plain `status` may refresh the index, which would
    # change its bytes and read as the pollution this case exists to catch.
    before="$(tg -C "$s" rev-parse HEAD) $(tg -C "$s" rev-list --count HEAD) $(cksum < "$s/.git/index") [$(tg --no-optional-locks -C "$s" status --porcelain)]"
    WORKTREE_AUDIT_NESTED=1 GIT_DIR="$s/.git" GIT_INDEX_FILE="$s/.git/index" \
      "$SELF" --self-test > "$tmp/nested.out" 2>&1 || nested=$?
    after="$(tg -C "$s" rev-parse HEAD) $(tg -C "$s" rev-list --count HEAD) $(cksum < "$s/.git/index") [$(tg --no-optional-locks -C "$s" status --porcelain)]"
    if [ "$nested" -eq 0 ] && [ "$before" = "$after" ]; then
      echo "ok   [self-test under an inherited GIT_DIR and GIT_INDEX_FILE] passed, and the sentinel repo is untouched"
    else
      echo "FAIL [self-test under an inherited GIT_DIR and GIT_INDEX_FILE]: nested exit $nested; sentinel before: $before; after: $after"
      tail -5 "$tmp/nested.out"
      fail=1
    fi
    # A HOSTILE environment. Its global config sets core.hooksPath and
    # init.templateDir to hooks, commit.gpgsign on, and core.fsmonitor to a
    # program -- which no `-c` here overrides, so only a clean environment
    # keeps it out. Each writes a marker outside every scratch repo. GIT_CONFIG
    # names a file that `git config` would write to, and must stay unchanged.
    local h="$tmp/hostile-home" hooks="$tmp/hostile-hooks" tmpl="$tmp/hostile-template"
    local ran="$tmp/HOOK_RAN" fsmon="$tmp/FSMONITOR_RAN" gc="$tmp/hostile.gitconfig"
    local hook probe="$tmp/probe" nested2=0 gc_before
    mkdir -p "$h" "$hooks" "$tmpl/hooks" "$probe"
    for hook in pre-commit post-commit post-checkout; do
      printf '#!/bin/sh\ntouch "%s"\n' "$ran" > "$hooks/$hook"
      cp "$hooks/$hook" "$tmpl/hooks/$hook"
      chmod +x "$hooks/$hook" "$tmpl/hooks/$hook"
    done
    printf '#!/bin/sh\ntouch "%s"\nexit 1\n' "$fsmon" > "$tmp/fsmonitor.sh"
    chmod +x "$tmp/fsmonitor.sh"
    printf '[core]\n\thooksPath = %s\n\tfsmonitor = %s\n[init]\n\ttemplateDir = %s\n[commit]\n\tgpgsign = true\n' \
      "$(winpath "$hooks")" "$(winpath "$tmp/fsmonitor.sh")" "$(winpath "$tmpl")" > "$h/.gitconfig"
    printf '[user]\n\tname = hostile\n' > "$gc"
    gc_before="$(cksum < "$gc")"
    # Prove the fixture is LIVE before trusting a clean result. The probe is
    # deliberately BARE git under the hostile HOME, with the `-c` layer on: it
    # must still run the fsmonitor, which is what shows that `-c` alone does
    # not cover this and the clean environment is load-bearing.
    HOME="$h" git -C "$probe" init -q -b main
    printf 'x\n' > "$probe/x"
    HOME="$h" git -c core.hooksPath="$tmp/no-hooks" -c commit.gpgsign=false \
      -c user.email=t@example.invalid -c user.name=t -C "$probe" add -A
    HOME="$h" git -c core.hooksPath="$tmp/no-hooks" -c commit.gpgsign=false \
      -c user.email=t@example.invalid -c user.name=t -C "$probe" commit -q -m probe
    if [ ! -e "$fsmon" ]; then
      echo "FAIL [self-test under a hostile global config]: setup -- the hostile fsmonitor did not run under the -c layer, so this case would prove nothing"
      fail=1
    else
      # Two nested runs, one signal each, so a lost clean environment is
      # caught by what it lets in rather than by whichever fails first.
      rm -f "$ran" "$fsmon"
      HOME="$h" WORKTREE_AUDIT_NESTED=1 "$SELF" --self-test > "$tmp/nested2.out" 2>&1 || nested2=$?
      if [ "$nested2" -eq 0 ] && [ ! -e "$ran" ] && [ ! -e "$fsmon" ]; then
        echo "ok   [self-test under a hostile global config] passed; no hook or fsmonitor ran"
      else
        echo "FAIL [self-test under a hostile global config]: nested exit $nested2; hook ran: $([ -e "$ran" ] && echo yes || echo no); fsmonitor ran: $([ -e "$fsmon" ] && echo yes || echo no)"
        tail -5 "$tmp/nested2.out"
        fail=1
      fi
      local nested3=0
      GIT_CONFIG="$gc" WORKTREE_AUDIT_NESTED=1 "$SELF" --self-test > "$tmp/nested3.out" 2>&1 || nested3=$?
      if [ "$nested3" -eq 0 ] && [ "$(cksum < "$gc")" = "$gc_before" ]; then
        echo "ok   [self-test under an inherited GIT_CONFIG] passed; the file it names is unchanged"
      else
        echo "FAIL [self-test under an inherited GIT_CONFIG]: nested exit $nested3; file changed: $([ "$(cksum < "$gc")" = "$gc_before" ] && echo no || echo yes)"
        tail -5 "$tmp/nested3.out"
        fail=1
      fi
    fi
    observed="$observed, a self-test under an inherited GIT_DIR, a hostile global config, and an inherited GIT_CONFIG"
  fi
  [ "$fail" -eq 0 ] || return 1
  echo "worktree-audit: self-test ok -- $observed each observed."
}

winpath() { # a path git.exe can read on Windows; unchanged elsewhere
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

case "$MODE" in
  report) report ;;
  check) check ;;
  self-test) self_test ;;
  self-test-inner) self_test_inner ;;
esac
