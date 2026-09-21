#!/bin/sh
# Prove the web install guard in EVERY state it can reach (#226).
#
# `scripts/web-install-if-stale.sh` decides whether a security patch is applied.
# The thing it replaced was a one-line `[ -f ... ] ||` inside a YAML folded
# scalar, which nothing could test and which nobody could see was wrong.
#
# It said "wrong for eighteen months", and nothing in this repo supports that.
# DERIVED instead, which is both smaller and checkable:
#
#   git log --reverse --format=%ad --date=short | head -1        -> 2026-08-04
#   git log -S'apps/web/node_modules/next/dist/bin/next' -- docker-compose.yml
#                                              -> 072ffad, the BASELINE IMPORT
#
# So it was present in the first commit this repo has and was wrong for the
# whole of its recorded history, which is about six weeks to the #226 fix. How
# long it was wrong BEFORE the import is not knowable from here, and a number
# that cannot be re-derived does not belong in a file about checks that can be.
#
# Watching a guard fire proves it fires. It does not prove it PASSES, and a
# guard that installs unconditionally would make every `up` reinstall the world
# -- indistinguishable, from the outside, from a guard that is working. So both
# directions are exercised here, and so is every refusal.
#
# Run it against a scratch directory, never the real volume:
#
#     sh tests/gates/web_install_guard.sh
#
# It uses `--check`, so it never runs `pnpm install` and never writes into
# anything but its own temporary tree.

set -eu

# An UNRECOGNISED ARGUMENT is exit 2, not a clean run.
#
# This script takes none. Ignoring whatever it is given makes a mistyped or
# imagined flag read as a successful run -- `prettier_hook.sh` printed its
# success banner and exited 0 for a `--self-test` it does not have, reached
# for because the gate beside it DOES have one.
if [ "$#" -gt 0 ]; then
  echo "FAIL: this script takes no arguments; got: $*" >&2
  exit 2
fi


SCRIPT="${SCRIPT:-$(cd "$(dirname "$0")/../.." && pwd)/scripts/web-install-if-stale.sh}"
[ -f "$SCRIPT" ] || { echo "FAIL: cannot find $SCRIPT"; exit 2; }

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

fresh() {
  rm -rf "$ROOT"
  mkdir -p "$ROOT/node_modules" "$ROOT/apps/web/node_modules/next/dist/bin"
  printf 'lockfileVersion: 9.0\n' > "$ROOT/pnpm-lock.yaml"
  : > "$ROOT/apps/web/node_modules/next/dist/bin/next"
}

stamp_from_lock() {
  sha256sum "$ROOT/pnpm-lock.yaml" | cut -d' ' -f1 > "$ROOT/node_modules/.shield-installed-lock"
}

# `$1` expected exit, `$2` a fragment the output must contain, `$3` the label,
# and `$4...` the ARGUMENTS to pass. `expect` below fixes them at `--check`;
# this is what lets the argument-handling states be exercised at all.
expect_args() {
  want_code="$1"; want_text="$2"; label="$3"; shift 3
  set +e
  out="$(SHIELD_WEB_APP_DIR="$ROOT" sh "$SCRIPT" "$@" 2>&1)"
  code=$?
  set -e
  if [ "$code" -ne "$want_code" ]; then
    echo "FAIL [$label]: exit $code, wanted $want_code"
    echo "$out"
    exit 1
  fi
  case "$out" in
    *"$want_text"*) echo "ok   [$label]" ;;
    *) echo "FAIL [$label]: output did not contain '$want_text'"; echo "$out"; exit 1 ;;
  esac
}

# `$1` expected exit, `$2` a fragment the output must contain, `$3` the label.
expect() {
  want_code="$1"; want_text="$2"; label="$3"
  set +e
  out="$(SHIELD_WEB_APP_DIR="$ROOT" sh "$SCRIPT" --check 2>&1)"
  code=$?
  set -e
  if [ "$code" -ne "$want_code" ]; then
    echo "FAIL [$label]: exit $code, wanted $want_code"
    echo "$out"
    exit 1
  fi
  case "$out" in
    *"$want_text"*) : ;;
    *)
      echo "FAIL [$label]: output does not mention '$want_text'"
      echo "$out"
      exit 1
      ;;
  esac
  echo "ok   [$label]"
}

# --- THE PASSING STATE. Without it the guard is only ever seen firing. -------
fresh
stamp_from_lock
expect 0 "skip:" "matching stamp and binary present -> skip"

# --- #226 ITSELF: the lockfile moved and the binary is still there. ----------
# This is the exact state the old guard reported as "nothing to do" while the
# container ran a version with two unauthenticated RCEs.
fresh
stamp_from_lock
printf 'lockfileVersion: 9.0\nnext: 15.5.24\n' > "$ROOT/pnpm-lock.yaml"
expect 1 "the lockfile changed" "lockfile moved -> install"

# --- A volume nobody stamped. -----------------------------------------------
# "Probably fine" is not an answer about a dependency tree, and a first run
# against an existing volume is exactly when it would be tempting.
fresh
expect 1 "no stamp" "unstamped volume -> install"

# --- A fresh or damaged volume. ---------------------------------------------
fresh
stamp_from_lock
rm -f "$ROOT/apps/web/node_modules/next/dist/bin/next"
expect 1 "is missing" "binary absent -> install"

# --- THE REFUSAL. The mount is gone, so the lockfile cannot be read. ---------
# Falling back to a range-resolved install here is the silent drift the whole
# script exists to end, and it is what the container did before this change.
fresh
stamp_from_lock
rm -f "$ROOT/pnpm-lock.yaml"
expect 2 "refuse:" "no lockfile -> refuse, not a range install"

# --- And the refusal must name the remedy that exists. ----------------------
out="$(SHIELD_WEB_APP_DIR="$ROOT" sh "$SCRIPT" --check 2>&1 || true)"
case "$out" in
  *"pnpm-lock.yaml:/app/pnpm-lock.yaml:ro"*) echo "ok   [refusal names the mount to restore]" ;;
  *) echo "FAIL: the refusal does not say how to fix it"; echo "$out"; exit 1 ;;
esac

# --- And the script must be readable by the shell that runs it. -------------
# This repo is developed on Windows and the script is BIND-MOUNTED into a Linux
# container, which reads the WORKING TREE rather than the committed blob. A CRLF
# copy makes `sh` report `: not found` and `set: Illegal option -` on lines that
# are perfectly valid -- errors that name the wrong thing entirely.
#
# `.gitattributes` carries `* text=auto eol=lf`, which normalises on checkout
# and does nothing for a file an editor or a script has just written. Measured
# here: a Python `write_text` during this very change flipped it, and the red it
# produced looked exactly like a broken guard.
#
# Written with `tr -d` rather than a grep for a backslash escape, and that is
# not a style choice: two attempts to write this check through a shell heredoc
# had the escape collapsed on the way in. The first produced a literal CR in
# this file -- which the check then correctly caught in its own source -- and
# the second produced `tr -d ""`, a check that deletes nothing and passes
# always. The second is the dangerous one, and it is the reason the assertion
# below the loop exists.
for f in "$SCRIPT" "$0"; do
  if tr -d '\r' < "$f" | cmp -s - "$f"; then
    :
  else
    echo "FAIL: $f has CRLF line endings; the container's sh cannot run it."
    exit 1
  fi
done

# The check above can be neutered into always-passing by one lost backslash, so
# prove it can still SEE a CR before trusting the result. `CLAUDE.md`: a guard
# must be observed in BOTH states, and watching it pass proves nothing on its
# own.
probe="$(mktemp)"
printf 'a\r\nb\n' > "$probe"
if tr -d '\r' < "$probe" | cmp -s - "$probe"; then
  rm -f "$probe"
  echo "FAIL: the CRLF check cannot detect a CR, so its pass means nothing."
  exit 1
fi
rm -f "$probe"
echo "ok   [both scripts are LF, so the container's sh can read them]"

# ---------------------------------------------------------------------------
# `scripts/dev-web.sh` must CALL this guard, not carry a second copy of the
# idea (#318).
#
# It used to guard its own `pnpm install` on `[[ ! -d node_modules ]]`, over a
# NAMED VOLUME that exists from the first boot onward -- so the guard was false
# forever after and a lockfile change installed nothing. That is #226 exactly,
# surviving inside a script `README.md` documents as a Quick-start path. The
# install also had no `--frozen-lockfile`, so the one run it did fire resolved
# package.json RANGES while CI installs what the lockfile pins.
#
# `CLAUDE.md`: "uses the same X as the Y path" is a claim to enforce by CALLING
# X, never by reimplementing it. Asserted statically because the alternative is
# running a real install, and a gate that installs the world is a gate nobody
# runs.
# ---------------------------------------------------------------------------
DEV_WEB="$(cd "$(dirname "$0")/../.." && pwd)/scripts/dev-web.sh"
if [ ! -f "$DEV_WEB" ]; then
  echo "FAIL: $DEV_WEB is missing; this check cannot look, which is not a pass."
  exit 2
fi

# COMMENT LINES STRIPPED FIRST, and that is not tidiness.
#
# The first version of this check was `grep -q 'web-install-if-stale.sh'` over
# the whole file. `dev-web.sh` NAMES that script five times in its own header,
# explaining why it calls it -- so deleting the actual call left the check
# green. MEASURED: removing the invocation and running this gate returned
# `ok   [dev-web.sh calls the guard...]`, exit 0.
#
# An assertion satisfied by a COMMENT is the #308 shape (a 204 needle matched
# by the sentence three lines above it) and the reason `check_test_integrity`
# exists. It was caught here by red-on-revert and by nothing else: the check
# was correct-looking, correctly motivated, and could not fail.
code_only="$(mktemp)"
sed 's/[[:space:]]*#.*$//' "$DEV_WEB" > "$code_only"

if ! grep -q 'web-install-if-stale' "$code_only"; then
  rm -f "$code_only"
  echo "FAIL: scripts/dev-web.sh does not name web-install-if-stale.sh in CODE."
  echo "      It is documented as a Quick-start path, so an install it performs"
  echo "      itself bypasses the guard that decides whether a patch is applied."
  echo "      (Mentioning it in a comment is not calling it.)"
  exit 1
fi

# Naming it is not running it. Require an actual invocation -- `sh <something>`
# where the something is the guard or the variable holding it.
if ! grep -qE '(^|[[:space:]])(sh|bash)[[:space:]]+.*(\$GUARD|\$\{GUARD\}|web-install-if-stale)' "$code_only"; then
  rm -f "$code_only"
  echo "FAIL: scripts/dev-web.sh references the guard but never executes it."
  echo "      Assigning its path and not running it installs nothing, and the"
  echo "      dev server then starts against whatever is in the volume."
  exit 1
fi
rm -f "$code_only"

# The second copy, stated as what must NOT be there. A script that calls the
# guard AND keeps its own install is not fixed -- whichever runs last wins, and
# the unfrozen one is the one that drifts.
if sed 's/[[:space:]]*#.*$//' "$DEV_WEB" | grep -qE '^[[:space:]]*pnpm install'; then
  echo "FAIL: scripts/dev-web.sh still runs its own \`pnpm install\`."
  echo "      The guard installs with --frozen-lockfile; a second, unguarded"
  echo "      install beside it re-opens #226 whichever order they run in."
  exit 1
fi
echo "ok   [dev-web.sh calls the guard and carries no install of its own]"

echo
# --- ARGUMENT HANDLING. Added because this file claimed "EVERY state it can
# --- reach" while every case it ran passed `--check`, so the script's
# --- unknown-argument arm was exercised by nothing in the repo: delete that
# --- guard and this gate still printed its certificate. The claim was the
# --- thing a reader checks INSTEAD of reading the gate.
expect_args 2 "unknown argument" "an unknown flag is refused, not ignored" --checks
expect_args 2 "unknown argument" "an EMPTY argument is not 'no argument'" ""
expect_args 2 "too many arguments" "a second argument is refused" --check --check

# THE CERTIFICATE CARRIES NO TALLY, deliberately.
#
# It said "all states exercised -- 1 skip, 3 installs, 1 refusal" and then this
# branch appended three argument cases without touching it, so the sentence
# certifying coverage undercounted the file it was certifying. #318 appended an
# install-half section to the same file and rewrote only ITS own version of this
# line -- so whichever won the merge would have named neither the other's cases
# nor the true count, which is a false-coverage certificate of exactly the kind
# this file already shipped once.
#
# `CLAUDE.md`: don't write the count -- if a number describes a list in the same
# document, delete the number and let the list be the count. The `ok [...]` lines
# printed immediately above ARE the list, and they cannot go stale.
echo "web-install-guard: every check above printed ok. There is no tally here on"
echo "purpose -- the labelled lines are the list, and a hand-written count in"
echo "this position has already gone stale twice."
