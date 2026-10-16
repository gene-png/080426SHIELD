#!/usr/bin/env bash
# Prove `scripts/unit-in-worktree.sh` reports a verdict ONLY when pytest
# demonstrably ran, and that its `--self-test` can fail.
#
# Drives the REAL script with a stub `docker` on PATH, so no container starts
# and this runs on a CI runner. The stub's `probe` mode stands in for pytest by
# reading the test file out of the directory the script MOUNTS, so the
# self-test is exercised in both states: green when the mount is the worktree,
# red (exit 2, naming the red half) when it is pointed elsewhere.
#
#     bash tests/gates/unit_in_worktree_status.sh
#
# Exit 0 = every case held. 1 = a case did not. 2 = could not look.
set -euo pipefail

if [ "$#" -gt 0 ]; then
  echo "FAIL: this script takes no arguments; got: $*" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$ROOT/scripts/unit-in-worktree.sh"
[ -f "$SCRIPT" ] || { echo "FAIL: could not look -- cannot find $SCRIPT" >&2; exit 2; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

REPO="$TMP/repo"
mkdir -p "$REPO/scripts" "$REPO/apps/api/tests/unit"
cp "$SCRIPT" "$REPO/scripts/unit-in-worktree.sh"
: > "$REPO/apps/api/tests/unit/.keep"
git -C "$REPO" init -q
git -C "$REPO" config core.autocrlf false
git -C "$REPO" config user.email gate@example.invalid
git -C "$REPO" config user.name gate
git -C "$REPO" add -A
git -C "$REPO" -c commit.gpgsign=false commit -qm "gate fixture"
EMPTY="$TMP/empty"
mkdir -p "$EMPTY"

STUB="$TMP/stub"
mkdir -p "$STUB"
cat > "$STUB/docker" <<'EOF'
#!/usr/bin/env bash
if [ "$1" = "image" ]; then
  [ "${STUB_IMAGE:-present}" = "present" ] || { echo "Error: No such image: shield-v2-api:latest" >&2; exit 1; }
  echo "2026-10-15T00:00:00Z"; exit 0
fi
# `docker run ... sh -c <script> sh <depcheck> <pytest args...>`: everything
# after the depcheck is what pytest would receive.
all=("$@") ; mount="" ; args=() ; c=-1
for i in "${!all[@]}"; do
  if [ "${all[$i]}" = "-v" ]; then
    case "${all[$((i + 1))]}" in *:/src:ro) mount="${all[$((i + 1))]%:/src:ro}" ;; esac
  fi
  if [ "${all[$i]}" = "-c" ] && [ "$c" -lt 0 ]; then c="$i"; fi
done
# -c <script> sh <depcheck> <pytest args...>
[ "$c" -ge 0 ] && args=("${all[@]:$((c + 4))}")
ran() { echo "unit-in-worktree: RAN python -m pytest -p no:cacheprovider ${args[*]} (app=/tmp/repo/apps/api/app/__init__.py)"; }
case "$STUB_MODE" in
  pass) ran; echo "3 passed in 0.10s"; exit 0 ;;
  fail) ran; echo "1 failed, 2 passed in 0.10s"; exit 1 ;;
  crash) ran; echo "Traceback (most recent call last):"; exit 1 ;;
  noran) echo "3 passed in 0.10s"; exit 0 ;;
  daemon) echo "docker: Cannot connect to the Docker daemon" >&2; exit 125 ;;
  noselect) ran; echo "no tests ran in 0.01s"; exit 5 ;;
  wrongapp) echo "unit-in-worktree: WRONG-APP (app resolved to /app/app/__init__.py, not the mounted worktree)"; exit 2 ;;
  skew) echo "unit-in-worktree: DEP-SKEW ruff: required ==0.16.8, installed 0.16.7"; ran; echo "3 passed in 0.10s"; exit 0 ;;
  echoargs) ran; echo "1 passed in 0.01s"; exit 0 ;;
  # pytest exits 0 when every selected test SKIPPED: no test ran, so no verdict.
  allskip) ran; echo "5 skipped in 0.01s"; exit 0 ;;
  # The self-test's red half, slowly, so a TERM lands while its probe exists.
  slow) sleep 3; ran; echo "1 failed in 0.01s"; exit 1 ;;
  # A LARGE log: `printf | grep -q` takes SIGPIPE on output this size, and
  # under pipefail read a present RAN line as absent (2026-10-15).
  big) ran; seq 1 200000; echo "3 passed in 0.10s"; exit 0 ;;
  probe)
    target="${args[${#args[@]}-1]}"
    file="$mount/apps/api/$target"
    ran
    if [ ! -f "$file" ]; then echo "ERROR: file or directory not found: $target"; echo "no tests ran in 0.01s"; exit 4; fi
    if grep -q 'assert False' "$file"; then cat "$file"; echo "1 failed in 0.01s"; exit 1; fi
    echo "1 passed in 0.01s"; exit 0 ;;
  *) echo "stub: unknown STUB_MODE '$STUB_MODE'" >&2; exit 99 ;;
esac
EOF
chmod +x "$STUB/docker"

fails=0
# $1 label, $2 STUB_MODE, $3 wanted exit, $4 a fixed string the output must
# contain, $5 a fixed string it must NOT contain ("" for none), $6... args.
check() {
  local label="$1" mode="$2" want="$3" must="$4" mustnot="$5" out code
  shift 5
  set +e
  out="$(cd "$REPO" && STUB_MODE="$mode" PATH="$STUB:$PATH" bash scripts/unit-in-worktree.sh "$@" 2>&1)"
  code=$?
  set -e
  if [ "$code" -ne "$want" ]; then
    echo "FAIL [$label]: exit $code, wanted $want"; printf '%s\n' "$out" | sed 's/^/      /'; fails=$((fails + 1)); return
  fi
  if ! printf '%s\n' "$out" | grep -qF -- "$must"; then
    echo "FAIL [$label]: output lacks '$must'"; printf '%s\n' "$out" | sed 's/^/      /'; fails=$((fails + 1)); return
  fi
  if [ -n "$mustnot" ] && printf '%s\n' "$out" | grep -qF -- "$mustnot"; then
    echo "FAIL [$label]: output contains '$mustnot'"; printf '%s\n' "$out" | sed 's/^/      /'; fails=$((fails + 1)); return
  fi
  echo "ok   [$label] exit $code"
}

# Usage refusals, before any docker call.
check "unknown flag"            pass 2 "unknown flag"               "RAN python" --bogus
check "self-test plus an arg"   pass 2 "takes no other arguments"   "RAN python" --self-test tests/unit
SHIELD_UNIT_MOUNT_SOURCE="$EMPTY" check "override outside self-test" pass 2 "self-test hook" "RAN python"
# The inner-run marker, exported by hand, names no live probe: still refused.
_UNIT_IN_WORKTREE_SELF_TEST=1 SHIELD_UNIT_MOUNT_SOURCE="$EMPTY" check "override, marker set by hand" pass 2 "self-test hook" "RAN python"
_UNIT_IN_WORKTREE_SELF_TEST=0123456789ab SHIELD_UNIT_MOUNT_SOURCE="$EMPTY" check "override, tag with no probe" pass 2 "self-test hook" "RAN python"
# Could-not-look: no evidence pytest ran, or nothing it says is a verdict.
STUB_IMAGE=missing check "image missing" pass 2 "is not available"  "RAN python"
check "daemon down (125)"       daemon   2 "could not start"         "pytest exit"
check "exit 0, no RAN line"     noran    2 "pytest never started"    "pytest exit"
check "exit 1, no summary"      crash    2 "a crash, not a verdict"  "pytest exit"
check "nothing selected (5)"    noselect 2 "selected no tests"       "pytest exit"
check "app from the image"      wrongapp 2 "WRONG-APP"               "pytest exit"
check "dependency skew"         skew     2 "COULD NOT FULLY LOOK"    ""
check "exit 0, all skipped"      allskip  2 "no 'N passed' summary"   "pytest exit"
# Verdicts.
check "pass"                    pass     0 "pytest exit 0 -- 3 passed" ""
check "fail"                    fail     1 "pytest exit 1 -- 1 failed" ""
check "pass, large log"         big      0 "pytest exit 0 -- 3 passed" ""
# Selection: CI's default, and pytest options after `--`.
check "default is CI's"         echoargs 0 "pytest -p no:cacheprovider -m unit tests/unit (app=" ""
check "options after --"        echoargs 0 "-m unit tests/unit -k foo (app=" "" tests/unit -- -k foo
# The self-test in BOTH states.
check "self-test, right mount"  probe    0 "self-test: PASS"         "FAIL"   --self-test
# The must-not is the inner run REFUSING the hook: that also ends in "FAIL (red
# half)", and would hide a broken tag-and-probe check (review of 74506b66).
SHIELD_UNIT_MOUNT_SOURCE="$EMPTY" check "self-test, wrong mount" probe 2 "FAIL (red half)" "self-test hook" --self-test
# Run from ANOTHER tree, the script refuses rather than test the tree the shell
# is in (review of 313678ad: the self-test then "proved" the wrong tree).
OTHER="$TMP/other"
mkdir -p "$OTHER"
git -C "$OTHER" init -q
set +e
out="$(cd "$OTHER" && STUB_MODE=pass PATH="$STUB:$PATH" bash "$REPO/scripts/unit-in-worktree.sh" 2>&1)"
code=$?
set -e
if [ "$code" -ne 2 ] || ! printf '%s
' "$out" | grep -qF "but the shell" || printf '%s
' "$out" | grep -qF "RAN python"; then
  echo "FAIL [run from another tree]: exit $code, wanted 2 naming the two trees"; printf '%s
' "$out" | sed 's/^/      /'; fails=$((fails + 1))
else
  echo "ok   [run from another tree] exit $code"
fi

# TERM while the self-test's probe exists: exit 143, and no probe left behind.
# A trap that only cleaned up would swallow the signal and report the run.
(cd "$REPO" && STUB_MODE=slow PATH="$STUB:$PATH" exec bash scripts/unit-in-worktree.sh --self-test) > "$TMP/term.log" 2>&1 &
pid=$!
seen=0
i=0
while [ "$i" -lt 100 ]; do
  if compgen -G "$REPO/apps/api/tests/unit/test_zz_unit_in_worktree_selftest_*" > /dev/null; then
    seen=1; kill -TERM "$pid"; break
  fi
  sleep 0.1
  i=$((i + 1))
done
wait "$pid" && trc=0 || trc=$?
if [ "$seen" -ne 1 ]; then
  echo "FAIL [TERM mid-self-test]: the probe never appeared, so the case never ran"; fails=$((fails + 1))
elif [ "$trc" -ne 143 ]; then
  echo "FAIL [TERM mid-self-test]: exit $trc, wanted 143"; sed 's/^/      /' "$TMP/term.log"; fails=$((fails + 1))
else
  echo "ok   [TERM mid-self-test] exit $trc"
fi

left="$(find "$REPO/apps/api/tests/unit" -name 'test_zz_unit_in_worktree_selftest_*' | wc -l | tr -d '[:space:]')"
if [ "$left" -ne 0 ]; then
  echo "FAIL [probes removed]: $left probe file(s) left behind"; fails=$((fails + 1))
else
  echo "ok   [probes removed] none left"
fi

if [ "$fails" -ne 0 ]; then
  echo "unit-in-worktree-status: $fails case(s) failed"
  exit 1
fi
echo "unit-in-worktree-status: all cases held"
