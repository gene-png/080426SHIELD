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

tsc()    { run_in_container "cd apps/web && ./node_modules/.bin/tsc --noEmit"; }
vitest() { run_in_container "cd apps/web && ./node_modules/.bin/vitest run"; }
# EXACTLY what the repo gate runs, not stricter. `apps/web/package.json`
# defines `"lint": "eslint ."` and `ci.yml` runs `pnpm -F web lint`. A first
# draft of this file passed `--max-warnings=0` over `src`, and independent
# verification measured the difference: `eslint .` exits 0 with 3 warnings,
# `eslint src --max-warnings=0` exits 1 with 2. A harness stricter than the
# gate produces a red no CI run can reproduce, and the natural repair is to
# "fix" untouched files -- here two `window.location.assign` call sites CI
# accepts. That is a harness steering an author into changes nobody asked for.
eslint() { run_in_container "cd apps/web && ./node_modules/.bin/eslint ."; }

self_test() {
  local probe="apps/web/src/lib/__verify_probe.ts"
  echo "self-test: the mount must SEE this worktree, so make it fail on purpose"
  if ! tsc >/dev/null 2>&1; then
    echo "self-test: BASELINE NOT GREEN -- fix the tree before trusting this harness" >&2
    return 2
  fi
  printf 'export const probe: number = "not a number";\n' > "$WORKTREE/$probe"
  # Prove the mutation landed BEFORE reading its result. A revert or a write
  # that silently did not apply reports the same green as a harness that
  # cannot fail, and it is the answer you are hoping for.
  grep -q 'not a number' "$WORKTREE/$probe" || { echo "self-test: probe never written" >&2; return 2; }
  local mutated=0
  tsc >/dev/null 2>&1 || mutated=$?
  rm -f "$WORKTREE/$probe"
  if [ "$mutated" -eq 0 ]; then
    echo "self-test: FAILED -- a deliberate type error did not turn this red." >&2
    echo "           The container is not reading $WORKTREE. Do not trust any" >&2
    echo "           green from it; it is describing some other tree." >&2
    return 1
  fi
  echo "self-test: PASS -- baseline 0, mutated $mutated, probe removed"
}

case "${1:---all}" in
  --self-test) self_test ;;
  tsc)         tsc ;;
  vitest)      vitest ;;
  eslint)      eslint ;;
  --all)       echo "== tsc ==";    tsc
               echo "== vitest =="; vitest
               echo "== eslint =="; eslint ;;
  *) echo "usage: $0 [tsc|vitest|eslint|--all|--self-test]" >&2; exit 2 ;;
esac
