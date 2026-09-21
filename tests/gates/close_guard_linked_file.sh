#!/usr/bin/env bash
# Prove that a FAILED `gh pr view` leaves no `--linked` file, and that an
# EMPTY answer leaves one.
#
# The close guard (#182) tells "GitHub linked nothing" apart from "I could not
# look" BY THE FILE -- `linked_numbers`' docstring says so in as many words.
# The collect step in `audit-gate.yml` is the only thing that can honour that,
# and its first version could not: `... > /tmp/pr_linked.txt || true` creates
# and truncates the target BEFORE `gh` runs, so a failed query produced an
# empty file that EXISTS. The guard then read an empty set, found no mismatch,
# and printed "clean -- no closing references (verified against GitHub)" over a
# query that never returned -- the accidental close it was built to prevent,
# carrying the sentence that says it cannot happen.
#
# So this EXTRACTS the block from the workflow rather than restating it. A copy
# here would agree with itself forever; the point is to go red when the
# workflow changes. It stubs `gh`, asserts both states, and then runs the real
# guard on what was produced and asserts the VERDICT -- the file's presence is
# only interesting through what the guard does with it.
#
#   tests/gates/close_guard_linked_file.sh              # the gate
#   tests/gates/close_guard_linked_file.sh --self-test  # prove it can fail
#
# `--self-test` puts the old `|| true` shape back and requires this gate to go
# RED. A harness that cannot fail is the defect it exists to prevent.

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

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORKFLOW="$ROOT/.github/workflows/audit-gate.yml"
GUARD="$ROOT/apps/api/scripts/check_issue_references.py"
SELF_TEST=0

# An UNRECOGNISED ARGUMENT is exit 2, not a clean run.
#
# A flag a script does not implement must not SUCCEED. Silent
# argument-ignoring makes every future `--self-test`, `--dry-run` and
# `--check` a coin flip where both faces read as heads: the reader gets the
# success banner they were hoping for and no signal that nothing happened.
#
# Found on `prettier_hook.sh`, which printed its success banner and exited 0
# for `--self-test` -- a flag it does not have, reached for because the gate
# beside it DOES have one. The trap is aimed at careful people: the instinct
# to verify was correct and the reward was a false pass.
# Arity is judged on `$#`, NOT on `${1:-}`.
#
# `case "${1:-}"` cannot tell an ABSENT argument from an EMPTY one: an
# explicit `""` expands to the same thing as no argument at all and took the
# `""` arm, so `close_guard_linked_file.sh ""` ran as though nothing had been
# passed. Two of the four scripts this commit touched rejected `""` and two
# accepted it, and nothing said why -- an unstated carve-out inside the change
# whose thesis is that a script must not accept what it does not implement.
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

MUTATION="${MUTATION:-}"

for f in "$WORKFLOW" "$GUARD"; do
  [ -f "$f" ] || { echo "FAIL: cannot find $f"; exit 2; }
done

# CI runners have `python3`; a Windows dev box usually has only `python`.
# Resolved rather than assumed, and absent -> exit 2, because "no interpreter"
# is a could-not-look, not a pass.
# Probed by RUNNING each candidate, not by `command -v`: Windows ships a
# `python3.exe` App Execution Alias that resolves, prints an advert for the
# Microsoft Store, and exits non-zero. `command -v` cannot tell that apart from
# an interpreter. Absent -> exit 2, because "no interpreter" is a
# could-not-look, not a pass.
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for candidate in python3 python; do
    if "$candidate" -c "import sys" >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
  done
fi
[ -n "$PYTHON" ] || { echo "FAIL: no working python3/python on PATH; cannot extract the block"; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- extract the block, from the workflow, by its own markers ----------------
# Anchored on the `if gh pr view` line -- unique, where `rm -f /tmp/pr_linked`
# is NOT, because the else branch cleans up the scratch path too. The extractor
# below says the same thing; this comment said `rm -f .. fi` for one round, and
# two contradictory statements of the anchor four lines apart send whoever
# edits `audit-gate.yml` to protect the wrong string.
#
# Not found -> exit 2, never a pass, and never the 1 this gate uses for a real
# violation: "the block moved" and "the block is correct" must not share a
# branch, and neither must "the block moved" and "the block is wrong".
"$PYTHON" - "$WORKFLOW" "$WORK/block.sh" <<'EXTRACT'
import re, sys
src, dest = sys.argv[1], sys.argv[2]
lines = open(src, encoding="utf-8").read().split("\n")
# Anchored on `if gh pr view`, which is unique; `rm -f /tmp/pr_linked` is not,
# because the else branch cleans up the scratch path too. Then walk back over
# any leading `rm -f` lines so the pre-clean is part of what gets exercised.
starts = [i for i, l in enumerate(lines) if l.strip().startswith("if gh pr view")]
if len(starts) != 1:
    # `sys.exit(<str>)` prints and exits 1 -- this gate's VIOLATION code. A
    # could-not-look is 2 everywhere else in this file and in every gate in the
    # repo, so it is written explicitly rather than inherited from the idiom.
    sys.stderr.write(
        "EXTRACT FAILED: expected 1 `if gh pr view` line, found %d\n" % len(starts)
    )
    sys.exit(2)
i = starts[0]
while i > 0 and lines[i - 1].strip().startswith("rm -f "):
    i -= 1
ends = [j for j in range(starts[0], len(lines)) if lines[j].strip() == "fi"]
if not ends:
    sys.stderr.write("EXTRACT FAILED: no closing `fi` after the publish decision\n")
    sys.exit(2)
chunk = lines[i:ends[0] + 1]
block = "\n".join(l[10:] if l.startswith(" " * 10) else l.lstrip() for l in chunk)
block = re.sub(r"\$\{\{[^}]*\}\}", "1", block)
# Relocate the fixed /tmp paths into this run's scratch dir, so a real runner's
# files are never touched.
block = block.replace("/tmp/pr_linked", "$SCRATCH/pr_linked")
open(dest, "w", encoding="utf-8", newline="\n").write(block + "\n")
sys.stderr.write("extracted %d lines from the workflow\n" % len(chunk))
EXTRACT

if [ -n "$MUTATION" ]; then
  # A mutation replaces the extracted block entirely, so nothing of the real
  # publish decision survives to make a check pass by accident.
  case "$MUTATION" in
    prefix)
      # The defect this gate was built for, restored exactly: redirect straight
      # at the real path, swallow the status.
      cat > "$WORK/block.sh" <<'BAD'
gh pr view "1" \
  --json closingIssuesReferences \
  --jq '.closingIssuesReferences[].number' > $SCRATCH/pr_linked.txt || true
BAD
      ;;
    donothing)
      # A block that publishes nothing and cleans nothing. This is the mutation
      # that matters, and the reason the self-test runs more than one: under
      # `prefix`, checks 2 and 3 PASS, so a single-mutation self-test showed
      # them able to fail exactly never. `donothing` is what fails when the
      # stale-file pre-creation in `run_block` is removed -- the "redundant
      # cleanup" deletion that would otherwise reopen the do-nothing hole with
      # the self-test still green.
      : > "$WORK/block.sh"
      ;;
    alwayspublish)
      # Publishes an empty file whatever `gh` did -- "I could not look" and
      # "nothing to report" collapsed into one answer, which is the shape the
      # whole close guard exists to keep apart.
      cat > "$WORK/block.sh" <<'BAD'
rm -f $SCRATCH/pr_linked.txt $SCRATCH/pr_linked.raw
gh pr view "1" --json closingIssuesReferences \
  --jq '.closingIssuesReferences[].number' > $SCRATCH/pr_linked.raw || true
touch $SCRATCH/pr_linked.txt
BAD
      ;;
    *)
      echo "unknown MUTATION '$MUTATION'"; exit 2 ;;
  esac
  echo "mutation: $MUTATION"
fi

# --- a stubbed gh ------------------------------------------------------------
mkdir -p "$WORK/bin"
cat > "$WORK/bin/gh" <<'STUB'
#!/usr/bin/env bash
case "$GH_STUB_MODE" in
  fail)    echo "gh: could not query the GitHub API" >&2; exit 1 ;;
  empty)   exit 0 ;;
  numbers) printf '317\n'; exit 0 ;;
  *)       echo "gh stub: unknown GH_STUB_MODE" >&2; exit 64 ;;
esac
STUB
chmod +x "$WORK/bin/gh"

FAILURES=0
FAILED_LABELS=""
note_fail() {
  echo "FAIL [$1]: $2"
  # The extracted block's own stdout and stderr, which were captured and then
  # thrown away for one round. On a syntax error introduced by editing
  # `audit-gate.yml`, the gate's only output was a message about the PUBLISH
  # logic while the real cause -- `syntax error: unexpected end of file` -- sat
  # unread in a file the EXIT trap then deleted. A guard must name the CAUSE,
  # not the check.
  if [ -s "$WORK/out.log" ]; then
    echo "     the block said:"
    sed 's/^/       /' "$WORK/out.log"
  fi
  FAILURES=$((FAILURES + 1))
  FAILED_LABELS="$FAILED_LABELS|$1"
}

LINKED=""
run_block() {  # $1 = GH_STUB_MODE
  SCRATCH="$WORK/scratch"
  rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"
  export SCRATCH
  LINKED="$SCRATCH/pr_linked.txt"
  # A stale file from an earlier query, so "left absent" is a real deletion and
  # not a file that merely never appeared.
  printf '999\n' > "$LINKED"
  GH_STUB_MODE="$1" PATH="$WORK/bin:$PATH" bash -e "$WORK/block.sh" > "$WORK/out.log" 2>&1 || true
}

# `--title`, `--body` and `--commits` are FILE paths, not literals. Passing
# strings made the guard exit 2 with "title file not found" -- the SAME 2 the
# missing-linked-file case wants, so check 1 was green for the wrong reason
# until checks 2 and 3 disagreed with it. Diagnose the disagreement; do not
# vote on it.
verdict() {  # $1 = PR body text -> echoes the guard exit code
  printf 'chore: a title with no numbers\n' > "$WORK/title.txt"
  printf 'chore: a commit with no numbers\n' > "$WORK/commits.txt"
  printf '%s\n' "$1" > "$WORK/body.txt"
  set +e
  "$PYTHON" "$GUARD" --title "$WORK/title.txt" \
    --body "$WORK/body.txt" --commits "$WORK/commits.txt" \
    --linked "$LINKED" > "$WORK/guard.log" 2>&1
  code=$?
  set -e
  echo "$code"
}

# --- 1. a FAILED query leaves no file, and the guard refuses -----------------
run_block fail
if [ -e "$LINKED" ]; then
  note_fail "gh fails" "the linked file EXISTS ($(wc -c < "$LINKED") bytes) -- the guard cannot tell this from 'closes nothing'"
else
  echo "ok   [gh fails] -> linked file absent"
fi
code="$(verdict "No closes declared.")"
if [ "$code" != "2" ]; then
  note_fail "gh fails -> guard" "guard exited $code, wanted 2 (could not look): $(head -1 "$WORK/guard.log")"
else
  echo "ok   [gh fails -> guard] -> exit 2"
fi

# --- 2. an EMPTY answer is a real answer ------------------------------------
run_block empty
if [ ! -e "$LINKED" ]; then
  note_fail "gh returns nothing" "linked file absent -- 'this PR closes nothing' must stay reportable"
elif [ -s "$LINKED" ]; then
  note_fail "gh returns nothing" "linked file is not empty: $(cat "$LINKED")"
else
  echo "ok   [gh returns nothing] -> linked file present and empty"
fi
code="$(verdict "No closes declared.")"
if [ "$code" != "0" ]; then
  note_fail "gh returns nothing -> guard" "guard exited $code, wanted 0: $(head -1 "$WORK/guard.log")"
else
  echo "ok   [gh returns nothing -> guard] -> exit 0"
fi

# --- 3. a real answer still reaches the guard -------------------------------
# Without this the gate is satisfied by a block that never writes anything.
run_block numbers
if ! grep -q 317 "$LINKED" 2>/dev/null; then
  note_fail "gh returns 317" "linked file does not carry 317"
else
  echo "ok   [gh returns 317] -> linked file carries 317"
fi
code="$(verdict "Auto-close-approved: 317")"
if [ "$code" != "0" ]; then
  note_fail "declared and linked -> guard" "guard exited $code, wanted 0: $(head -1 "$WORK/guard.log")"
else
  echo "ok   [declared and linked -> guard] -> exit 0"
fi
code="$(verdict "No closes declared.")"
if [ "$code" != "1" ]; then
  note_fail "linked but not declared -> guard" "guard exited $code, wanted 1: $(head -1 "$WORK/guard.log")"
else
  echo "ok   [linked but not declared -> guard] -> exit 1"
fi

# --- verdict ----------------------------------------------------------------
# Under a mutation, report the failure SET and stop. The driver below compares
# it; this pass makes no judgement of its own.
if [ -n "$MUTATION" ]; then
  echo "SELF_LABELS=$FAILED_LABELS"
  exit 0
fi

if [ "$SELF_TEST" = "1" ]; then
  # Each mutation and the exact set of checks it must break.
  #
  # Named rather than counted, and MORE THAN ONE, which is the correction. The
  # first version of this self-test applied a single mutation and accepted any
  # non-zero count. Under that mutation checks 1 and 1b fail and checks 2, 3a,
  # 3b and 3c pass -- so four of the six were never shown able to fail at all,
  # and a bare `-ne 0` could not tell the difference.
  #
  # That was not hypothetical. Deleting the stale-file pre-creation from
  # `run_block` as redundant cleanup reopens the do-nothing hole this gate
  # exists to close, and the single-mutation self-test stayed GREEN through it
  # -- measured, before this was rewritten. `donothing` is the mutation that
  # goes red on exactly that deletion.
  #
  # Asserting the SET rather than a count also means a check that starts or
  # stops catching something is a red to read, not a number to shrug at.
  self_fail=0
  while IFS='=' read -r mutation expected; do
    [ -n "$mutation" ] || continue
    out="$(MUTATION="$mutation" bash "$0" 2>&1 || true)"
    actual="$(printf '%s\n' "$out" | sed -n 's/^SELF_LABELS=//p')"
    if [ "$actual" != "$expected" ]; then
      echo "SELF-TEST FAILED [$mutation]: broke a different set of checks than expected."
      echo "  expected: ${expected:-<none>}"
      echo "  actual:   ${actual:-<none>}"
      echo "  Either a check stopped discriminating, or one started catching"
      echo "  something it did not before. Both need reading, not a re-run."
      self_fail=1
    else
      echo "self-test ok [$mutation] -> fails exactly [${expected#|}]"
    fi
  done <<'EXPECTATIONS'
prefix=|gh fails|gh fails -> guard
donothing=|gh fails|gh fails -> guard|gh returns nothing|gh returns nothing -> guard|gh returns 317|declared and linked -> guard
alwayspublish=|gh fails|gh fails -> guard|gh returns 317|declared and linked -> guard|linked but not declared -> guard
EXPECTATIONS
  if [ "$self_fail" -ne 0 ]; then
    exit 1
  fi
  echo "self-test ok: every check was observed red under at least one mutation."
  exit 0
fi

if [ "$FAILURES" -ne 0 ]; then
  echo "close-guard linked-file gate: $FAILURES check(s) failed."
  exit 1
fi
echo "close-guard linked-file gate: clean (a failed query leaves no file; an empty answer leaves one)."
