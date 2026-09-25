#!/bin/sh
# Prove `verify-in-worktree.sh` prints a bound ONLY when a tool demonstrably
# ran, and cleans its self-test probes up when it is killed.
#
# ## Why
#
# The eslint arm passed a removed `--format unix`, exited 2 on every tree, and
# printed a sentence claiming it had run the CI command (#450). The fix's first
# round refused on ONE cause -- a NO-WEB-SCRIPT marker -- and every other
# could-not-look walked past it: with docker off PATH, or a tool missing from
# an empty node_modules volume, tsc printed "0 error(s)" and vitest "53/53 test
# files ran" over exit 127. The arms now require POSITIVE evidence -- the
# `scripts.<name> =` line WEB_SCRIPT prints before exec'ing the tool, plus a
# status the tool gives as a verdict -- and this gate pins that by driving the
# REAL script with a stub `docker` on PATH. No container is started.
#
#     sh tests/gates/verify_in_worktree_status.sh

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

# A primary tree with the modules the script requires before it runs anything.
REPO="$TMP/primary"
mkdir -p "$REPO/scripts" "$REPO/packages/design-system/node_modules" "$REPO/apps/web/src/lib"
cp "$SCRIPT" "$REPO/scripts/verify-in-worktree.sh"
: > "$REPO/apps/web/src/lib/.keep"
git -C "$REPO" init -q
git -C "$REPO" config core.autocrlf false
git -C "$REPO" config user.email gate@example.invalid
git -C "$REPO" config user.name gate
git -C "$REPO" add -A
git -C "$REPO" -c commit.gpgsign=false commit -qm "gate fixture"

# The stub `docker`. Its behaviour is chosen per case by STUB_MODE. The last
# argument the script passes is the package.json script name (lint, test,
# typecheck), which the "ran" modes echo back the way WEB_SCRIPT does.
STUB="$TMP/stub"
mkdir -p "$STUB"
cat > "$STUB/docker" <<'EOF'
#!/bin/sh
for a in "$@"; do last="$a"; done
case "$STUB_MODE" in
  marker) echo "verify-in-worktree: NO-WEB-SCRIPT (apps/web/package.json defines no \"$last\" script)"; exit 2 ;;
  notfound) echo "sh: 1: ./node_modules/.bin/tool: not found" >&2; exit 127 ;;
  daemon) echo "docker: Cannot connect to the Docker daemon" >&2; exit 125 ;;
  noline-exit1) echo "docker: invalid reference format" >&2; exit 1 ;;
  ran-tool-missing) echo "verify-in-worktree: apps/web package.json scripts.$last = tool"; exit 127 ;;
  ran-clean) echo "verify-in-worktree: apps/web package.json scripts.$last = tool"; exit 0 ;;
  slow)
    echo "verify-in-worktree: apps/web package.json scripts.$last = tool"
    # The first call (the baseline) is quick and clean; the second -- made
    # while the probe exists -- is slow, so the gate can signal mid-probe.
    n=$(cat "$STUB_COUNT" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$STUB_COUNT"
    [ "$n" -ge 2 ] && sleep 3
    exit 0 ;;
  *) echo "stub: unknown STUB_MODE '$STUB_MODE'" >&2; exit 99 ;;
esac
EOF
chmod +x "$STUB/docker"

fail=0
run() {  # $1 = STUB_MODE, $2 = mode; sets out, rc
  out="$(cd "$REPO" && STUB_MODE="$1" STUB_COUNT="$TMP/count" PATH="$STUB:$PATH" bash scripts/verify-in-worktree.sh "$2" 2>&1)" && rc=0 || rc=$?
}
expect_refusal() {  # $1 = STUB_MODE, $2 = mode, $3 = bound text that must NOT appear, $4 = cause text
  run "$1" "$2"
  if [ "$rc" -ne 2 ]; then
    echo "FAIL: $2 with docker '$1' exited $rc, expected 2 (could not look)." >&2; fail=1
  fi
  case "$out" in *"COULD NOT LOOK"*) : ;; *) echo "FAIL: $2 with docker '$1' printed no COULD NOT LOOK." >&2; fail=1 ;; esac
  case "$out" in *"$4"*) : ;; *) echo "FAIL: $2 with docker '$1' did not name the cause '$4'." >&2; fail=1 ;; esac
  case "$out" in
    *"$3"*)
      echo "FAIL: $2 with docker '$1' printed a bound ('$3') although nothing is known to have run." >&2
      echo "$out" | sed 's/^/      | /' >&2
      fail=1 ;;
  esac
}

# 1. The round-2 case: the script could not be read.
expect_refusal marker tsc "error(s)" "could not be read"
expect_refusal marker eslint "ran apps/web" "could not be read"
# 2. The round-3 cases, which print NO marker: the bound needs positive evidence.
expect_refusal notfound tsc "error(s)" "is docker on PATH"
expect_refusal notfound vitest "test files ran" "is docker on PATH"
expect_refusal daemon eslint "ran apps/web" "exit 125"
expect_refusal ran-tool-missing tsc "error(s)" "node_modules volume empty"
# A VERDICT-SHAPED status with no evidence the tool ran: docker failed with 1.
# Only the positive `scripts.<name> =` line tells this from a real tsc exit 1.
expect_refusal noline-exit1 tsc "error(s)" "never started"

# 3. The POSITIVE CONTROL. A guard seen only refusing has been observed in one
#    state: a stub that did run must get its bound and its own status.
run ran-clean eslint
if [ "$rc" -ne 0 ]; then echo "FAIL: a clean lint run exited $rc, expected 0." >&2; fail=1; fi
case "$out" in *"ran apps/web"*"exit 0"*) : ;; *) echo "FAIL: a clean lint run printed no bound." >&2; echo "$out" | sed 's/^/      | /' >&2; fail=1 ;; esac

# 4. The self-test names the cause, not the mount.
run notfound --self-test
case "$out" in
  *"is not reading"*) echo "FAIL: the self-test blamed the mount for a missing tool." >&2; fail=1 ;;
esac
case "$out" in *"COULD NOT LOOK"*) : ;; *) echo "FAIL: the self-test printed no COULD NOT LOOK for a missing tool." >&2; fail=1 ;; esac

# 5. TERM while the probe exists: exit 143, no probe left behind.
rm -f "$TMP/count"
probe="$REPO/apps/web/src/lib/__verify_probe.ts"
(cd "$REPO" && STUB_MODE=slow STUB_COUNT="$TMP/count" PATH="$STUB:$PATH" exec bash scripts/verify-in-worktree.sh --self-test) > "$TMP/term.log" 2>&1 &
pid=$!
seen=0
i=0
while [ "$i" -lt 100 ]; do
  if [ -e "$probe" ]; then seen=1; kill -TERM "$pid"; break; fi
  sleep 0.1
  i=$((i + 1))
done
wait "$pid" && trc=0 || trc=$?
if [ "$seen" -ne 1 ]; then
  echo "FAIL: the probe never appeared, so the TERM case never ran." >&2; fail=1
elif [ "$trc" -ne 143 ]; then
  echo "FAIL: TERM mid-probe exited $trc, expected 143 -- a trap that only cleans up swallows the signal." >&2; fail=1
fi
if [ -e "$probe" ]; then echo "FAIL: TERM left the probe behind." >&2; fail=1; fi

if [ "$fail" -ne 0 ]; then
  echo "verify_in_worktree_status: FAIL" >&2
  exit 1
fi
echo "verify_in_worktree_status: PASS -- refusals, positive control, self-test cause and TERM cleanup all hold"
