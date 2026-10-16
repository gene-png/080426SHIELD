#!/usr/bin/env bash
# Prove `scripts/gitleaks-merge-group.sh` in every state it can reach (#659).
#
# On a merge_group event that script is the whole of "Secret scan (gitleaks)",
# a REQUIRED check: gitleaks-action@v3 refuses the event, so ci.yml runs the
# pinned CLI through it. Its zero-commit guard is what stops a merge-shaped
# queue group from scanning nothing and passing, and nothing pinned it --
# a root `scripts/*.sh` is invisible to `check_gate_fixtures`, which runs
# `[sys.executable] + argv`.
#
# Watching a guard fire proves it fires, not that it passes. So both
# directions are here: a squash-shaped group SCANS (the stub gitleaks must run
# and see the group's range), and each refusal is its own case. gitleaks is a
# stub that records whether it ran and exits with a chosen code; nothing here
# downloads or runs the real binary.
#
#     bash tests/gates/gitleaks_merge_group.sh
#
# Exit codes (D-090): 0 every case behaved; 1 a case did not; 2 could not look
# (an argument given, no git, or the script missing).

set -euo pipefail

if [ "$#" -gt 0 ]; then
  echo "FAIL: this script takes no arguments; got: $*" >&2
  exit 2
fi

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
SCRIPT="$ROOT/scripts/gitleaks-merge-group.sh"
[ -f "$SCRIPT" ] || { echo "FAIL: cannot find $SCRIPT"; exit 2; }
command -v git >/dev/null || { echo "FAIL: git is not on PATH -- could not look"; exit 2; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

for code in 0 1; do
  cat > "$WORK/stub-$code" <<EOF
#!/usr/bin/env bash
echo "STUB gitleaks invoked: \$*"
touch "$WORK/stub-ran"
exit $code
EOF
  chmod +x "$WORK/stub-$code"
done

REPO="$WORK/repo"
git init -q -b main "$REPO"
git -C "$REPO" config user.email gate@example.invalid
git -C "$REPO" config user.name gate
git -C "$REPO" config core.autocrlf false
echo a > "$REPO/f"
git -C "$REPO" add f
git -C "$REPO" commit -q -m base
BASE=$(git -C "$REPO" rev-parse HEAD)
echo b >> "$REPO/f"
git -C "$REPO" commit -q -am squash
SQUASH=$(git -C "$REPO" rev-parse HEAD)
git -C "$REPO" checkout -q -b side "$BASE"
echo c > "$REPO/g"
git -C "$REPO" add g
git -C "$REPO" commit -q -m side
git -C "$REPO" checkout -q --detach "$BASE"
git -C "$REPO" merge -q --no-ff side -m "merge-shaped group"
MERGED=$(git -C "$REPO" rev-parse HEAD)

# check LABEL WANT_CODE WANT_RAN WANT_TEXT -- ARGS...
check() {
  local label=$1 want_code=$2 want_ran=$3 want_text=$4
  shift 5
  rm -f "$WORK/stub-ran"
  local out code=0
  out=$(cd "$REPO" && bash "$SCRIPT" "$@" 2>&1) || code=$?
  local ran=no
  [ -f "$WORK/stub-ran" ] && ran=yes
  if [ "$code" != "$want_code" ]; then
    echo "FAIL [$label]: exit $code, wanted $want_code"; echo "$out"; exit 1
  fi
  if [ "$ran" != "$want_ran" ]; then
    echo "FAIL [$label]: gitleaks ran=$ran, wanted $want_ran"; echo "$out"; exit 1
  fi
  case "$out" in
    *"$want_text"*) echo "ok   [$label] exit $code, gitleaks ran=$ran" ;;
    *) echo "FAIL [$label]: output did not contain '$want_text'"; echo "$out"; exit 1 ;;
  esac
}

check "squash-shaped group scans its range" 0 yes "no-merges --first-parent ${BASE}..${SQUASH}" \
  -- "$WORK/stub-0" "$BASE" "$SQUASH"
check "merge-shaped group: zero commits is could-not-look" 2 no "holds no non-merge first-parent" \
  -- "$WORK/stub-0" "$BASE" "$MERGED"
check "a leak is red" 1 yes "gitleaks exited 1" \
  -- "$WORK/stub-1" "$BASE" "$SQUASH"
check "an unknown sha is could-not-look" 2 no "is not a commit in this checkout" \
  -- "$WORK/stub-0" "$BASE" 0000000000000000000000000000000000000000
check "a missing argument is could-not-look" 2 no "usage:" \
  -- "$WORK/stub-0" "$BASE"

echo "gitleaks-merge-group gate: clean (5 cases; the zero-commit guard fires and a real group scans)."
