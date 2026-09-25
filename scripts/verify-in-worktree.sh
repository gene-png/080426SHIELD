#!/usr/bin/env bash
#
# Run the web toolchain against THIS worktree, in a throwaway container.
#
# ## Why this exists
#
# Standing guidance: an implementation agent runs typecheck, unit tests, lint
# and formatters in its OWN worktree, and only tests that genuinely need the
# shared stack go through it.
#
# That was not executable. `docker compose exec -T web ...` attaches to the
# shared `shield-v2` stack, which `docker-compose.yml` bind-mounts from
# whichever tree last ran `up`. So an agent in worktree B running the house
# typecheck gets a verdict about worktree A's code -- and a green from the
# wrong mount is indistinguishable from a green from your own work.
#
# That is not hypothetical. It fired on 2026-09-09, before any agents existed:
# a typecheck run for `fix/transport-silent-success` returned 0 while the
# container was mounted from a tree holding none of that branch.
#
# With multiple agents in separate worktrees sharing one stack, that failure
# is continuous rather than occasional. This script removes the shared stack
# from the loop entirely.
#
# ## How it avoids a per-worktree install
#
# `pnpm install` per worktree would cost ~762M the first time and needs pnpm
# on the host, which is not installed, and would resolve platform binaries
# that differ from the Linux container CI matches. None of that is necessary:
#
#   - `/app/node_modules` and `/app/apps/web/node_modules` are NAMED VOLUMES,
#     shared and already populated. Mount them read-write as the stack does.
#   - `packages/*/node_modules` is the exception: it lives in the HOST TREE,
#     written through the bind mount, and is gitignored -- so it is absent
#     from every fresh worktree. It is mounted read-only from the primary
#     tree, which is the one line that makes this work.
#
# The container is `--rm` and touches no running service, so any number of
# agents can run this concurrently without contending for the stack.
#
# ## Proven discriminating, not merely green
#
# Red-on-revert on 2026-09-09, mutation proved landed by grep before the
# result was read:
#
#     baseline  0
#     mutated   2   (a deliberate type error appended to lib/api.ts)
#     restored  0
#
# A harness that cannot fail is the defect it exists to prevent, so the check
# below is the same one, run as `--self-test`.
#
# ## Usage
#
#     scripts/verify-in-worktree.sh              # tsc, vitest, eslint
#     scripts/verify-in-worktree.sh tsc          # one of: tsc | vitest | eslint
#     scripts/verify-in-worktree.sh --self-test  # prove the mount is live
#
set -euo pipefail

# `set -euo pipefail` is mandatory here rather than stylistic: this script's
# whole purpose is to report a status someone will act on, and an exit code
# taken from a pipe's last stage or a trailing statement is the failure this
# repo has hit three times in one day.

# CHECKED BEFORE ANY WORK, and that position is the point. It sat just above
# the `case` at the bottom of the file -- after `git rev-parse`, after the path
# computation -- so on a machine without git in PATH the script exited 127
# before it could refuse a bad argument. An argument check that runs after the
# side effects is not an argument check.
# AN ARGUMENT THIS SCRIPT DOES NOT IMPLEMENT MUST NOT SUCCEED, and the
# dangerous slot here is the SECOND one, not the first.
#
# The `case` below reads `$1` and rejects an unknown mode correctly. It ignored
# everything after it -- so `verify-in-worktree.sh tsc --self-test` ran an
# ordinary tsc, exited 0, and read as a self-test having run. That is the worst
# instance of this shape in the repo, because `CLAUDE.md` tells readers to run
# `--self-test` before trusting a clean result from a worktree they have not
# verified from before: the one command whose job is to prove the harness can
# fail was silently not running, and the reward for asking was a green.
#
# Arity is judged on `$#`, NOT on `${1:-}`. `case "${1:---all}"` cannot tell an
# ABSENT argument from an explicit `""` -- both take the `--all` default, so
# `verify-in-worktree.sh ""` quietly ran the entire toolchain.
if [ "$#" -gt 1 ]; then
  echo "FAIL: too many arguments; got: $*" >&2
  echo "      This script takes ONE mode. Everything after the first was" >&2
  echo "      ignored, so \`$0 tsc --self-test\` ran an ordinary tsc, exited 0," >&2
  echo "      and read as a self-test having run." >&2
  exit 2
fi
if [ "$#" -eq 1 ] && [ -z "$1" ]; then
  echo "FAIL: empty argument. An explicit \"\" is not 'no argument' -- it took" >&2
  echo "      the --all default and ran the whole toolchain." >&2
  exit 2
fi

# AND THE MODE IS VALIDATED HERE TOO, not only by the `case` at the bottom.
#
# The arity guard above catches a SECOND argument. A single unrecognised mode
# fell through it and reached the `case` 150 lines below -- which is after
# `git rev-parse` on the next line, so on a machine without git in PATH the
# script exited 127 instead of refusing. Measured: `verify-in-worktree.sh
# --definitely-not-a-flag` in a container without git gave
# `line 99: git: command not found`, exit 127.
#
# `is_known_mode` is the authority and holds the list ONCE. The `case` at the
# bottom still names each mode because that is the dispatch, and its `*)` arm
# is unreachable while the two agree -- it says so rather than silently being
# a second opinion.
is_known_mode() {
  case "$1" in
    --self-test|--self-test-bound|--check-mounts|tsc|vitest|eslint|--all) return 0 ;;
    *) return 1 ;;
  esac
}

if ! is_known_mode "${1:---all}"; then
  echo "FAIL: unknown mode '${1:-}'." >&2
  echo "usage: $0 [tsc|vitest|eslint|--all|--check-mounts|--self-test|--self-test-bound]" >&2
  exit 2
fi

# The PRIMARY TREE is the one `pnpm install` ran in, because that is the only
# tree holding `packages/*/node_modules`. Derive it from git's COMMON dir.
#
# It used to be derived from THIS SCRIPT'S OWN LOCATION:
#
#     PRIMARY_TREE="${SHIELD_PRIMARY_TREE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
#
# Every worktree carries its own copy of the script, so from a worktree that
# resolved to the WORKTREE -- precisely the tree that lacks the node_modules
# this mount exists to supply. The mount then named a host path that does not
# exist, and Docker CREATES a missing bind source as an empty directory and
# mounts it, SHADOWING the real `packages/design-system/node_modules` the line
# above had just provided.
#
# Measured 2026-09-21, `wt-353` vs the primary tree, same commit content:
#
#   primary tree   tsc 0 errors      vitest 53/53 files, 575 tests, exit 0
#   worktree       tsc 139 errors    vitest 33/53 files, 414 tests, exit 2
#                  (138 in packages/*)   20 files never collected
#
# So the one line the header calls "the line that makes this work" was correct
# only in the tree that does not need it. The script's own bound-printing is
# what kept this from being silent -- it reported COULD NOT FULLY LOOK and
# exited 2 rather than reporting 414 passed -- but a reader taking the test
# count instead of the exit code got a floor of unknown depth.
PRIMARY_TREE="${SHIELD_PRIMARY_TREE:-$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")}"
WORKTREE="$(git rev-parse --show-toplevel)"
IMAGE="${SHIELD_VERIFY_IMAGE:-node:22-bookworm}"

# REFUSE rather than mount a missing directory.
#
# Docker does not fail on a bind source that does not exist; it creates it
# empty. So a wrong PRIMARY_TREE cannot announce itself at mount time -- it
# announces itself as errors in `packages/*`, 150 lines later, attributed to
# the branch under test. That is the shape this whole script exists to
# prevent, reached through the script itself.
#
# Named for the CAUSE, not for the check: the most plausible misreading of a
# bare "mount check failed" is that Docker is unwell.
require_primary_tree() {
  if [ -d "$PRIMARY_TREE/packages/design-system/node_modules" ]; then
    return 0
  fi
  echo "verify-in-worktree: REFUSING -- no packages/design-system/node_modules under" >&2
  echo "    $PRIMARY_TREE" >&2
  echo "  That path is the PRIMARY TREE, the one \`pnpm install\` ran in. Docker would" >&2
  echo "  mount the missing directory as an EMPTY one, shadowing the real modules, and" >&2
  echo "  every \`packages/*\` import would fail to resolve -- reported against YOUR" >&2
  echo "  branch, which is not where the fault is." >&2
  echo "  Fix: run \`pnpm install\` in the primary tree, or set SHIELD_PRIMARY_TREE to" >&2
  echo "  a tree that has one." >&2
  exit 2
}
require_primary_tree

# MSYS rewrites any argument beginning with `/` when it crosses into a native
# Windows executable, and `docker.exe` is one. Without this, `-w /app` arrives
# as `C:/Program Files/Git/app` and the run dies with an unhelpful "working
# directory is invalid". See the MSYS entry in CLAUDE.md.
export MSYS_NO_PATHCONV=1

win() { printf '%s' "$1" | sed -e 's#^/\([a-z]\)/#\U\1:/#'; }

run_in_container() {
  docker run --rm \
    -v "$(win "$WORKTREE")/apps/web:/app/apps/web" \
    -v "$(win "$WORKTREE")/packages:/app/packages" \
    -v "$(win "$PRIMARY_TREE")/packages/design-system/node_modules:/app/packages/design-system/node_modules:ro" \
    -v "$(win "$WORKTREE")/package.json:/app/package.json" \
    -v "$(win "$WORKTREE")/pnpm-workspace.yaml:/app/pnpm-workspace.yaml" \
    -v shield-v2_node-modules-root:/app/node_modules \
    -v shield-v2_node-modules-web:/app/apps/web/node_modules \
    -w /app "$IMAGE" \
    sh -lc "$1"
}

# ---------------------------------------------------------------------------
# EVERY MODE PRINTS ITS BOUND.
#
# #258 landed the principle an hour before #261 landed this script without it:
# a gate states what it scanned -- `clean (6 documents)`, `scanned 1 file(s)`
# -- because silence from a check whose scope nobody remembers is how the
# 987ms attribution and the "48" both survived.
#
# This script shipped as a SANCTIONED verifier printing no bound, and the cost
# was immediate and exactly the predicted shape. Measured 2026-09-10 on a clean
# worktree cut from c1394da: 18 of 42 web test files fail to COLLECT, because
# `packages/design-system` cannot resolve `clsx` through its read-only mount
# (issue #175). So a green from `vitest` here meant "24 files passed and 18 were
# never asked", and nothing in the output said so. Two PRs stated that limit in
# their bodies as a workaround, which is a person remembering -- the thing a
# bound exists to replace.
#
# A file that fails to COLLECT is not a failing test. It is a file nobody ran,
# and it must not share an exit path with a file that ran and passed: that is
# "I could not look" wearing "nothing to complain about", which is the shape
# every gate in this repo now returns 2 for.
# ---------------------------------------------------------------------------

# Test files as they exist on disk. The denominator: what a reader assumes a
# green covered. Derived from the tree rather than from the tool's own report,
# on purpose -- asking the tool how much it looked at cannot detect the tool
# not looking.
count_test_files() {
  find "$WORKTREE/apps/web/src"     \( -name '*.test.ts' -o -name '*.test.tsx'        -o -name '*.spec.ts' -o -name '*.spec.tsx' \)     -type f 2>/dev/null | wc -l | tr -d '[:space:]'
}

# A vitest COLLECTION failure prints as `FAIL  path [ path ]` -- the file named
# twice -- which is what distinguishes "this module never loaded" from "a test
# inside it failed". Reads stdin so `--self-test` can drive it with known input
# in BOTH states: watching a guard fire proves it fires, and proves nothing
# about whether it passes. A guard that halts unconditionally is indistinguish-
# able from the hazard it exists to catch, and this repo has recorded that.
count_uncollected() {
  grep -cE '^ *FAIL .*\[ .* \]' || true
}

tsc() {
  local out status
  out="$(run_in_container "cd apps/web && ./node_modules/.bin/tsc --noEmit" 2>&1)" && status=0 || status=$?
  printf '%s
' "$out"
  local total outside
  total="$(printf '%s
' "$out" | grep -c 'error TS' || true)"
  # Errors from OUTSIDE apps/web are not this worktree's code. CI runs
  # `pnpm -F web exec tsc` and is green on main, so when these appear they are
  # the mount, not the branch -- and reporting them without saying so sends an
  # author to debug someone else's package.
  outside="$(printf '%s
' "$out" | grep 'error TS' | grep -c '\.\./\.\./packages/' || true)"
  echo "verify-in-worktree: tsc -- ${total} error(s), ${outside} of them outside apps/web (packages/*, i.e. the mount, not this branch)"
  if [ "$outside" -gt 0 ]; then
    echo "verify-in-worktree: COULD NOT FULLY LOOK -- packages/* did not type-check here. apps/web errors: $((total - outside))." >&2
    # THE TWIN of the vitest message below, and it was left behind for a
    # commit: that one was rewritten to stop attributing every failure to
    # #175 while this one went on doing it unconditionally, one function
    # above. `outside` counts errors whose PATH is under `packages/`, which a
    # genuine type error in that package's own source satisfies just as well
    # as a missing module does.
    #
    # `TS2307: Cannot find module` is the mount's signature -- nothing
    # resolves, so every downstream annotation degrades to implicit `any`.
    # Real type errors in that source carry other codes.
    if printf '%s\n' "$out" | grep -q 'error TS2307'; then
      echo "verify-in-worktree: modules under packages/ could not be RESOLVED, which is" >&2
      echo "verify-in-worktree: #175's shape -- packages/ is bind-mounted with no" >&2
      echo "verify-in-worktree: node_modules overlay. Not this branch." >&2
    else
      echo "verify-in-worktree: these are TYPE errors in packages/ source, not missing" >&2
      echo "verify-in-worktree: modules, so they are NOT the mount and NOT #175. Read them." >&2
    fi
    return 2
  fi
  return "$status"
}

vitest() {
  local out status
  out="$(run_in_container "cd apps/web && ./node_modules/.bin/vitest run" 2>&1)" && status=0 || status=$?
  printf '%s
' "$out"

  local found ran uncollected
  found="$(count_test_files)"
  uncollected="$(printf '%s
' "$out" | count_uncollected)"
  ran=$((found - uncollected))

  echo "verify-in-worktree: vitest -- ${ran}/${found} test files ran; ${uncollected} never collected"
  if [ "$uncollected" -gt 0 ]; then
    local why
    why="$(printf '%s
' "$out" | grep -m1 -E 'Failed to resolve import|Cannot find module' || true)"
    echo "verify-in-worktree: COULD NOT FULLY LOOK -- ${uncollected} of ${found} test files never ran, so this result is a floor of unknown depth." >&2
    [ -n "$why" ] && echo "verify-in-worktree: skip reason: ${why}" >&2
    # WHICH CAUSE, decided from the evidence rather than asserted.
    #
    # This block used to print "see #175" for every collection failure. #175 is
    # ONE cause; a wrong PRIMARY_TREE was a second, with identical symptoms and
    # the cause entirely inside this script. `require_primary_tree` closes that
    # one -- but a THIRD remains and is the commonest: `count_uncollected`
    # matches `FAIL <file> [ <file> ]`, which vitest prints for ANY collection
    # failure, so a broken import in this branch's own `apps/web/src`, or a
    # dependency in the lockfile that this volume has not installed, lands here
    # too. Telling that author it is a compose-file defect is worse than saying
    # nothing: they go and read `docker-compose.yml` instead of their own diff.
    #
    # The discriminator is the IMPORTING FILE, not the specifier. #175's shape
    # is a module unresolvable FROM a file under `packages/` -- the observed
    # form is `Failed to resolve import "clsx" from
    # "../../packages/design-system/src/utils/cn.ts"`. A failure from a file
    # under `apps/web/src` is this branch's code, whatever the specifier is.
    case "$why" in
      *packages/*|*'"@shield/'*)
        echo "verify-in-worktree: a module could not be resolved FROM a file under packages/." >&2
        echo "verify-in-worktree: that is #175's shape -- packages/ is bind-mounted with no" >&2
        echo "verify-in-worktree: node_modules overlay, so a HOST pnpm install leaves" >&2
        echo "verify-in-worktree: host-absolute symlinks the container cannot follow." >&2
        ;;
      "")
        echo "verify-in-worktree: no unresolved-import line was printed, so the cause is" >&2
        echo "verify-in-worktree: NOT known to be a mount problem. Read the output above" >&2
        echo "verify-in-worktree: before assuming it is one." >&2
        ;;
      *)
        echo "verify-in-worktree: the failing import is NOT from packages/, so this is most" >&2
        echo "verify-in-worktree: likely THIS BRANCH's own code -- a bad import path, a" >&2
        echo "verify-in-worktree: renamed module, or a dependency added to the lockfile that" >&2
        echo "verify-in-worktree: the node_modules volume has not installed yet." >&2
        echo "verify-in-worktree: exit 2 means these files never RAN, not that you are clear." >&2
        ;;
    esac
    return 2
  fi
  return "$status"
}
# EXACTLY what the repo gate runs, not stricter. `apps/web/package.json`
# defines `"lint": "eslint ."` and `ci.yml` runs `pnpm -F web lint`. A first
# draft of this file passed `--max-warnings=0` over `src`, and independent
# verification measured the difference: `eslint .` exits 0 with 3 warnings,
# `eslint src --max-warnings=0` exits 1 with 2. A harness stricter than the
# gate produces a red no CI run can reproduce, and the natural repair is to
# "fix" untouched files -- here two `window.location.assign` call sites CI
# accepts. That is a harness steering an author into changes nobody asked for.
#
# `--format unix` used to follow `eslint .` here. ESLint 9 removed that
# formatter from core, so every run exited 2 ("The unix formatter is no longer
# part of core ESLint") and then printed the line below claiming the same
# invocation as the gate. The web-lint half of worktree verification checked
# nothing. The message is now built from the command that ran, so the two
# cannot disagree again.
eslint() {
  local out status cmd="./node_modules/.bin/eslint ."
  out="$(run_in_container "cd apps/web && $cmd" 2>&1)" && status=0 || status=$?
  printf '%s
' "$out"
  echo "verify-in-worktree: eslint -- ran \`$cmd\` from apps/web (\`pnpm -F web lint\` runs \`eslint .\`), exit $status"
  return "$status"
}

# apps/web errors ONLY, as a number.
#
# `self_test` asks one question -- does the container SEE this worktree -- and
# that question does not depend on whether `packages/*` resolves. Scoping it
# here keeps the mount check usable while #175 is open. Without this, adding
# the bound above would have left the harness unable to self-test at all, which
# is a worse defect than the one being fixed.
tsc_appsweb_error_count() {
  run_in_container "cd apps/web && ./node_modules/.bin/tsc --noEmit" 2>&1     | grep 'error TS' | grep -vc '\.\./\.\./packages/' || true
}

self_test() {
  local probe="apps/web/src/lib/__verify_probe.ts"
  echo "self-test: the mount must SEE this worktree, so make it fail on purpose"
  local baseline
  baseline="$(tsc_appsweb_error_count)"
  echo "self-test: baseline apps/web errors: ${baseline} (packages/* excluded -- see #175)"
  if [ "$baseline" -ne 0 ]; then
    echo "self-test: BASELINE NOT GREEN -- ${baseline} apps/web error(s). Fix the" >&2
    echo "           tree before trusting this harness." >&2
    return 2
  fi
  printf 'export const probe: number = "not a number";\n' > "$WORKTREE/$probe"
  # Prove the mutation landed BEFORE reading its result. A revert or a write
  # that silently did not apply reports the same green as a harness that
  # cannot fail, and it is the answer you are hoping for.
  grep -q 'not a number' "$WORKTREE/$probe" || { echo "self-test: probe never written" >&2; return 2; }
  local mutated
  mutated="$(tsc_appsweb_error_count)"
  rm -f "$WORKTREE/$probe"
  if [ "$mutated" -eq 0 ]; then
    echo "self-test: FAILED -- a deliberate type error did not turn this red." >&2
    echo "           The container is not reading $WORKTREE. Do not trust any" >&2
    echo "           green from it; it is describing some other tree." >&2
    return 1
  fi
  echo "self-test: PASS -- apps/web errors: baseline 0, mutated $mutated, probe removed"
}

self_test_bound() {
  # BOTH STATES, against fixed input, so neither branch is assumed.
  local clean broken n
  clean=' Test Files  42 passed (42)
 ✓ src/a.test.tsx (3 tests) 12ms'
  broken=' FAIL  src/a.test.tsx [ src/a.test.tsx ]
 FAIL  src/b.test.tsx [ src/b.test.tsx ]
 ✓ src/c.test.tsx (3 tests) 12ms
 FAIL  src/d.test.tsx > it does a thing'

  n="$(printf '%s
' "$clean" | count_uncollected)"
  echo "self-test-bound: clean run -> ${n} uncollected (expect 0)"
  [ "$n" -eq 0 ] || { echo "FAIL: the guard fires on a clean run" >&2; return 1; }

  n="$(printf '%s
' "$broken" | count_uncollected)"
  echo "self-test-bound: broken run -> ${n} uncollected (expect 2)"
  [ "$n" -eq 2 ] || { echo "FAIL: expected 2, got ${n}" >&2; return 1; }

  # The discriminating case: `FAIL ... > it does a thing` is a FAILING TEST in
  # a file that ran, not an uncollected file. If the pattern counted it, every
  # ordinary red would be reported as "never asked" and the exit-2 branch would
  # fire on a working suite -- which is how a bound becomes noise and then gets
  # ignored.
  echo "self-test-bound: a failing test inside a collected file is not counted -- OK"
  echo "self-test-bound: PASS"
}

case "${1:---all}" in
  # Reports the resolved trees and stops, without starting a container, so
  # `require_primary_tree`'s PASSING state is assertable -- a guard watched
  # only while it fires has been observed in one state.
  #
  # IT CHECKS ONE MOUNT, NOT ALL OF THEM, and says so rather than printing
  # "mounts OK". `run_in_container` declares five host binds; this validates
  # the `packages/design-system/node_modules` one, because that is the bind
  # whose source is a DIFFERENT tree and therefore the one that can be wrong
  # while everything else looks right.
  #
  # The other four are not checked here, and two of them -- `package.json`
  # and `pnpm-workspace.yaml` -- are FILE binds, which Docker materialises as
  # DIRECTORIES when the source is absent. That is a real silent failure and
  # it is simply out of this mode's scope; an earlier draft of this comment
  # claimed "arriving here at all means the mounts are sound", which was the
  # over-claim, in the mode added to make a claim checkable.
  --check-mounts)
    echo "verify-in-worktree: primary tree   $PRIMARY_TREE"
    echo "verify-in-worktree: worktree       $WORKTREE"
    echo "verify-in-worktree: checked 1 of 5 host binds -- packages/design-system/node_modules resolves"
    ;;
  --self-test) self_test ;;
  --self-test-bound) self_test_bound ;;
  tsc)         tsc ;;
  vitest)      vitest ;;
  eslint)      eslint ;;
  --all)       echo "== tsc ==";    tsc
               echo "== vitest =="; vitest
               echo "== eslint =="; eslint ;;
  # UNREACHABLE while this list and `is_known_mode` agree -- the mode is
  # validated at the top of the file, before any work. Kept as fail-closed
  # cover for the case where they drift, and it says which check is the
  # authority so the next reader fixes the right one.
  *) echo "FAIL: unknown mode '$1' reached the dispatch." >&2
     echo "      is_known_mode() accepted it and this case did not, so the two" >&2
     echo "      have drifted. is_known_mode is the authority." >&2
     exit 2 ;;
esac
