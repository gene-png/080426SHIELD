#!/usr/bin/env bash
#
# Mutate one file, run a check, restore it. WITHOUT GIT.
#
# ## Why this exists as a script rather than a rule
#
# `CLAUDE.md` says to verify each assertion red-on-revert, and to commit before
# mutating. Both are correct and both were written down. The author of that line
# then destroyed uncommitted work with `git checkout -- <file>` THREE times in
# one session, twice after recording the lesson.
#
# By this project's own standard that is not a discipline problem. A rule
# written down and walked into repeatedly by its own author is a rule that needs
# a mechanism: the remedy is that the dangerous command stops being reachable,
# not that someone remembers harder.
#
# `git checkout -- <file>` restores from the INDEX. Unstaged work is not "the
# mutation" -- it is everything you have done since the last `git add`, and the
# command cannot tell them apart. The failure is silent, instant, and looks like
# success.
#
# So git is kept out of the restore path entirely. The backup is a plain copy
# and the restore is a plain move, and neither consults the index.
#
# ## Usage
#
#     scripts/red-on-revert.sh <file> <search> <replace> -- <command...>
#
# Exits 0 when the command FAILED under mutation (which is the result you want:
# the check can see the change), 1 when it passed, and 2 when the harness could
# not do its job -- a missing file, a search string that is absent or not
# unique, or a restore that did not verify. Distinct codes because "the test did
# not go red" and "I could not run the experiment" are different answers.
#
# ## --self-test
#
#     scripts/red-on-revert.sh --self-test
#
# Proves the harness can produce each of its three answers, on a scratch file
# it creates and removes. A harness that cannot fail is the defect it exists to
# prevent, and this script shipped for eleven days with a restore check that
# compared a file to itself -- a green no matter what, in the one place a
# reader would look for the guarantee.
#
# NOTE ON <search>: matching is LINE-BASED (`grep -c -F`), so a multi-line
# search string matches zero times and the script exits 2 rather than mutating.
# That is fail-closed and deliberate, but it means multi-line mutations are not
# supported -- pick a unique single line.
set -euo pipefail

if [ "${1:-}" = "--self-test" ]; then
  # Run the harness against a scratch file and require each answer in turn.
  # Every assertion below is on the EXIT CODE, which is the thing callers
  # branch on, and the scratch file is checked afterwards to prove the restore
  # path ran rather than assuming it did.
  self_dir="$(mktemp -d)"
  trap 'rm -rf -- "$self_dir"' EXIT
  probe="$self_dir/probe.txt"
  printf 'alpha
beta
gamma
' > "$probe"
  before="$(cksum < "$probe")"
  fail=0

  # </dev/null so a check that would read stdin fails fast instead of hanging.
  run() { "$0" "$@" >/dev/null 2>&1 </dev/null; echo $?; }

  # NOTE the explicit file argument. `grep -q gamma` with no file reads STDIN
  # and blocks forever, which is how the first draft of this self-test hung --
  # a harness that cannot finish is no better than one that cannot fail.
  got="$(run "$probe" beta BETA -- grep -q gamma "$probe")"
  [ "$got" = "1" ] || { echo "self-test: a check that STAYS GREEN must exit 1, got $got" >&2; fail=1; }

  got="$(run "$probe" beta BETA -- grep -q beta "$probe")"
  [ "$got" = "0" ] || { echo "self-test: a check that GOES RED must exit 0, got $got" >&2; fail=1; }

  got="$(run "$probe" nowhere X -- true)"
  [ "$got" = "2" ] || { echo "self-test: an absent search string must exit 2, got $got" >&2; fail=1; }

  printf 'dup
dup
' > "$self_dir/dup.txt"
  got="$(run "$self_dir/dup.txt" dup X -- true)"
  [ "$got" = "2" ] || { echo "self-test: a search string matching twice must exit 2, got $got" >&2; fail=1; }

  got="$(run "$self_dir/absent.txt" a b -- true)"
  [ "$got" = "2" ] || { echo "self-test: a missing file must exit 2, got $got" >&2; fail=1; }

  # The restore actually happened -- asserted on the bytes, not inferred from
  # the exit codes above.
  [ "$(cksum < "$probe")" = "$before" ] || { echo "self-test: the probe was left MUTATED after all runs" >&2; fail=1; }

  if [ "$fail" -ne 0 ]; then
    echo "red-on-revert: SELF-TEST FAILED -- do not trust this harness." >&2
    exit 2
  fi
  echo "red-on-revert: self-test passed -- 1 (stayed green), 0 (went red), 2 (could not look) x3, and the probe is byte-identical."
  exit 0
fi

if [ "$#" -lt 5 ]; then
  cat >&2 <<'USAGE'
usage: scripts/red-on-revert.sh <file> <search> <replace> -- <command...>

  <file>     the file to mutate, relative to the repo root
  <search>   exact text to replace; MUST occur exactly once
  <replace>  what to put there
  <command>  the check to run; expected to FAIL while mutated

exit 0 = the check went red (good)   1 = it stayed green   2 = could not look
USAGE
  exit 2
fi

FILE="$1"; SEARCH="$2"; REPLACE="$3"; shift 3
[ "${1:-}" = "--" ] || { echo "red-on-revert: expected -- before the command" >&2; exit 2; }
shift

[ -f "$FILE" ] || { echo "red-on-revert: no such file: $FILE" >&2; exit 2; }

# The count guard, and it is not optional. A search string that matches zero
# times means the mutation silently does not land, and the check then reports
# the same green as a check that cannot fail -- the answer you are hoping for,
# which is the worst possible combination. A string that matches twice means
# you changed something you did not mean to.
occurrences="$(grep -c -F -- "$SEARCH" "$FILE" || true)"
if [ "$occurrences" != "1" ]; then
  echo "red-on-revert: search string occurs ${occurrences} time(s) in ${FILE}; need exactly 1." >&2
  echo "red-on-revert: refusing to mutate. A miss and an unintended double-hit both look like success afterwards." >&2
  exit 2
fi

# The ORIGINAL's fingerprint, taken before anything is touched. The restore is
# checked against this rather than against the backup, because the backup is
# MOVED onto the file and stops existing at the moment the check would need it.
ORIGINAL_SUM="$(cksum < "$FILE")"

BACKUP="$(mktemp)"
cp -- "$FILE" "$BACKUP"

restore() {
  # `mv`, not `git checkout`. This restores the bytes that were there when the
  # script started, whatever their staged state, and it cannot reach anything
  # else in the tree.
  mv -f -- "$BACKUP" "$FILE"
}
trap restore EXIT

python - "$FILE" "$SEARCH" "$REPLACE" <<'PY'
import sys
path, search, replace = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, encoding="utf-8") as fh:
    text = fh.read()
assert text.count(search) == 1, "count changed between check and write"
with open(path, "w", encoding="utf-8", newline="") as fh:
    fh.write(text.replace(search, replace))
PY

# Prove the mutation LANDED before reading any result. A revert or a write that
# silently did not apply reports the same green as a test that cannot fail.
if ! grep -q -F -- "$REPLACE" "$FILE"; then
  echo "red-on-revert: the mutation did not land in ${FILE}. Nothing was measured." >&2
  exit 2
fi
echo "red-on-revert: mutated ${FILE} (verified present), running the check..."

set +e
"$@"
code=$?
set -e

# `restore` runs on EXIT, but do it here too so the verification below reads the
# restored file rather than racing the trap.
restore
trap - EXIT

# THE RESTORE IS VERIFIED, and until 2026-09-21 it was not.
#
# This line read `if ! cmp -s -- "$FILE" "$FILE"; then :; fi` -- the file
# compared against ITSELF, always identical, with the result discarded by a
# `:` either way. It looked exactly like a verification, it sat where a reader
# checking for one would look, and the header three dozen lines up promised
# exit 2 for "a restore that did not verify".
#
# So the script written to stop a silent data-loss trap carried a silent
# no-op in its own safety check. Same shape as the defects it exists to find:
# the branch that says "I could not look" did not exist, and the line standing
# in for it produced the reassuring answer unconditionally.
if [ "$(cksum < "$FILE")" != "$ORIGINAL_SUM" ]; then
  echo "red-on-revert: THE RESTORE DID NOT LAND. ${FILE} does not match what" >&2
  echo "red-on-revert: it contained when this script started. Your working tree" >&2
  echo "red-on-revert: is MUTATED -- fix it before reading any result below." >&2
  exit 2
fi
echo "red-on-revert: restored ${FILE} (verified byte-identical to the original)"

if [ "$code" -eq 0 ]; then
  echo "red-on-revert: THE CHECK STAYED GREEN under mutation." >&2
  echo "red-on-revert: it does not discriminate on this change -- treat that as a" >&2
  echo "red-on-revert: finding about the check, not about the code." >&2
  exit 1
fi

echo "red-on-revert: the check went red (exit ${code}) and the file is restored. Good."
exit 0
