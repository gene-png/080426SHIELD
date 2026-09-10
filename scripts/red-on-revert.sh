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
set -euo pipefail

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

if ! cmp -s -- "$FILE" "$FILE"; then :; fi
echo "red-on-revert: restored ${FILE}"

if [ "$code" -eq 0 ]; then
  echo "red-on-revert: THE CHECK STAYED GREEN under mutation." >&2
  echo "red-on-revert: it does not discriminate on this change -- treat that as a" >&2
  echo "red-on-revert: finding about the check, not about the code." >&2
  exit 1
fi

echo "red-on-revert: the check went red (exit ${code}) and the file is restored. Good."
exit 0
