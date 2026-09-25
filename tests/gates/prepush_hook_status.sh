#!/usr/bin/env bash
# Prove the pre-push API unit-test hook (#143) passes a failing suite through
# as a failed push, and that every NOT RUN branch exits 2 and names its cause.
#
# #143's hook was `pytest -m unit 2>/dev/null || echo "skipped ..."`: a failing
# suite and a stopped container printed the same line, and both pushed. The
# repair lives in ONE line of `.pre-commit-config.yaml`, and a line nothing
# executes is a line the next edit can quietly revert.
#
# So this EXTRACTS the hook's `entry:` from `.pre-commit-config.yaml` (parsed
# as YAML, not restated), runs its `bash -c` body against a stub `docker`, and
# asserts the exit status and the message in each state:
#
#   suite passes -> 0      suite fails -> 1        api container down -> 2
#   compose fails -> 2     docker info fails -> 2  docker not on PATH -> 2
#
# Every NOT RUN message must also carry both bypasses (Git Bash and
# PowerShell). It also asserts the hook's registration: `stages: [pre-push]`,
# `always_run: true`, `pass_filenames: false`.
#
#   tests/gates/prepush_hook_status.sh              # the gate
#   tests/gates/prepush_hook_status.sh --self-test  # prove it can fail
#
# `--self-test` applies each mutation to the extracted body -- #143's
# `|| echo skipped`, a NOT RUN branch exiting 0, `--collect-only` on the suite,
# and `docker info`'s redirects flipped -- proves each LANDED (exit 2 if not),
# and requires exactly its named checks to go RED.
#
# Exit codes: 0 clean; 1 a check failed; 2 could not look (the config is
# missing, unreadable, unparseable or has no such hook, or a mutation did not
# land). The states never run against a body that was not extracted.

set -euo pipefail

# Refuse a poisoned environment rather than answer from one: this hands paths
# to Python, and MSYS_NO_PATHCONV=1 stops Git Bash translating them.
if [ "${MSYS_NO_PATHCONV:-}" = "1" ]; then
  echo "$0: MSYS_NO_PATHCONV=1 is set. This script hands a path to Python," >&2
  echo "  which needs the MSYS rewrite that variable suppresses. Unset it" >&2
  echo "  and re-run; do not read this exit as a verdict about the code." >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="$ROOT/.pre-commit-config.yaml"
SELF_TEST=0

# Arity on `$#`, not `${1:-}`: an explicit "" must not run as no argument.
if [ "$#" -gt 1 ]; then
  echo "FAIL: too many arguments; got: $*" >&2
  exit 2
fi
if [ "$#" -eq 1 ]; then
  case "$1" in
    --self-test) SELF_TEST=1 ;;
    *)
      echo "FAIL: unknown argument '$1'. This script accepts only --self-test." >&2
      exit 2 ;;
  esac
fi

[ -f "$CONFIG" ] || { echo "FAIL: cannot find $CONFIG" >&2; exit 2; }

# Probed by RUNNING each candidate: Windows ships a `python3.exe` alias that
# resolves and exits non-zero. No interpreter is a could-not-look.
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for candidate in python3 python; do
    if "$candidate" -c "import yaml" >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
  done
fi
[ -n "$PYTHON" ] || { echo "FAIL: no python3/python with PyYAML on PATH; cannot parse the hook" >&2; exit 2; }

BASH_BIN="$(command -v bash)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- extract, and check the registration --------------------------------------
# Exit 2 from the extractor is could-not-look (the hook moved or changed shape);
# exit 1 is a registration violation. Neither is read as a pass.
rc=0
"$PYTHON" - "$CONFIG" "$WORK/body.sh" <<'EXTRACT' || rc=$?
import os, shlex, sys, yaml
src, dest = sys.argv[1], sys.argv[2]


def _crash(kind, value, tb):
    # An UNEXPECTED exception would otherwise exit 1, which the caller reads as
    # a registration violation and then runs the states. A crash is a 2.
    sys.stderr.write("EXTRACT FAILED: crashed: %s: %s\n" % (kind.__name__, value))
    sys.stderr.flush()
    os._exit(2)


sys.excepthook = _crash


def could_not_look(cause):
    # 2, never 1: an unreadable config is not a registration violation, and
    # nothing below may run against a body that was never extracted.
    sys.stderr.write("EXTRACT FAILED: %s\n" % cause)
    sys.exit(2)


try:
    doc = yaml.safe_load(open(src, encoding="utf-8"))
except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
    could_not_look("cannot read or parse %s: %s" % (src, exc))
if not isinstance(doc, dict) or not isinstance(doc.get("repos"), list):
    could_not_look("%s has no `repos:` list (empty or not a pre-commit config)" % src)
hooks = [
    h
    for r in doc["repos"] if isinstance(r, dict)
    for h in (r.get("hooks") or []) if isinstance(h, dict) and h.get("id") == "api-unit-tests"
]
if len(hooks) != 1:
    could_not_look("expected 1 api-unit-tests hook, found %d" % len(hooks))
hook = hooks[0]
try:
    words = shlex.split(str(hook.get("entry", "")))
except ValueError as exc:
    could_not_look("the entry does not split as shell words: %s" % exc)
if len(words) != 3 or words[:2] != ["bash", "-c"] or not words[2].strip():
    could_not_look("entry is not `bash -c '<non-empty body>'`: %r" % words[:2])
bad = []
if hook.get("stages") != ["pre-push"]:
    bad.append("stages is %r, not ['pre-push']" % hook.get("stages"))
if hook.get("always_run") is not True:
    bad.append("always_run is %r, not true" % hook.get("always_run"))
if hook.get("pass_filenames") is not False:
    bad.append("pass_filenames is %r, not false" % hook.get("pass_filenames"))
open(dest, "w", encoding="utf-8", newline="\n").write(words[2])
if bad:
    sys.stderr.write("REGISTRATION: " + "; ".join(bad) + "\n")
    sys.exit(1)
EXTRACT
# Only 0 (registered correctly) and 1 (a registration violation, reached only
# after the body was written) mean a body was extracted. Every read or parse
# failure, and any crash, is 2 above, and stops here before the states run.
case "$rc" in
  0|1) ;;
  *) echo "could not look: the extractor exited $rc" >&2; exit 2 ;;
esac
[ -s "$WORK/body.sh" ] || { echo "could not look: the extracted body is empty" >&2; exit 2; }
FAILURES=0
if [ "$rc" -ne 0 ]; then
  echo "FAIL [registration]: see above"
  FAILURES=$((FAILURES + 1))
fi

# --- the stub docker ------------------------------------------------------------
mkdir -p "$WORK/bin" "$WORK/empty"
# The stub answers ONLY the exact argv the hook is meant to send, and exits 99
# on anything else. An edit to `pytest -m unit --collect-only`, `-T web` or
# `-m integration` is a different call, so it cannot pass as the suite.
cat > "$WORK/bin/docker" <<'STUB'
#!/usr/bin/env bash
case "$*" in
  "info")
    [ "${STUB_INFO:-0}" = "0" ] || { echo "permission denied while trying to connect" >&2; exit 1; }
    exit 0 ;;
  "compose ps --status running --services")
    [ "${STUB_COMPOSE:-0}" = "0" ] || { echo "unknown flag: --status" >&2; exit 1; }
    printf '%s\n' ${STUB_SERVICES:-api web}
    exit 0 ;;
  "compose exec -T api pytest -m unit")
    exit "${STUB_PYTEST:-0}" ;;
esac
echo "stub docker: unexpected call: $*" >&2
exit 99
STUB
chmod +x "$WORK/bin/docker"

# run_case BODY LABEL EXPECTED_EXIT NEEDLE [VAR=VAL...]
# Runs the body under `bash -c`, as pre-commit does, with the stub first on PATH
# (or with an EMPTY PATH for the no-docker case, where only builtins run).
LABELS=""
run_case() {
  local body="$1" label="$2" want="$3" needle="$4"; shift 4
  local path="$WORK/bin:$PATH"
  if [ "$label" = "docker not on PATH" ]; then path="$WORK/empty"; fi
  local out got=0
  out="$(env PATH="$path" "$@" "$BASH_BIN" -c "$(cat "$body")" 2>&1)" || got=$?
  local ok=1
  [ "$got" = "$want" ] || ok=0
  case "$out" in *"$needle"*) ;; *) ok=0 ;; esac
  if [ "$want" = "2" ]; then
    case "$out" in *"SKIP=api-unit-tests git push"*) ;; *) ok=0 ;; esac
    case "$out" in *'$env:SKIP="api-unit-tests"; git push; Remove-Item Env:SKIP'*) ;; *) ok=0 ;; esac
  fi
  if [ "$ok" = "1" ]; then
    echo "ok   [$label] exit $got"
  else
    echo "FAIL [$label] exit $got, wanted $want with '$needle'; output: $out"
    LABELS="$LABELS|$label"
  fi
}

check_body() {  # $1 = body file; sets LABELS to the failed checks
  LABELS=""
  local B="$1" tree="the tree the shared api container mounts"
  run_case "$B" "suite passes" 0 "$tree" STUB_PYTEST=0
  run_case "$B" "suite fails" 1 "$tree" STUB_PYTEST=1
  run_case "$B" "container down" 2 "NOT RUN - the api container is not running" STUB_SERVICES=web
  run_case "$B" "compose fails" 2 "NOT RUN - docker compose failed - unknown flag: --status" STUB_COMPOSE=1
  run_case "$B" "docker info fails" 2 "NOT RUN - docker info failed, so the daemon is unreachable or permission was denied - permission denied while trying to connect" STUB_INFO=1
  run_case "$B" "docker not on PATH" 2 "NOT RUN - docker is not on PATH"
}

if [ "$SELF_TEST" = "1" ]; then
  self_fail=0
  while IFS='=' read -r mutation expected; do
    [ -n "$mutation" ] || continue
    rc=0
    "$PYTHON" - "$WORK/body.sh" "$WORK/mutant.sh" "$mutation" <<'MUTATE' || rc=$?
import sys
src, dest, which = sys.argv[1], sys.argv[2], sys.argv[3]
body = open(src, encoding="utf-8").read()
old, new = {
    # #143's shape: a failing suite is rescued by an echo.
    "echo_rescue": ("exec docker compose exec -T api pytest -m unit",
                    "docker compose exec -T api pytest -m unit || echo skipped"),
    # A NOT RUN branch that exits 0 reads as Passed on pre-commit's line.
    "down_exits_0": ('the api container is not running. $hint"; exit 2',
                     'the api container is not running. $hint"; exit 0'),
    # Collects and runs nothing, then exits 0: every push passes.
    "collect_only": ("exec docker compose exec -T api pytest -m unit",
                     "exec docker compose exec -T api pytest -m unit --collect-only"),
    # Flipped redirects: stderr goes to /dev/null, so the cause is lost.
    "info_redirects": ("docker info 2>&1 >/dev/null", "docker info >/dev/null 2>&1"),
}[which]
if body.count(old) != 1:
    sys.stderr.write("MUTATION DID NOT LAND [%s]: anchor found %d times\n" % (which, body.count(old)))
    sys.exit(2)
open(dest, "w", encoding="utf-8", newline="\n").write(body.replace(old, new))
MUTATE
    # A mutation that did not land proves nothing about the gate: could not look.
    if [ "$rc" -ne 0 ]; then echo "self-test could not look: [$mutation] did not land" >&2; exit 2; fi
    check_body "$WORK/mutant.sh" >/dev/null
    if [ "$LABELS" = "$expected" ]; then
      echo "self-test ok [$mutation] -> fails exactly [${expected#|}]"
    else
      echo "SELF-TEST FAILED [$mutation]: failed [${LABELS#|}], expected [${expected#|}]"
      self_fail=1
    fi
  done <<'EXPECTATIONS'
echo_rescue=|suite fails
down_exits_0=|container down
collect_only=|suite passes|suite fails
info_redirects=|docker info fails
EXPECTATIONS
  [ "$self_fail" -eq 0 ] || exit 1
  echo "self-test ok: each mutation turned exactly its named check red."
  exit 0
fi

check_body "$WORK/body.sh"
if [ -n "$LABELS" ]; then
  FAILURES=$((FAILURES + 1))
fi
if [ "$FAILURES" -ne 0 ]; then
  echo "pre-push hook gate: FAILED."
  exit 1
fi
echo "pre-push hook gate: clean (a failing suite fails the push; every NOT RUN exits 2, names its cause and both bypasses)."
