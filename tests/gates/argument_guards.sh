#!/usr/bin/env sh
#
# EVERY ARGUMENT GUARD IN THIS TERRITORY ACTUALLY REFUSES.
#
# ## Why this file exists
#
# The change that added those guards asserted only ONE of them. `expect_args`
# in `web_install_guard.sh` drives `scripts/web-install-if-stale.sh`, and the
# oracle's guard has a unit test. The guards added to `scripts/dev-web.sh`, to
# `web_install_guard.sh` itself and to `close_guard_linked_file.sh` itself were
# asserted by nothing: delete any of the three and every gate in the repo still
# printed its certificate.
#
# That is the exact condition the change exists to end, reproduced inside it --
# a guard against a silent success, itself silently unguarded. It is also not a
# lapse of care: the author asserted the guard on the script that was the
# SUBJECT of the work and not the ones added in passing to the harness, which
# is the reflex `CLAUDE.md` records surviving the rule until the rule has a
# gate.
#
# ## The subject set is DERIVED, and the derivation is stated
#
# `tests/gates/*.sh` is a GLOB, so a shell gate added later is covered without
# anybody registering it -- including gates nobody has thought of yet, which is
# the half an enumeration always misses. This script is in that glob and drives
# ITSELF; the recursion terminates because the child hits its own guard and
# exits before reaching this loop.
#
# The two `scripts/` entries are NAMED rather than globbed, and that is a
# SCOPE rather than an oversight: `scripts/` also holds `red-on-revert.sh`,
# `verify-in-worktree.sh` and `demo-reset.sh`, which are owned elsewhere and
# whose argument handling is not this gate's to assert. A glob there would
# fail on somebody else's file and be deleted within a day.
#
# `verify-in-worktree.sh` is IN the set, and it is the reason the set is worth
# having: it ignored everything after `$1`, so `verify-in-worktree.sh tsc
# --self-test` ran an ordinary tsc, exited 0, and read as a self-test having
# run -- while `CLAUDE.md` tells readers to run that self-test before trusting
# a clean result from a worktree they have not verified from before. The one
# command whose job is to prove the harness can fail was the one silently not
# running, and the reward for asking was a green.
#
# ## Both spellings, because one of them was an unstated carve-out
#
# An UNKNOWN flag and an EMPTY argument are different inputs and were handled
# differently by scripts in the same commit: `case "${1:-}"` cannot tell an
# absent argument from an explicit `""`, so `<script> ""` ran as though nothing
# had been passed. Both are asserted here so the two cannot drift apart again.
#
# ## Silent-success branches, enumerated before the first line was written
#
#   * ZERO scripts discovered -- the glob matched nothing, or the repo root
#     resolved somewhere unexpected. Exit 2. A predicate that matches nothing
#     reports clean, which is `check_test_integrity`'s `rglob` hole and is the
#     shape this whole directory exists to refuse.
#   * a script in the set that does not EXIST -- exit 2, never skipped.
#   * a script that exits 2 with NO message. Exit 2 is also what an unrelated
#     crash produces, so the code alone does not say the guard ran. Every case
#     asserts the refusal TEXT as well.
#
# Exit 0 = every guard refused. 1 = a guard did not. 2 = could not look.

set -eu

# An UNRECOGNISED ARGUMENT is exit 2, not a clean run. This is the guard this
# script asserts on everything else, so it carries one itself -- and, being in
# `tests/gates/*.sh`, it is one of the scripts driven below.
if [ "$#" -gt 0 ]; then
  echo "FAIL: this script takes no arguments; got: $*" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

SUBJECTS=""
for f in "$ROOT"/tests/gates/*.sh; do
  [ -f "$f" ] || continue
  SUBJECTS="$SUBJECTS $f"
done
for named in scripts/dev-web.sh scripts/web-install-if-stale.sh scripts/verify-in-worktree.sh; do
  if [ ! -f "$ROOT/$named" ]; then
    echo "FAIL: could not look -- $named is missing. This gate names it" >&2
    echo "      explicitly, so its absence is a moved file rather than a" >&2
    echo "      clean tree, and skipping it would drop coverage in silence." >&2
    exit 2
  fi
  SUBJECTS="$SUBJECTS $ROOT/$named"
done

count=0
for s in $SUBJECTS; do
  count=$((count + 1))
done
if [ "$count" -eq 0 ]; then
  echo "FAIL: could not look -- no scripts discovered under $ROOT/tests/gates" >&2
  echo "      and scripts/. An empty glob is not a clean tree." >&2
  exit 2
fi

# `$1` the script, `$2` the label for the argument, `$3...` the argument(s).
refuses() {
  script="$1"; what="$2"; shift 2
  set +e
  out="$(sh "$script" "$@" 2>&1)"
  code=$?
  set -e
  name="${script##*/}"
  if [ "$code" -ne 2 ]; then
    echo "FAIL [$name]: $what gave exit $code, wanted 2."
    echo "      A script that accepts what it does not implement reports the"
    echo "      success the caller was hoping for and does something else."
    echo "$out"
    exit 1
  fi
  # THE MESSAGE, not just the code. Exit 2 is also what a crash, a missing
  # interpreter or an unrelated could-not-look branch produces, so the number
  # alone does not say the ARGUMENT GUARD is what ran.
  case "$out" in
    *"FAIL:"*) echo "ok   [$name] $what refused, with a message" ;;
    *)
      echo "FAIL [$name]: $what exited 2 with no refusal message."
      echo "      Exit 2 without a message is indistinguishable from a crash."
      echo "$out"
      exit 1 ;;
  esac
}

echo "argument-guards: $count scripts"
for s in $SUBJECTS; do
  refuses "$s" "an unknown flag" --definitely-not-a-flag
  refuses "$s" "an EMPTY argument" ""
done

echo
echo "argument-guards: every script above refuses an unknown flag and an empty"
echo "argument with exit 2 AND a message. It does NOT assert that a script"
echo "missing a guard entirely is caught -- the set is derived from the files,"
echo "not from a list of who ought to have one."
