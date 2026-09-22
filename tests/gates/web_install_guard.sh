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
REPO="$(cd "$(dirname "$0")/../.." && pwd)"

# THE ENTRY POINTS ARE NAMED; THE BYPASS SWEEP IS DERIVED. Both, because
# neither is enough on its own.
#
# This section asserted `dev-web.sh` ALONE while the branch adding it also
# converted `.devcontainer/post-create.sh`, which `devcontainer.json` runs as
# `postCreateCommand` -- Quick-start Option A's FIRST install, reached before
# `dev-web.sh` exists in the flow. Restore that file's
# `pnpm install --prefer-offline || echo "...non-fatal"` and every gate in this
# repo still printed its certificate, under a change whose own title says BOTH
# documented paths. A gate covering half of a two-path claim is the
# false-coverage shape this file already shipped once.
#
# `CLAUDE.md`: fix from the SHAPE, not from the list you were handed. So the
# list below is the two paths a human is DOCUMENTED to run, which get the
# strong positive assertion that they CALL the guard, and the sweep after it is
# the derived half: no shell script in this repo may carry an install of its
# own, whether or not anyone thought to name it here.
entry_point_delegates() { # <path-relative-to-repo> <label>
  rel="$1"; label="$2"
  f="$REPO/$rel"
  if [ ! -f "$f" ]; then
    echo "FAIL: $rel is missing; this check cannot look, which is not a pass."
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
  sed 's/[[:space:]]*#.*$//' "$f" > "$code_only"

  if ! grep -q 'web-install-if-stale' "$code_only"; then
    rm -f "$code_only"
    echo "FAIL: $rel does not name web-install-if-stale.sh in CODE."
    echo "      It is documented as a Quick-start path, so an install it performs"
    echo "      itself bypasses the guard that decides whether a patch is applied."
    echo "      (Mentioning it in a comment is not calling it.)"
    exit 1
  fi

  # Naming it is not running it. Require an actual invocation -- `sh <something>`
  # where the something is the guard or the variable holding it.
  if ! grep -qE '(^|[[:space:]])(sh|bash)[[:space:]]+.*(\$GUARD|\$\{GUARD\}|web-install-if-stale)' "$code_only"; then
    rm -f "$code_only"
    echo "FAIL: $rel references the guard but never executes it."
    echo "      Assigning its path and not running it installs nothing, and the"
    echo "      dev server then starts against whatever is in the volume."
    exit 1
  fi
  rm -f "$code_only"
  echo "ok   [$label calls the guard]"
}

entry_point_delegates scripts/dev-web.sh "dev-web.sh"
# Quick-start Option A's postCreateCommand. Its install ran BEFORE dev-web.sh
# was ever reached, so "both documented paths go through the guard" was false
# while this file was unchecked.
entry_point_delegates .devcontainer/post-create.sh "post-create.sh"

# THE DERIVED HALF, stated as what must NOT exist anywhere. A script that calls
# the guard AND keeps its own install is not fixed -- whichever runs last wins,
# and the unfrozen one is the one that drifts. Swept over every tracked shell
# script rather than over the two named above, because the next bypass will be
# written by someone who never read this file.
#
# TWO EXEMPTIONS, both stated so an unexplained hit is a real finding:
#   * `scripts/web-install-if-stale.sh` IS the guard, and its install is the
#     one legitimate one in the repo.
#   * `tests/gates/` holds the gates themselves, which quote `pnpm install` as
#     a pattern to search for and stub the binary. A gate installs nothing.
#
# QUOTED STRINGS ARE STRIPPED AS WELL AS COMMENTS, and that is not tidiness
# either. Stripping comments alone reported `scripts/prettier-hook.sh` and
# `scripts/verify-in-worktree.sh` as bypasses over two `echo` lines -- one of
# which says `pnpm installs`, a verb. That is this file's own recorded defect
# facing the other way: a check on CODE satisfied by PROSE. An over-reporting
# gate is not the safe direction, because the cheapest route to green is to
# exempt the file.
#
# THE RESIDUALS, MEASURED rather than reasoned about, by running the stripper
# and the pattern over one probe string per form. Stated because a sweep whose
# blind spots are unwritten is a sweep whose next reader assumes it has none:
#
#   caught: a bare line; `(cd "$X" && pnpm install ...) || echo "..."` (the
#           exact form this branch removes from post-create.sh); a heredoc
#           body; `npx pnpm install`; the four other subcommands that write
#           node_modules (`i`, `add`, `up`, `update`).
#   NOT caught, and each needs a different mechanism:
#     * an install inside a QUOTED command argument -- `sh -c "pnpm install"`.
#       Stripping quoted strings is what stops the prose false positives above,
#       so this is the price of that, not an oversight.
#     * variable indirection -- `CMD="pnpm install"; $CMD`.
#     * a non-`.sh` writer: `Dockerfile`, `docker-compose.yml`,
#       `devcontainer.json`, a `package.json` script, a `.ps1`. `git ls-files
#       '*.sh'` is the stated population and nothing here claims more.
#   correctly NOT caught: `echo "run pnpm install first"`, and the verb in
#           `the entry pnpm installs for the workspace`.
bypass_hits="$(
  cd "$REPO" || exit 2
  git ls-files '*.sh'     | grep -v '^scripts/web-install-if-stale\.sh$'     | grep -v '^tests/gates/'     | while IFS= read -r f; do
        if sed -e "s/'[^']*'//g" -e 's/\"[^\"]*\"//g' -e 's/[[:space:]]*#.*$//' "$f"              | grep -qE '(^|[[:space:]]|;|&&)[[:space:]]*pnpm[[:space:]]+(install|i|add|up|update)([[:space:]]|$)'; then
          echo "$f"
        fi
      done
)"
# `git ls-files` returning NOTHING is not a clean sweep -- it is a sweep that
# could not look, which D-051 says must never share a branch with a pass.
tracked_sh="$(cd "$REPO" && git ls-files '*.sh' | wc -l)"
if [ "$tracked_sh" -eq 0 ]; then
  echo "FAIL: git ls-files '*.sh' found no shell scripts; this sweep could not look."
  exit 2
fi
if [ -n "$bypass_hits" ]; then
  echo "FAIL: these shell scripts run an install of their own, bypassing the guard:"
  echo "$bypass_hits" | sed 's/^/        /'
  echo "      The guard installs with --frozen-lockfile and keys on the lockfile"
  echo "      hash; a second, unguarded install beside it re-opens #226 whichever"
  echo "      order they run in. Call scripts/web-install-if-stale.sh instead."
  exit 1
fi
echo "ok   [no shell script outside the guard carries an install of its own]"

# ---------------------------------------------------------------------------
# THE INSTALL HALF. Every case above passes `--check`, which returns at
#
#     [ "$CHECK_ONLY" -eq 1 ] && exit "$verdict"
#
# BEFORE `pnpm install --frozen-lockfile` and before the stamp write. So this
# file certified "all states exercised" while covering `decide()` alone, and
# the half that decides whether a security patch is actually APPLIED was
# asserted by nothing: delete `--frozen-lockfile`, move the stamp above the
# install, or drop the refuse->exit-1 remapping, and every case above stayed
# green.
#
# `pnpm` is STUBBED rather than run. A gate that installs the world is a gate
# nobody runs, and the properties worth pinning are about what the script does
# with the installer, not about npm. The stub records its argv and can be made
# to fail on demand, which is what makes the ordering property testable at all.
# ---------------------------------------------------------------------------
STUB_DIR="$(mktemp -d)"
trap 'rm -rf "$ROOT" "$STUB_DIR"' EXIT
# APPENDS, one line per invocation, and that is not a detail.
#
# It overwrote (`>`), so only the LAST call was visible. MEASURED with
# red-on-revert: adding a bare `pnpm install` BEFORE the frozen one left this
# gate GREEN -- the second call overwrote the first, the recorded argv still
# read `install --frozen-lockfile`, and a script running an unguarded install
# alongside the guarded one passed a check written to forbid exactly that.
# A one-character bug in a gate asserting that another script has no
# one-character bug.
cat > "$STUB_DIR/pnpm" <<'STUB'
#!/bin/sh
echo "$@" >> "$PNPM_ARGV"
[ -n "${PNPM_MUST_FAIL:-}" ] && exit 1
exit 0
STUB
chmod +x "$STUB_DIR/pnpm"
PNPM_ARGV="$STUB_DIR/argv"
export PNPM_ARGV

# `$1` expected exit, `$2` the label. Runs WITHOUT `--check`, so the install
# path is reached.
install_run() {
  want_code="$1"; label="$2"
  set +e
  install_out="$(PATH="$STUB_DIR:$PATH" SHIELD_WEB_APP_DIR="$ROOT" sh "$SCRIPT" 2>&1)"
  install_code=$?
  set -e
  if [ "$install_code" -ne "$want_code" ]; then
    echo "FAIL [$label]: exit $install_code, wanted $want_code"
    echo "$install_out"
    exit 1
  fi
}

# --- The installer is invoked with --frozen-lockfile. -----------------------
# This is the whole reason the guard exists: CI installs what the lockfile
# pins, and a range-resolved install in the container means the two can differ
# with nothing saying so.
fresh
rm -f "$PNPM_ARGV"
install_run 0 "stale volume -> install"
if [ ! -f "$PNPM_ARGV" ]; then
  echo "FAIL [install] the guard reported an install and never ran the installer."
  exit 1
fi
# EVERY invocation, not "an" invocation. A check reading only one of them is
# satisfied by a guarded install standing beside an unguarded one, which is the
# state `dev-web.sh` was actually in.
unfrozen="$(grep -c -v -- '--frozen-lockfile' "$PNPM_ARGV" || true)"
if [ "$unfrozen" -ne 0 ]; then
  echo "FAIL [install] $unfrozen pnpm invocation(s) ran WITHOUT --frozen-lockfile:"
  grep -v -- '--frozen-lockfile' "$PNPM_ARGV"
  echo "      An unfrozen install resolves package.json RANGES while CI installs"
  echo "      what the lockfile pins, which is the drift this script exists to"
  echo "      end. One beside a frozen one is not better -- whichever runs last"
  echo "      decides what is on disk."
  exit 1
fi
if [ "$(wc -l < "$PNPM_ARGV")" -ne 1 ]; then
  echo "FAIL [install] expected exactly one pnpm invocation, got $(wc -l < "$PNPM_ARGV"):"
  cat "$PNPM_ARGV"
  exit 1
fi
echo "ok   [exactly one pnpm invocation, and it uses --frozen-lockfile]"

# --- The stamp is written AFTER the install, and only if it SUCCEEDED. ------
# `CLAUDE.md`: a success record must be written where the success is. A stamp
# written above the install claims currency for a run that may not have
# finished -- and the next boot reads that stamp, sees a match, and skips.
# A failed install that leaves a stamp is therefore not a failed install; it is
# a permanently wrong container.
fresh
rm -f "$PNPM_ARGV"
PNPM_MUST_FAIL=1 install_run 1 "a failing install is fatal"
if [ -f "$ROOT/node_modules/.shield-installed-lock" ]; then
  echo "FAIL [stamp] the install FAILED and a stamp was written anyway."
  echo "      The next boot will read it, match, and skip -- so the failure"
  echo "      becomes permanent and silent."
  exit 1
fi
echo "ok   [a failed install exits non-zero and leaves NO stamp]"

# --- And a successful one stamps the lockfile's own hash. -------------------
fresh
install_run 0 "successful install stamps"
if [ ! -f "$ROOT/node_modules/.shield-installed-lock" ]; then
  echo "FAIL [stamp] the install succeeded and wrote no stamp, so every boot reinstalls."
  exit 1
fi
if [ "$(cat "$ROOT/node_modules/.shield-installed-lock")" != "$(sha256sum "$ROOT/pnpm-lock.yaml" | cut -d' ' -f1)" ]; then
  echo "FAIL [stamp] the stamp does not hold the lockfile's hash, so it can never match."
  exit 1
fi
echo "ok   [a successful install stamps the lockfile hash]"

# --- A REFUSAL in install mode exits 1, not 2. ------------------------------
# `--check` returns the raw verdict; without it, 2 is remapped to 1 so the
# compose command and `dev-web.sh` treat a refusal as fatal. Nothing above
# reached that remapping.
fresh
stamp_from_lock
rm -f "$ROOT/pnpm-lock.yaml"
rm -f "$PNPM_ARGV"
install_run 1 "no lockfile -> refuse, fatal"
if [ -f "$PNPM_ARGV" ]; then
  echo "FAIL [refusal] the guard refused and ran the installer anyway."
  exit 1
fi
echo "ok   [a refusal is fatal and installs nothing]"

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

# The RESIDUAL, stated rather than left to be assumed. `pnpm` is a stub above,
# so nothing in this file says a real install succeeds -- only what this script
# does with the installer. Written with no tally for the same reason as the
# certificate above.
echo
echo "NOT covered: pnpm is stubbed, so nothing here says a real install"
echo "succeeds. That is npm's job, not this guard's."
