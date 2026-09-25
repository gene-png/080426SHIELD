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
# Two files matching vitest's include, so the disk count agrees with the
# `(2)` the stub's vitest summaries print. A `.spec.ts` that vitest never
# includes, which the disk count must NOT count (#577).
: > "$REPO/apps/web/src/a.test.ts"
: > "$REPO/apps/web/src/b.test.tsx"
: > "$REPO/apps/web/src/c.spec.ts"
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
  # The vitest lines are CAPTURED, not typed from memory (#577): vitest 3.2.7,
  # 2026-09-25, from one passing, one failing and one uncollected file --
  #    FAIL  src/__cap/fail.test.ts > fails
  #    Test Files  2 failed | 1 passed (3)
  # and ESLint v9.39.5's debug line under DEBUG=eslint:eslint --
  #   2026-09-25T18:47:02.872Z eslint:eslint 399 file(s) found in 4865 ms
  ran-clean)
    echo "verify-in-worktree: apps/web package.json scripts.$last = tool"
    case "$last" in
      test) echo " Test Files  2 passed (2)" ;;
      lint) echo "2026-09-25T18:47:02.872Z eslint:eslint 2 file(s) found in 10 ms" >&2 ;;
    esac
    exit 0 ;;
  ran-verdict)
    # A REAL non-zero verdict, in each tool's own shape.
    echo "verify-in-worktree: apps/web package.json scripts.$last = tool"
    case "$last" in
      typecheck) echo "src/lib/a.ts(1,7): error TS2322: Type 'string' is not assignable to type 'number'."; exit 2 ;;
      test) echo " FAIL  src/a.test.ts > does a thing"; echo " Test Files  1 failed | 1 passed (2)"; exit 1 ;;
      lint) echo "2026-09-25T18:47:02.872Z eslint:eslint 2 file(s) found in 10 ms" >&2; echo "  1:5  error  Parsing error: Expression expected"; echo "✖ 1 problem (1 error, 0 warnings)"; exit 1 ;;
    esac ;;
  # #577: vitest exit 0 with no summary (an include matching nothing under
  # passWithNoTests), and a summary total that disagrees with the disk.
  vitest-nosummary) echo "verify-in-worktree: apps/web package.json scripts.$last = tool"; echo "No test files found, exiting with code 0"; exit 0 ;;
  vitest-mismatch) echo "verify-in-worktree: apps/web package.json scripts.$last = tool"; echo " Test Files  5 passed (5)"; exit 0 ;;
  # #566: eslint exit 0 with no file count, and with a count of zero.
  lint-nocount) echo "verify-in-worktree: apps/web package.json scripts.$last = tool"; exit 0 ;;
  # For --all's ranking: real verdicts from tsc and vitest, then an eslint
  # that cannot look (no count line).
  mixed-lint-blind)
    echo "verify-in-worktree: apps/web package.json scripts.$last = tool"
    case "$last" in
      typecheck) echo "src/lib/a.ts(1,7): error TS2322: Type 'string' is not assignable to type 'number'."; exit 2 ;;
      test) echo " FAIL  src/a.test.ts > does a thing"; echo " Test Files  1 failed | 1 passed (2)"; exit 1 ;;
      lint) exit 0 ;;
    esac ;;
  # The reverse order: vitest cannot look (no summary), then eslint gives a
  # real finding. A last-status-wins --all would report eslint's 1.
  mixed-vitest-blind)
    echo "verify-in-worktree: apps/web package.json scripts.$last = tool"
    case "$last" in
      typecheck) exit 0 ;;
      test) exit 0 ;;
      lint) echo "2026-09-25T18:47:02.872Z eslint:eslint 2 file(s) found in 10 ms" >&2; echo "  1:5  error  Parsing error: Expression expected"; echo "✖ 1 problem (1 error, 0 warnings)"; exit 1 ;;
    esac ;;
  lint-zero) echo "verify-in-worktree: apps/web package.json scripts.$last = tool"; echo "2026-09-25T18:47:02.872Z eslint:eslint 0 file(s) found in 3 ms" >&2; exit 0 ;;
  ran-crash)
    # The scripts line printed, then the tool CRASHED: exit 1, no verdict output.
    echo "verify-in-worktree: apps/web package.json scripts.$last = tool"
    echo "Error: Cannot find module 'typescript/lib/tsc.js'" >&2
    exit 1 ;;
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
expect_refusal marker eslint "eslint -- linted" "could not be read"
# 2. The round-3 cases, which print NO marker: the bound needs positive evidence.
expect_refusal notfound tsc "error(s)" "is docker on PATH"
expect_refusal notfound vitest "test files ran" "is docker on PATH"
expect_refusal daemon eslint "eslint -- linted" "exit 125"
expect_refusal ran-tool-missing tsc "error(s)" "node_modules volume empty"
# A VERDICT-SHAPED status with no evidence the tool ran: docker failed with 1.
# Only the positive `scripts.<name> =` line tells this from a real tsc exit 1.
expect_refusal noline-exit1 tsc "error(s)" "never started"

# 3. The POSITIVE CONTROL. A guard seen only refusing has been observed in one
#    state: a stub that did run must get its bound and its own status.
run ran-clean eslint
if [ "$rc" -ne 0 ]; then echo "FAIL: a clean lint run exited $rc, expected 0." >&2; fail=1; fi
case "$out" in *"eslint -- linted 2 file(s)"*"exit 0"*) : ;; *) echo "FAIL: a clean lint run printed no bound." >&2; echo "$out" | sed 's/^/      | /' >&2; fail=1 ;; esac

# 3b. POSITIVE CONTROLS FOR A REAL NON-ZERO VERDICT. Without these, dropping a
#     verdict code from an arm's list left this gate green while real type
#     errors printed COULD NOT LOOK.
run ran-verdict tsc
# 1, not tsc's own 2: in this script 2 means could-not-look, and `--all` ranks
# it above 1, so passing tsc's 2 through read a real type error as "could not
# look" (#618 review).
if [ "$rc" -ne 1 ]; then echo "FAIL: tsc with a real type error exited $rc, expected 1 (a verdict; tsc's own 2 is not passed through)." >&2; fail=1; fi
case "$out" in *"tsc -- 1 error(s)"*) : ;; *) echo "FAIL: tsc with a real type error printed no bound." >&2; echo "$out" | sed 's/^/      | /' >&2; fail=1 ;; esac
run ran-verdict vitest
if [ "$rc" -ne 1 ]; then echo "FAIL: vitest with a failing test exited $rc, expected its own 1." >&2; fail=1; fi
case "$out" in *"test files ran"*) : ;; *) echo "FAIL: vitest with a failing test printed no bound." >&2; echo "$out" | sed 's/^/      | /' >&2; fail=1 ;; esac
run ran-verdict eslint
if [ "$rc" -ne 1 ]; then echo "FAIL: eslint with a finding exited $rc, expected its own 1." >&2; fail=1; fi
case "$out" in *"eslint -- linted 2 file(s)"*"exit 1"*) : ;; *) echo "FAIL: eslint with a finding printed no bound." >&2; fail=1 ;; esac

# 3c. A CRASH IS NOT A VERDICT. The scripts line prints before the tool starts,
#     and exit 1 is also Node's code for an uncaught exception.
expect_refusal ran-crash tsc "error(s)" "without producing a verdict"
expect_refusal ran-crash vitest "test files ran" "without producing a verdict"
expect_refusal ran-crash eslint "eslint -- linted" "without producing a verdict"

# 3d. #577 -- vitest exit 0 must carry its summary, and its total must agree
#     with the disk count of files its include matches.
expect_refusal vitest-nosummary vitest "test files ran" "no 'Test Files ... (N)' summary"
expect_refusal vitest-mismatch vitest "test files ran" "the two disagree"
run ran-clean vitest
if [ "$rc" -ne 0 ]; then echo "FAIL: a clean vitest run exited $rc, expected 0." >&2; fail=1; fi
# 2/2, not 3/3: c.spec.ts is on disk and outside vitest's include.
case "$out" in *"vitest -- 2/2 test files ran"*) : ;; *) echo "FAIL: a clean vitest run did not report 2/2 (a .spec.ts counted?)." >&2; echo "$out" | sed 's/^/      | /' >&2; fail=1 ;; esac

# 3e. #566 -- the eslint bound is ESLint's own count; none, or zero, is
#     could-not-look. The debug lines themselves are not printed.
expect_refusal lint-nocount eslint "eslint -- linted" "file(s) found"
expect_refusal lint-zero eslint "eslint -- linted" "found 0 files"
case "$out" in *"eslint:eslint"*) echo "FAIL: eslint's debug lines were printed, not consumed." >&2; fail=1 ;; esac

# 3f. #566 -- `--all` runs every arm even after a red, says what each gave,
#     and exits with the worst status. The old --all stopped at tsc's red
#     without saying the later arms never ran. Three real verdicts are 1s.
run ran-verdict --all
if [ "$rc" -ne 1 ]; then echo "FAIL: --all over three real verdicts exited $rc, expected 1." >&2; fail=1; fi
case "$out" in
  *"== eslint =="*"--all -- tsc 1, vitest 1, eslint 1 (all three ran"*) : ;;
  *) echo "FAIL: --all did not run every arm and summarise them." >&2; echo "$out" | sed 's/^/      | /' >&2; fail=1 ;;
esac
# 2 OUTRANKS 1 even when the 1s come first: tsc and vitest give real verdicts,
# eslint cannot look. A last-status-wins or first-status-wins --all fails here.
run mixed-lint-blind --all
if [ "$rc" -ne 2 ]; then echo "FAIL: --all over tsc 1 / vitest 1 / eslint could-not-look exited $rc, expected 2." >&2; fail=1; fi
case "$out" in *"--all -- tsc 1, vitest 1, eslint 2 (all three ran"*) : ;; *) echo "FAIL: --all did not rank eslint's 2 over the earlier 1s." >&2; echo "$out" | sed 's/^/      | /' >&2; fail=1 ;; esac
run mixed-vitest-blind --all
if [ "$rc" -ne 2 ]; then echo "FAIL: --all over tsc 0 / vitest could-not-look / eslint 1 exited $rc, expected 2 -- a later 1 must not replace an earlier 2." >&2; fail=1; fi
case "$out" in *"--all -- tsc 0, vitest 2, eslint 1 (all three ran"*) : ;; *) echo "FAIL: --all did not keep vitest's 2 over eslint's later 1." >&2; echo "$out" | sed 's/^/      | /' >&2; fail=1 ;; esac
run ran-clean --all
if [ "$rc" -ne 0 ]; then echo "FAIL: --all over three clean arms exited $rc, expected 0." >&2; fail=1; fi
case "$out" in *"--all -- tsc 0, vitest 0, eslint 0"*) : ;; *) echo "FAIL: a clean --all printed no summary." >&2; fail=1 ;; esac
run lint-nocount --all
# tsc and vitest are clean-shaped here but vitest has no summary, so the
# worst is 2 either way; the point is that eslint's 2 is named, not skipped.
if [ "$rc" -ne 2 ]; then echo "FAIL: --all with eslint could-not-look exited $rc, expected 2." >&2; fail=1; fi
case "$out" in *"eslint 2 (all three ran"*) : ;; *) echo "FAIL: --all did not report eslint's could-not-look." >&2; fail=1 ;; esac

# 4. The self-test names the cause, not the mount.
for mode in notfound ran-crash; do
  run "$mode" --self-test
  case "$out" in
    *"is not reading"*) echo "FAIL: the self-test ($mode) blamed the mount." >&2; fail=1 ;;
  esac
  case "$out" in *"COULD NOT LOOK"*) : ;; *) echo "FAIL: the self-test ($mode) printed no COULD NOT LOOK." >&2; fail=1 ;; esac
done

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
