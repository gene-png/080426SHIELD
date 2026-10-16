#!/usr/bin/env bash
# Prove `scripts/preflight.sh` reports PASS only when every planned step left a
# zero exit status, and that a step with NO status is could-not-look.
#
# Drives the REAL script and the REAL planner over a small fixture repository,
# with a stub `docker` (and `npx`) on PATH: the stub reads the plan the script
# wrote and prints one status line per planned step, in the mode a case asks
# for. No container starts, so this runs on a CI runner.
#
#     bash tests/gates/preflight_status.sh
#
# Exit 0 = every case held. 1 = a case did not. 2 = could not look.
set -euo pipefail

if [ "$#" -gt 0 ]; then
  echo "FAIL: this script takes no arguments; got: $*" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
for f in scripts/preflight.sh apps/api/scripts/preflight_plan.py; do
  [ -f "$ROOT/$f" ] || { echo "FAIL: could not look -- cannot find $ROOT/$f" >&2; exit 2; }
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
REPO="$TMP/repo"
mkdir -p "$REPO/scripts" "$REPO/apps/api/scripts" "$REPO/apps/api/tests/unit" "$REPO/.github/workflows"
cp "$ROOT/scripts/preflight.sh" "$REPO/scripts/"
cp "$ROOT/apps/api/scripts/preflight_plan.py" "$REPO/apps/api/scripts/"
printf '#!/usr/bin/env bash\necho 3.9.8\n' > "$REPO/scripts/prettier-hook.sh"
printf '#!/usr/bin/env bash\necho "stub web checks"\nexit "${STUB_WEB_RC:-0}"\n' > "$REPO/scripts/verify-in-worktree.sh"
printf '{"scripts": {"format:check": "prettier --check \\"**/*.{md,yml}\\""}}\n' > "$REPO/package.json"
cat > "$REPO/.github/workflows/ci.yml" << 'EOF'
on: pull_request
jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: first gate
        run: python -m scripts.check_a
      - name: unit
        working-directory: apps/api
        run: pytest -m unit tests/unit
      - name: advisory
        continue-on-error: true
        run: pip-audit
  e2e:
    runs-on: ubuntu-latest
    steps:
      - run: docker compose up -d
EOF
git -C "$REPO" init -q
git -C "$REPO" config core.autocrlf false
git -C "$REPO" config user.email gate@example.invalid
git -C "$REPO" config user.name gate
git -C "$REPO" add -A
git -C "$REPO" -c commit.gpgsign=false commit -qm base
git -C "$REPO" update-ref refs/remotes/origin/main HEAD
printf 'def test_x():\n    pass\n' > "$REPO/apps/api/tests/unit/test_x.py"
git -C "$REPO" add -A
git -C "$REPO" -c commit.gpgsign=false commit -qm "a test"
printf 'title\n' > "$TMP/title"
printf 'body\n' > "$TMP/body"

STUB="$TMP/stub"
mkdir -p "$STUB"
# `docker run ... -v <dir>:/work ...`: answer for each step that has a script,
# in STUB_MODE. `image inspect` succeeds; `rm -f` is a no-op.
cat > "$STUB/docker" << 'EOF'
#!/usr/bin/env bash
case "$1" in
  image) exit 0 ;;
  rm) exit 0 ;;
  run) ;;
  *) echo "stub docker: unexpected $*" >&2; exit 99 ;;
esac
work=""
prev=""
for a in "$@"; do
  if [ "$prev" = "-v" ]; then case "$a" in *:/work) work="${a%:/work}" ;; esac; fi
  prev="$a"
done
[ -n "$work" ] || { echo "stub docker: no /work mount" >&2; exit 98; }
n=0
while IFS=$'\t' read -r idx kind rest; do
  [ -f "$work/plan/step-$idx.sh" ] || continue
  n=$((n + 1))
  case "$STUB_MODE" in
    pass) echo "PREFLIGHT-STEP $idx 0" ;;
    missing) [ "$n" -eq 1 ] || echo "PREFLIGHT-STEP $idx 0" ;;
    fail) if [ "$n" -eq 1 ]; then echo "PREFLIGHT-STEP $idx 1"; else echo "PREFLIGHT-STEP $idx 0"; fi ;;
    advisory) if [ "$kind" = "advisory" ]; then echo "PREFLIGHT-STEP $idx 1"; else echo "PREFLIGHT-STEP $idx 0"; fi ;;
  esac
  echo "PREFLIGHT-TIME $idx 0"
done < "$work/plan/steps.tsv"
EOF
printf '#!/usr/bin/env bash\nexit "${STUB_PRETTIER_RC:-0}"\n' > "$STUB/npx"
chmod +x "$STUB/docker" "$STUB/npx"

fails=0
# $1 label, $2 STUB_MODE, $3 wanted exit, $4 a fixed string the output must hold,
# $5 a fixed string it must NOT hold ("" for none), $6... preflight arguments.
check() {
  local label="$1" mode="$2" want="$3" must="$4" mustnot="$5" out code
  shift 5
  set +e
  out="$(cd "$REPO" && STUB_MODE="$mode" PATH="$STUB:$PATH" bash scripts/preflight.sh "$@" 2>&1)"
  code=$?
  set -e
  if [ "$code" -ne "$want" ] || ! grep -qF -- "$must" <<< "$out" || { [ -n "$mustnot" ] && grep -qF -- "$mustnot" <<< "$out"; }; then
    echo "FAIL [$label]: exit $code (wanted $want), wanted '$must'${mustnot:+, not '$mustnot'}"
    sed 's/^/      /' <<< "$out"
    fails=$((fails + 1))
    return
  fi
  echo "ok   [$label] exit $code"
}

ARGS=(--title "$TMP/title" --body "$TMP/body")
check "every step 0"          pass     0 "preflight: PASS at"           "COULD-NOT-LOOK" "${ARGS[@]}"
check "narrow is the default" pass     0 "NARROW unit run"              "FULL unit run"  "${ARGS[@]}"
check "full when asked"       pass     0 "FULL unit run"                "NARROW"         "${ARGS[@]}" --unit full
check "a step with no status" missing  2 "preflight: COULD-NOT-LOOK at" "preflight: PASS" "${ARGS[@]}"
check "a step that failed"    fail     1 "preflight: FAIL at"           "preflight: PASS" "${ARGS[@]}"
check "advisory failure"      advisory 0 "preflight: PASS at"           ""               "${ARGS[@]}"
check "e2e stays on GitHub"   pass     0 "github"                       ""               "${ARGS[@]}"
check "no title"              pass     2 "--title"                      "preflight: PASS" --body "$TMP/body"
check "unknown flag"          pass     2 "unknown argument"             "preflight: PASS" "${ARGS[@]}" --bogus
# The web checks count: prettier always; eslint/tsc/vitest unless a NARROW run
# finds no web change (this fixture has none, so --unit full forces them).
STUB_PRETTIER_RC=1 check "prettier failed" pass 1 "preflight: FAIL at" "preflight: PASS" "${ARGS[@]}"
STUB_WEB_RC=1 check "web checks failed" pass 1 "preflight: FAIL at" "preflight: PASS" "${ARGS[@]}" --unit full
STUB_WEB_RC=2 check "web could not look" pass 2 "preflight: COULD-NOT-LOOK" "preflight: PASS" "${ARGS[@]}" --unit full
check "narrow skips web, and says so" pass 0 "eslint/tsc/vitest NOT RUN" "" "${ARGS[@]}"
# CI tests the MERGE with the base: a base that conflicts with HEAD is
# could-not-look; one that merges cleanly is merged in, and the summary says so.
# A base that moved on with a NEW GATE: the merged plan must run it, as CI's
# merge checkout would (review of d4ace8ef: a no-op merge proved nothing).
BASE0="$(git -C "$REPO" rev-parse refs/remotes/origin/main)"
git -C "$REPO" checkout -q -b ahead "$BASE0"
sed -i 's/^      - name: first gate$/      - name: a gate only main has\n        run: python -m scripts.check_b\n      - name: first gate/' "$REPO/.github/workflows/ci.yml"
grep -q "a gate only main has" "$REPO/.github/workflows/ci.yml" || { echo "FAIL: could not look -- the base's new gate was not written" >&2; exit 2; }
git -C "$REPO" -c commit.gpgsign=false commit -qam "main adds a gate"
git -C "$REPO" update-ref refs/remotes/origin/main HEAD
git -C "$REPO" checkout -q -
check "the base's new gate runs" pass 0 "a gate only main has" "" "${ARGS[@]}"
git -C "$REPO" update-ref refs/remotes/origin/main "$BASE0"
check "without it, it does not" pass 0 "preflight: PASS at" "a gate only main has" "${ARGS[@]}"
git -C "$REPO" checkout -q -b conflicting refs/remotes/origin/main
mkdir -p "$REPO/apps/api/tests/unit"
printf 'base side\n' > "$REPO/apps/api/tests/unit/test_x.py"
git -C "$REPO" add -A
git -C "$REPO" -c commit.gpgsign=false commit -qm "base adds test_x differently"
git -C "$REPO" update-ref refs/remotes/origin/main HEAD
git -C "$REPO" checkout -q -
check "base conflicts with HEAD" pass 2 "merging origin/main into HEAD failed" "preflight: PASS" "${ARGS[@]}"
git -C "$REPO" update-ref refs/remotes/origin/main "$BASE0"
printf 'x\n' >> "$REPO/apps/api/tests/unit/test_x.py"
check "a dirty tree"          pass     2 "uncommitted"                  "preflight: PASS" "${ARGS[@]}"
git -C "$REPO" checkout -q -- apps/api/tests/unit/test_x.py

if [ "$fails" -ne 0 ]; then
  echo "preflight-status: $fails case(s) failed"
  exit 1
fi
echo "preflight-status: all cases held"
