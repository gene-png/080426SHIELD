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

PRIMARY_TREE="${SHIELD_PRIMARY_TREE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WORKTREE="$(git rev-parse --show-toplevel)"
IMAGE="${SHIELD_VERIFY_IMAGE:-node:22-bookworm}"

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
    echo "verify-in-worktree: COULD NOT FULLY LOOK -- packages/* did not type-check here (#175). apps/web errors: $((total - outside))." >&2
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
    echo "verify-in-worktree: see #175 (packages/ bind-mounted with no node_modules overlay)." >&2
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
eslint() {
  local out status
  out="$(run_in_container "cd apps/web && ./node_modules/.bin/eslint . --format unix" 2>&1)" && status=0 || status=$?
  printf '%s
' "$out"
  echo "verify-in-worktree: eslint -- ran \`eslint .\` from apps/web, the same invocation \`pnpm -F web lint\` uses"
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
  --self-test) self_test ;;
  --self-test-bound) self_test_bound ;;
  tsc)         tsc ;;
  vitest)      vitest ;;
  eslint)      eslint ;;
  --all)       echo "== tsc ==";    tsc
               echo "== vitest =="; vitest
               echo "== eslint =="; eslint ;;
  *) echo "usage: $0 [tsc|vitest|eslint|--all|--self-test|--self-test-bound]" >&2; exit 2 ;;
esac
