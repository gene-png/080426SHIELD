#!/usr/bin/env bash
#
# Run the API unit suite against THIS worktree, in a throwaway container.
#
# ## Why this exists
#
# The API twin of `scripts/verify-in-worktree.sh`. `docker compose exec -T api
# pytest ...` attaches to the shared `shield-v2` stack, which bind-mounts
# `./apps/api` from whichever tree last ran `up`, so an agent in worktree B
# gets a verdict about worktree A. This removes the shared stack from the loop:
# `docker run --rm --network none` on the existing `shield-v2-api` image, with
# THIS worktree's full checkout mounted read-only at /src, COPIED to /tmp/repo
# inside the container, and pytest run from /tmp/repo/apps/api -- CI's layout
# (`working-directory: apps/api`, the root `pyproject.toml` above it,
# `apps/web` and `.github` present for the tests that read them).
#
# The copy is deliberate. Some unit tests write scratch files into the tree
# (`test_gate_crash_exit_code.py` writes `scripts/_crashmutant_*.py`), so a
# read-only mount fails them with EROFS, and a read-write one leaves those
# files in the worktree whenever a run is killed -- where `git add -A` finds
# them. The copy costs ~30 s on this host (measured 2026-10-15, 29 MB tree).
#
# `--network none` is the isolation, not a nicety: the suite's fixtures use
# their own SQLite files, and `conftest.py` defaults DATABASE_URL to a
# localhost Postgres -- which, with no network, cannot be the shared one.
# The mount is read-only, so nothing the run does is written into the
# worktree; bytecode goes to PYTHONPYCACHEPREFIX inside the container. Bytecode is kept rather than disabled because without it every
# test's alembic upgrade recompiles every migration: 60 tests took 7m21s.
#
# ## What a result names
#
# Every run prints the worktree, its HEAD and whether it is clean BEFORE
# running, and the container prints where `app` resolved from. The image
# carries its own baked copy of apps/api at /app; a run importing THAT would
# test the image, not the branch, so `app` resolving anywhere but
# /tmp/repo/apps/api is exit 2.
#
# ## Residual: the image's dependencies are the image's
#
# Installed packages come from when `shield-v2-api` was BUILT, not from this
# worktree's `apps/api/pyproject.toml`. The container checks every requirement
# in `[project] dependencies` and the `dev` extra against what is installed;
# any requirement missing or outside its specifier is exit 2 (could not fully
# look), whatever pytest said. Rebuilding the image is a human decision -- it
# is the shared stack's image too.
#
# ## Exit codes (D-090)
#
#     0  pytest ran and passed            1  pytest ran and something failed
#     2  could not look: bad usage, no docker/image, no evidence pytest ran,
#        nothing selected, collection/usage error, wrong `app`, dependency skew
#
# ## Usage
#
#     scripts/unit-in-worktree.sh                      # pytest -m unit tests/unit (CI)
#     scripts/unit-in-worktree.sh tests/unit/test_x.py # pytest -m unit <paths>
#     scripts/unit-in-worktree.sh tests/unit -- -k foo # pytest options after --
#     scripts/unit-in-worktree.sh --self-test          # prove the mount is THIS tree
#
# Paths are relative to apps/api, as in CI. Run one container at a time on a
# small host; SHIELD_UNIT_MEMORY overrides the default `--memory=3g`.
set -euo pipefail

# ARGUMENTS ARE JUDGED BEFORE ANY WORK. A flag this script does not implement
# must not reach pytest as one: `--self-tset` would run as a pytest option and
# its usage error would be the only trace of a self-test that never ran.
if [ "$#" -ge 1 ] && [ "$1" = "--self-test" ]; then
  if [ "$#" -gt 1 ]; then
    echo "FAIL: --self-test takes no other arguments; got: $*" >&2
    exit 2
  fi
else
  seen_dashdash=0
  for a in "$@"; do
    if [ -z "$a" ]; then
      echo "FAIL: empty argument. An explicit \"\" is not a path." >&2
      exit 2
    fi
    if [ "$seen_dashdash" -eq 0 ]; then
      case "$a" in
        --) seen_dashdash=1 ;;
        -*)
          echo "FAIL: unknown flag '$a'. This script's only flag is --self-test;" >&2
          echo "      pass pytest options after '--'." >&2
          exit 2 ;;
      esac
    fi
  done
fi

command -v docker > /dev/null 2>&1 || {
  echo "unit-in-worktree: COULD NOT LOOK -- docker is not on PATH." >&2
  echo "  Git Bash: export PATH=\"\$PATH:/c/Program Files/Docker/Docker/resources/bin\"" >&2
  exit 2
}

WORKTREE="$(git rev-parse --show-toplevel)"
IMAGE="${SHIELD_UNIT_IMAGE:-shield-v2-api:latest}"
MEMORY="${SHIELD_UNIT_MEMORY:-3g}"

# A TEST HOOK, AND ONLY THAT. The self-test sets SHIELD_UNIT_MOUNT_SOURCE to a
# different directory to prove it notices a wrong mount; outside a self-test
# run it is refused, because a mount that is not this worktree is the exact
# defect this script exists to prevent.
MOUNT_SOURCE="$WORKTREE"
if [ -n "${SHIELD_UNIT_MOUNT_SOURCE:-}" ]; then
  if [ "${1:-}" != "--self-test" ] && [ "${_UNIT_IN_WORKTREE_SELF_TEST:-}" != "1" ]; then
    echo "FAIL: SHIELD_UNIT_MOUNT_SOURCE is a self-test hook; refusing to mount" >&2
    echo "      '$SHIELD_UNIT_MOUNT_SOURCE' in place of $WORKTREE." >&2
    exit 2
  fi
  MOUNT_SOURCE="$SHIELD_UNIT_MOUNT_SOURCE"
fi

# docker.exe is a native Windows executable, so MSYS would rewrite `/src`.
export MSYS_NO_PATHCONV=1
win() { printf '%s' "$1" | sed -e 's#^/\([a-z]\)/#\U\1:/#'; }

PREFIX="unit-in-worktree:"

# Runs inside the container as `sh -c "$CONTAINER_SCRIPT" sh <depcheck> <pytest args...>`,
# so values arrive as positional arguments and are never spliced into source.
CONTAINER_SCRIPT='
depcheck="$1"; shift
cp -R /src /tmp/repo || { echo "unit-in-worktree: NO-COPY (copying the mounted worktree into the container failed)"; exit 2; }
cd /tmp/repo/apps/api || { echo "unit-in-worktree: NO-API-DIR (no apps/api in the mount)"; exit 2; }
app_file="$(python -c "import app; print(app.__file__)")" || { echo "unit-in-worktree: WRONG-APP (app is not importable from the copied apps/api)"; exit 2; }
case "$app_file" in
  /tmp/repo/apps/api/app/*) ;;
  *) echo "unit-in-worktree: WRONG-APP (app resolved to $app_file, not the mounted worktree)"; exit 2 ;;
esac
python -c "$depcheck" || { echo "unit-in-worktree: DEP-CHECK-FAILED (the dependency check itself crashed)"; exit 2; }
echo "unit-in-worktree: RAN python -m pytest -p no:cacheprovider $* (app=$app_file)"
exec python -m pytest -p no:cacheprovider "$@"
'

# Every requirement the worktree declares, against what the IMAGE installed.
DEPCHECK='
import tomllib
from importlib import metadata
from packaging.requirements import Requirement
with open("pyproject.toml", "rb") as f:
    project = tomllib.load(f)["project"]
reqs = list(project.get("dependencies", [])) + list(project.get("optional-dependencies", {}).get("dev", []))
skew = 0
for line in reqs:
    req = Requirement(line)
    if req.marker is not None and not req.marker.evaluate():
        continue
    wanted = str(req.specifier) or "any version"
    try:
        have = metadata.version(req.name)
    except metadata.PackageNotFoundError:
        print(f"unit-in-worktree: DEP-SKEW {req.name}: required {wanted}, NOT INSTALLED")
        skew += 1
        continue
    if req.specifier and not req.specifier.contains(have, prereleases=True):
        print(f"unit-in-worktree: DEP-SKEW {req.name}: required {req.specifier}, installed {have}")
        skew += 1
print(f"unit-in-worktree: deps -- checked {len(reqs)} requirement(s) from apps/api/pyproject.toml, {skew} skewed")
'

preamble() {
  local head dirty created
  head="$(git -C "$WORKTREE" rev-parse HEAD)"
  dirty="$(git -C "$WORKTREE" status --porcelain | wc -l | tr -d '[:space:]')"
  echo "$PREFIX worktree  $WORKTREE"
  echo "$PREFIX HEAD      $head"
  if [ "$dirty" -eq 0 ]; then
    echo "$PREFIX tree      clean"
  else
    echo "$PREFIX tree      DIRTY ($dirty path(s) in git status --porcelain) -- the run tests the working files, not HEAD"
  fi
  if [ "$MOUNT_SOURCE" != "$WORKTREE" ]; then
    echo "$PREFIX MOUNT OVERRIDE -- mounting $MOUNT_SOURCE, NOT the worktree (self-test only)"
  fi
  if ! created="$(docker image inspect --format '{{.Created}}' "$IMAGE" 2>&1)"; then
    echo "$PREFIX COULD NOT LOOK -- image '$IMAGE' is not available: $created" >&2
    echo "  This script never builds or pulls. Build it deliberately (it is the" >&2
    echo "  shared stack's api image), or set SHIELD_UNIT_IMAGE." >&2
    return 2
  fi
  echo "$PREFIX image     $IMAGE, built $created"
}

# $@ = pytest arguments. Streams output, and judges the status only on
# POSITIVE evidence that pytest ran: the RAN line the container prints just
# before exec'ing it, plus a summary line matching the status.
run_unit() {
  preamble || return 2
  local log status tee_status
  log="$(mktemp)"
  set +e
  docker run --rm --network none --memory="$MEMORY" \
    -e SHIELD_LLM_MODE=fixture -e PYTHONDONTWRITEBYTECODE= -e PYTHONPYCACHEPREFIX=/tmp/pycache -e HOME=/tmp \
    -v "$(win "$MOUNT_SOURCE"):/src:ro" \
    -w /tmp "$IMAGE" \
    sh -c "$CONTAINER_SCRIPT" sh "$DEPCHECK" "$@" 2>&1 | tee "$log"
  # One read: assigning from PIPESTATUS resets it.
  local ps=("${PIPESTATUS[@]}")
  status="${ps[0]}"
  tee_status="${ps[1]}"
  set -e
  local out
  out="$(cat "$log")"
  rm -f "$log"
  if [ "$tee_status" -ne 0 ]; then
    echo "$PREFIX COULD NOT LOOK -- capturing the output failed (tee exit $tee_status)." >&2
    return 2
  fi
  judge "$out" "$status"
}

# $1 = captured output, $2 = docker's exit status. Returns 0, 1 or 2.
#
# Every match reads a HERE-STRING, never `printf ... | grep -q`: `grep -q`
# exits at its first match, the writer takes SIGPIPE, and under pipefail the
# pipeline is FALSE. On a large log that turned a run with a RAN line into
# "pytest never started" (measured 2026-10-15, three test files).
judge() {
  local out="$1" status="$2" summary skew
  if grep -qE "^$PREFIX (NO-COPY|NO-API-DIR|WRONG-APP|DEP-CHECK-FAILED)" <<< "$out"; then
    echo "$PREFIX COULD NOT LOOK -- $(grep -m1 -oE "(NO-COPY|NO-API-DIR|WRONG-APP|DEP-CHECK-FAILED).*" <<< "$out")" >&2
    return 2
  fi
  if ! grep -qF "$PREFIX RAN python -m pytest" <<< "$out"; then
    case "$status" in
      125) echo "$PREFIX COULD NOT LOOK -- docker could not start the container (exit 125: daemon down, or a bad run option)." >&2 ;;
      126 | 127) echo "$PREFIX COULD NOT LOOK -- a command was not found in the container (exit $status)." >&2 ;;
      *) echo "$PREFIX COULD NOT LOOK -- pytest never started (exit $status, no RAN line)." >&2 ;;
    esac
    return 2
  fi
  summary="$(grep -E '^=*[^=]*[0-9]+ (passed|failed|error|errors|deselected|skipped)' <<< "$out" | tail -1 || true)"
  skew="$(grep -c "^$PREFIX DEP-SKEW" <<< "$out" || true)"
  case "$status" in
    0) grep -qE '[0-9]+ passed' <<< "$summary" || { echo "$PREFIX COULD NOT LOOK -- exit 0 with no 'N passed' summary." >&2; return 2; } ;;
    1) grep -qE '[0-9]+ (failed|error)' <<< "$summary" || { echo "$PREFIX COULD NOT LOOK -- exit 1 with no 'N failed' summary: a crash, not a verdict." >&2; return 2; } ;;
    5) echo "$PREFIX COULD NOT LOOK -- pytest selected no tests (exit 5)." >&2; return 2 ;;
    *) echo "$PREFIX COULD NOT LOOK -- pytest exit $status (interrupted, collection error, usage error or internal error) is not a verdict." >&2; return 2 ;;
  esac
  echo "$PREFIX pytest exit $status -- ${summary:-<no summary>}"
  if [ "$skew" -gt 0 ]; then
    echo "$PREFIX COULD NOT FULLY LOOK -- $skew requirement(s) above differ between this worktree's" >&2
    echo "  apps/api/pyproject.toml and the image. pytest said $status; the result is reported as 2." >&2
    return 2
  fi
  return "$status"
}

# ---------------------------------------------------------------------------
# --self-test: PROVE THE CONTAINER READ THIS WORKTREE, in both directions.
#
# Red half: an untracked probe test, named with a random token, that fails and
# prints the token. Exit 1 AND the token in the output means pytest ran a file
# that exists only in this worktree. Green half: a second probe that passes,
# required to exit 0 with `1 passed`. Either half misbehaving is exit 2, naming
# which. A wrong mount (SHIELD_UNIT_MOUNT_SOURCE pointed elsewhere) cannot see
# the probes, so the red half fails -- that is the self-test's own red state.
# ---------------------------------------------------------------------------
PROBE_DIR_REL="apps/api/tests/unit"
PROBE_GLOB="test_zz_unit_in_worktree_selftest_"

remove_probes() {
  rm -f "$WORKTREE/$PROBE_DIR_REL/$PROBE_GLOB"*.py
}

self_test() {
  # TWO tokens: one names the files, the other is only INSIDE them. The file
  # name is echoed by this script's own RAN line, so a token shared with it
  # would be "found" in the output without pytest having read the file.
  local tag token red green out st
  tag="$(od -An -N6 -tx1 /dev/urandom | tr -d ' \n')"
  token="$(od -An -N6 -tx1 /dev/urandom | tr -d ' \n')"
  { [ -n "$tag" ] && [ -n "$token" ] && [ "$tag" != "$token" ]; } || { echo "self-test: FAIL -- could not make two random tokens" >&2; return 2; }
  red="$PROBE_GLOB${tag}_red.py"
  green="$PROBE_GLOB${tag}_green.py"
  # Stale probes are removed at ENTRY too: KILL cannot be trapped.
  remove_probes
  trap remove_probes EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  export _UNIT_IN_WORKTREE_SELF_TEST=1

  printf 'import pytest\n\n\n@pytest.mark.unit\ndef test_probe():\n    print("probe-token-%s")\n    assert False, "unit-in-worktree self-test probe-token-%s"\n' \
    "$token" "$token" > "$WORKTREE/$PROBE_DIR_REL/$red"
  # Prove the write landed before reading any result.
  grep -q "probe-token-$token" "$WORKTREE/$PROBE_DIR_REL/$red" || { echo "self-test: FAIL -- red probe never written" >&2; return 2; }
  echo "self-test: red half -- a failing probe that exists only in $WORKTREE"
  out="$("${BASH:-bash}" "$0" "tests/unit/$red" 2>&1)" && st=0 || st=$?
  printf '%s\n' "$out"
  rm -f "$WORKTREE/$PROBE_DIR_REL/$red"
  if [ "$st" -ne 1 ] || ! grep -qF "probe-token-$token" <<< "$out"; then
    echo "self-test: FAIL (red half) -- wanted exit 1 with probe-token-$token in the output; got exit $st$(grep -qF "probe-token-$token" <<< "$out" && echo ', token present' || echo ', token ABSENT')." >&2
    echo "           The container did not run this worktree's file. Do not trust any result from it." >&2
    return 2
  fi
  echo "self-test: red half PASS -- exit 1, token present"

  printf 'import pytest\n\n\n@pytest.mark.unit\ndef test_probe():\n    assert "%s"\n' "$token" > "$WORKTREE/$PROBE_DIR_REL/$green"
  grep -q "$token" "$WORKTREE/$PROBE_DIR_REL/$green" || { echo "self-test: FAIL -- green probe never written" >&2; return 2; }
  echo "self-test: green half -- a passing probe"
  out="$("${BASH:-bash}" "$0" "tests/unit/$green" 2>&1)" && st=0 || st=$?
  printf '%s\n' "$out"
  rm -f "$WORKTREE/$PROBE_DIR_REL/$green"
  if [ "$st" -ne 0 ] || ! grep -qE '(^|[^0-9])1 passed' <<< "$out"; then
    echo "self-test: FAIL (green half) -- wanted exit 0 with '1 passed'; got exit $st." >&2
    return 2
  fi
  echo "self-test: green half PASS -- exit 0, 1 passed"
  echo "self-test: PASS -- the container ran against $WORKTREE (probes removed)"
}

if [ "${1:-}" = "--self-test" ]; then
  self_test
  exit $?
fi

# Default: CI's exact selection. Arguments replace `tests/unit`; `-m unit`
# always stays, as CI's does. A `--` separator is dropped here and its options
# forwarded.
args=()
for a in "$@"; do
  [ "$a" = "--" ] && continue
  args+=("$a")
done
if [ "${#args[@]}" -eq 0 ]; then
  args=(tests/unit)
fi
st=0
run_unit -m unit "${args[@]}" || st=$?
exit "$st"
