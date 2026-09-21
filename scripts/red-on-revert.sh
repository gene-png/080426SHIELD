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
#     scripts/red-on-revert.sh <file> <search> <replace> [<search> <replace>...] -- <command...>
#
# SEVERAL PAIRS, applied together as ONE mutation, because some properties
# cannot be broken with a single edit. Moving a statement past an `await` is
# the case that forced this: it is a delete in one place and an insert in
# another, and neither half alone reproduces the defect -- the delete just
# fails to compile. Every pair must match exactly once, and if any pair does
# not, NOTHING is written.
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

# REFUSE A POISONED ENVIRONMENT RATHER THAN ANSWER FROM ONE.
#
# This script hands a PATH to Python, which is a native Windows executable on
# the machines this repo is developed on. MSYS rewrites such a path at the exe
# boundary; MSYS_NO_PATHCONV=1 suppresses exactly that rewrite, so Python
# receives a literal /c/... that does not exist and dies.
#
# `CLAUDE.md` PRESCRIBES that variable -- correctly -- for `docker ... -w /app`.
# It is an exported variable in a long-lived shell, so the next person setting
# up a docker mount exports it and every later gate in that shell is measuring
# from a poisoned environment. That happened, and it cost three "flaky gate"
# observations that were deterministic all along.
#
# Exit 2, not 1: this is a COULD NOT LOOK. The script cannot trust the path it
# is about to hand over, so it refuses rather than producing a verdict.
#
# Deliberately NOT repaired with `cygpath`. Silently fixing a poisoned
# environment is how a script stops being able to tell you it is poisoned.
if [ "${MSYS_NO_PATHCONV:-}" = "1" ]; then
  echo "$0: MSYS_NO_PATHCONV=1 is set. This script hands a path to Python," >&2
  echo "  which needs the MSYS rewrite that variable suppresses. Unset it" >&2
  echo "  and re-run; do not read this exit as a verdict about the code." >&2
  exit 2
fi

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

  # `bash "$0"`, NOT `"$0"`. This file is mode 100644 in git -- as is nearly
  # every script in this repo, because `core.fileMode` is false on the Windows
  # checkout where they are written, so an exec bit set locally never reaches
  # the index. `ci.yml` invokes all of them as `bash <script>` for the same
  # reason.
  #
  # Invoking `"$0"` directly worked on the author's machine (the filesystem
  # bit was set) and returned 126 -- "found but not executable" -- for EVERY
  # case in CI. The self-test failed loudly and named the code, which is the
  # only reason this took minutes rather than a morning: a harness that had
  # swallowed the 126 would have reported the runs as ordinary failures.
  #
  # </dev/null so a check that would read stdin fails fast instead of hanging.
  run() { bash "$0" "$@" >/dev/null 2>&1 </dev/null; echo $?; }

  # NOTE the explicit file argument. `grep -q gamma` with no file reads STDIN
  # and blocks forever, which is how the first draft of this self-test hung --
  # a harness that cannot finish is no better than one that cannot fail.
  got="$(run --any-red "$probe" beta BETA -- grep -q gamma "$probe")"
  [ "$got" = "1" ] || { echo "self-test: a check that STAYS GREEN must exit 1, got $got" >&2; fail=1; }

  got="$(run --any-red "$probe" beta BETA -- grep -q beta "$probe")"
  [ "$got" = "0" ] || { echo "self-test: a check that GOES RED must exit 0, got $got" >&2; fail=1; }

  got="$(run --any-red "$probe" nowhere X -- true)"
  [ "$got" = "2" ] || { echo "self-test: an absent search string must exit 2, got $got" >&2; fail=1; }

  printf 'dup
dup
' > "$self_dir/dup.txt"
  got="$(run --any-red "$self_dir/dup.txt" dup X -- true)"
  [ "$got" = "2" ] || { echo "self-test: a search string matching twice must exit 2, got $got" >&2; fail=1; }

  got="$(run --any-red "$self_dir/absent.txt" a b -- true)"
  [ "$got" = "2" ] || { echo "self-test: a missing file must exit 2, got $got" >&2; fail=1; }

  # TWO pairs applied together. The check requires BOTH originals to still be
  # present, so it goes RED only if both replacements landed -- which is the
  # property multi-pair exists for: a statement moved past an await is a delete
  # plus an insert, and neither half alone reproduces the defect.
  #
  # Note the polarity, which the first draft of this case got backwards: the
  # script exits 0 when the CHECK FAILS. A check that succeeds under mutation
  # is the "stayed green" answer. The self-test caught that, which is the
  # entire argument for having one.
  multi="$self_dir/multi.txt"
  printf 'one
two
three
' > "$multi"
  before_multi="$(cksum < "$multi")"
  got="$(run --any-red "$multi" one ONE three THREE -- sh -c "grep -qx one '$multi' && grep -qx three '$multi'")"
  [ "$got" = "0" ] || { echo "self-test: both pairs must land and the check go red, got $got" >&2; fail=1; }
  [ "$(cksum < "$multi")" = "$before_multi" ] || { echo "self-test: multi-pair left the file MUTATED" >&2; fail=1; }

  # A pair that does not match refuses the WHOLE mutation. A partial write
  # measures a state nobody designed, so nothing may be written at all.
  printf 'one
two
' > "$multi"
  before_multi="$(cksum < "$multi")"
  got="$(run --any-red "$multi" one ONE nowhere X -- true)"
  [ "$got" = "2" ] || { echo "self-test: one bad pair must refuse everything with 2, got $got" >&2; fail=1; }
  [ "$(cksum < "$multi")" = "$before_multi" ] || { echo "self-test: a refused multi-pair still wrote to the file" >&2; fail=1; }

  # An odd number of pair arguments is a usage error, not a silent drop.
  got="$(run --any-red "$multi" one ONE dangling -- true)"
  [ "$got" = "2" ] || { echo "self-test: an unpaired search must exit 2, got $got" >&2; fail=1; }

  # --- WHICH RED. The named test must be the one that failed. ---
  #
  # THE CASE THAT WOULD HAVE CAUGHT THE const-in-try MUTATION. That mutation
  # broke the build, reddened an UNRELATED test, and left the named one
  # passing -- and the script said "Good", which reads as "the new test does
  # not discriminate". It was caught by a human reading the diff.
  named="$self_dir/named.txt"
  printf 'x
' > "$named"

  got="$(run --expect test_alpha "$named" x X -- sh -c 'echo "FAILED test_alpha"; exit 1')"
  [ "$got" = "0" ] || { echo "self-test: the NAMED test going red must exit 0, got $got" >&2; fail=1; }

  got="$(run --expect test_alpha "$named" x X -- sh -c 'echo "FAILED test_beta"; exit 1')"
  [ "$got" = "1" ] || { echo "self-test: red on a DIFFERENT test must exit 1, got $got" >&2; fail=1; }

  # The name appearing in PASSING output must not count. Matching it anywhere
  # in the log is the mistake this case exists to forbid.
  got="$(run --expect test_alpha "$named" x X -- sh -c 'echo "ok test_alpha"; echo "FAILED test_beta"; exit 1')"
  [ "$got" = "1" ] || { echo "self-test: a passing mention of the name must not count, got $got" >&2; fail=1; }

  # Neither flag is a usage error, not a silent downgrade to the weak form.
  got="$(run "$named" x X -- true)"
  [ "$got" = "2" ] || { echo "self-test: omitting --expect and --any-red must exit 2, got $got" >&2; fail=1; }

  # The restore actually happened -- asserted on the bytes, not inferred from
  # the exit codes above.
  [ "$(cksum < "$probe")" = "$before" ] || { echo "self-test: the probe was left MUTATED after all runs" >&2; fail=1; }

  # 126/127 are "could not execute", never a verdict. Saying so turns a
  # confusing wall of wrong-exit-code lines into one sentence naming the cause.
  if [ "$fail" -ne 0 ]; then
    echo "red-on-revert: SELF-TEST FAILED -- do not trust this harness." >&2
    echo "red-on-revert: if the codes above are 126 or 127, the script could not" >&2
    echo "red-on-revert: be EXECUTED rather than having produced a verdict --" >&2
    echo "red-on-revert: check how it is being invoked, not what it decided." >&2
    exit 2
  fi
  echo "red-on-revert: self-test passed -- 1 (stayed green), 0 (named test went red), 1 (red on a DIFFERENT test), 2 (could not look) x6, multi-pair applied and refused atomically, and every probe is byte-identical."
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

# --expect <needle> names the test that MUST be the one to go red.
#
# Without it, "the command failed" is all this script knows, and that is not
# what red-on-revert is for. A mutation can break the BUILD, or redden an
# unrelated test, and the exit code is identical to the one you wanted.
# Measured 2026-09-21: a mutation intended to move a token below an await
# instead put a `const` inside a `try`, out of scope for its `catch`. A
# DIFFERENT test went red, the named one passed, and the script reported
# success -- which reads as "the new test does not discriminate" when the
# truth was "the mutation was invalid". It was caught by reading the diff.
#
# --any-red is the explicit opt-out, and it has to be typed. An accidental
# omission must not silently buy the weaker guarantee.
#
# THE COMMAND MUST PRINT THE FAILING TEST'S IDENTIFIER, because the match
# needs a failure marker and the name on the SAME LINE. A name that appears
# anywhere in the log proves nothing -- it appears in passing output too.
# Practically: pytest needs `-rf` (or no `-rN`), which prints
# `FAILED <nodeid>`; vitest prints `x <name>` by default. A run that hides
# its failure summary is refused with "WENT RED ON SOMETHING ELSE", which is
# the harness being strict rather than wrong.
EXPECT=""
ANY_RED=0
while [ "$#" -gt 0 ]; do
  case "${1:-}" in
    --expect) [ "$#" -ge 2 ] || { echo "red-on-revert: --expect needs a value" >&2; exit 2; }
              EXPECT="$2"; shift 2 ;;
    --any-red) ANY_RED=1; shift ;;
    *) break ;;
  esac
done
if [ -z "$EXPECT" ] && [ "$ANY_RED" -eq 0 ]; then
  echo "red-on-revert: name the test that must go red with --expect <substring>," >&2
  echo "red-on-revert: or pass --any-red to accept 'something failed' as the result." >&2
  echo "red-on-revert: a bare non-zero exit does not prove the assertion under test" >&2
  echo "red-on-revert: can see the change, which is the only thing this script is for." >&2
  exit 2
fi

FILE="$1"; shift
PAIRS=()
while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do
  [ "$#" -ge 2 ] || { echo "red-on-revert: search/replace pairs must come in twos" >&2; exit 2; }
  PAIRS+=("$1" "$2"); shift 2
done
[ "${1:-}" = "--" ] || { echo "red-on-revert: expected -- before the command" >&2; exit 2; }
shift
[ "${#PAIRS[@]}" -ge 2 ] || { echo "red-on-revert: need at least one search/replace pair" >&2; exit 2; }

[ -f "$FILE" ] || { echo "red-on-revert: no such file: $FILE" >&2; exit 2; }

# The count guard, and it is not optional. A search string that matches zero
# times means the mutation silently does not land, and the check then reports
# the same green as a check that cannot fail -- the answer you are hoping for,
# which is the worst possible combination. A string that matches twice means
# you changed something you did not mean to.
# EVERY pair is counted BEFORE anything is written. A partial mutation is
# worse than none: it changes the file and measures a state nobody designed.
i=0
while [ "$i" -lt "${#PAIRS[@]}" ]; do
  occurrences="$(grep -c -F -- "${PAIRS[$i]}" "$FILE" || true)"
  if [ "$occurrences" != "1" ]; then
    echo "red-on-revert: search string occurs ${occurrences} time(s) in ${FILE}; need exactly 1." >&2
    echo "red-on-revert:   ${PAIRS[$i]}" >&2
    echo "red-on-revert: refusing to mutate. A miss and an unintended double-hit both look like success afterwards." >&2
    exit 2
  fi
  i=$((i + 2))
done

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

python - "$FILE" "${PAIRS[@]}" <<'PY'
import sys
path, rest = sys.argv[1], sys.argv[2:]
with open(path, encoding="utf-8") as fh:
    text = fh.read()
for j in range(0, len(rest), 2):
    search, replace = rest[j], rest[j + 1]
    assert text.count(search) == 1, "count changed between check and write: %r" % search
    text = text.replace(search, replace)
with open(path, "w", encoding="utf-8", newline="") as fh:
    fh.write(text)
PY

# Prove EVERY replacement LANDED before reading any result. A write that
# silently did not apply reports the same green as a test that cannot fail --
# and with several pairs, one landing is not evidence that the rest did.
i=1
while [ "$i" -lt "${#PAIRS[@]}" ]; do
  if ! grep -q -F -- "${PAIRS[$i]}" "$FILE"; then
    echo "red-on-revert: a replacement did not land in ${FILE}. Nothing was measured." >&2
    echo "red-on-revert:   ${PAIRS[$i]}" >&2
    exit 2
  fi
  i=$((i + 2))
done
echo "red-on-revert: mutated ${FILE} -- $(( ${#PAIRS[@]} / 2 )) replacement(s), all verified present. Running the check..."

OUTPUT="$(mktemp)"
set +e
"$@" 2>&1 | tee "$OUTPUT"
code=${PIPESTATUS[0]}
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
  rm -f -- "$OUTPUT"
  echo "red-on-revert: THE CHECK STAYED GREEN under mutation." >&2
  echo "red-on-revert: it does not discriminate on this change -- treat that as a" >&2
  echo "red-on-revert: finding about the check, not about the code." >&2
  exit 1
fi

# WHICH red. A failure marker and the named test on the SAME LINE: the name
# alone appears in passing output too, so matching it anywhere proves nothing.
if [ -n "$EXPECT" ]; then
  # `FAIL[ :]`, not `FAIL `. The house style under `tests/gates/` is `FAIL:`
  # with a COLON, which a trailing space cannot match -- so `--expect` reported
  # THE CHECK WENT RED ON SOMETHING ELSE for a gate that had gone red on
  # exactly the named assertion.
  #
  # Measured 2026-09-21 across the four gates PREDATING this change, so the
  # count excludes the one added alongside it: 22 `FAIL:` against 11 `FAIL `.
  #
  # It failed LOUDLY, which is why it cost nothing. But it is a false negative
  # in the harness whose whole job is telling a real assertion from a
  # decorative one, and the direction matters: it reports a discriminating
  # test as non-discriminating, which invites deleting or weakening a test
  # that was working.
  if ! grep -F -- "$EXPECT" "$OUTPUT" | grep -qE '(×|✕|✗|FAILED|FAIL[ :]|AssertionError|not ok)'; then
    echo "red-on-revert: THE CHECK WENT RED ON SOMETHING ELSE." >&2
    echo "red-on-revert: exit ${code}, but no failing line mentions:" >&2
    echo "red-on-revert:   ${EXPECT}" >&2
    echo "red-on-revert: so this run says nothing about whether that assertion can" >&2
    echo "red-on-revert: see the change. The usual cause is a mutation that broke" >&2
    echo "red-on-revert: the build or reddened an unrelated test -- read the output" >&2
    echo "red-on-revert: before concluding the test does not discriminate." >&2
    rm -f -- "$OUTPUT"
    exit 1
  fi
  rm -f -- "$OUTPUT"
  echo "red-on-revert: '${EXPECT}' went red (exit ${code}) and the file is restored. Good."
  exit 0
fi

rm -f -- "$OUTPUT"
echo "red-on-revert: the check went red (exit ${code}) and the file is restored."
echo "red-on-revert: --any-red was used, so WHICH test failed is unverified."
exit 0
