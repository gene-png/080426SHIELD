#!/bin/sh
# Prove the prettier hook reads the right version and refuses when it cannot.
#
# The thing this replaced was `rev: v3.1.0` in a YAML file -- a version literal
# nothing checked, eight minors behind CI, on a hook that rewrites every commit.
# Replacing one unchecked literal with another would have changed nothing that
# matters, so the hook derives the version and this proves the derivation.
#
# `--print-version` does the read and stops, so every case here runs without
# invoking prettier or the network.

set -eu

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

HOOK="${HOOK:-$(cd "$(dirname "$0")/../.." && pwd)/scripts/prettier-hook.sh}"

# An UNRECOGNISED ARGUMENT is exit 2, not a clean run.
#
# This gate took no arguments and ignored whatever it was given, so
# `prettier_hook.sh --self-test` printed the ordinary success banner and
# exited 0 -- and this directory's OTHER gate does have a `--self-test`, so
# reaching for it here is the natural mistake. A developer gets a green and
# believes a harness-can-fail check ran. That is "I could not look" wearing
# "nothing to complain about", in the gate suite built to refuse it.
#
# Found while verifying, for the registry entry on `main`, that
# `close_guard_linked_file.sh` is the only shell gate carrying a self-test.
# It is -- and this is how that turned out to be checkable rather than
# obvious.
if [ "$#" -gt 0 ]; then
  echo "FAIL: this gate takes no arguments; got: $*" >&2
  echo "      It has no --self-test. \`close_guard_linked_file.sh\` does, and" >&2
  echo "      silently exiting 0 here would read as one having run." >&2
  exit 2
fi

# CI runners have `python3`; a Windows dev box usually has only `python`.
# Probed by RUNNING each candidate, not by `command -v`: Windows ships a
# `python3.exe` App Execution Alias that resolves, prints a Microsoft Store
# advert, and exits non-zero. Absent -> exit 2, because "no interpreter" is a
# could-not-look, not a pass. Same shape as `close_guard_linked_file.sh`,
# deliberately, so there is one probe idiom in this directory and not two.
# An env-provided PYTHON is VALIDATED too, not trusted. Taking it on faith
# made `PYTHON=/nonexistent` exit 127 from `set -e` instead of the 2 this
# repo reserves for "I could not look" -- measured, not reasoned. A broken
# override and a missing interpreter are the same condition and must share
# the same exit code, or the gate's two non-zero meanings blur at exactly the
# point someone is debugging it.
PYTHON="${PYTHON:-}"
if [ -n "$PYTHON" ] && ! "$PYTHON" -c "import sys" >/dev/null 2>&1; then
  echo "FAIL: PYTHON='$PYTHON' is set but does not run; cannot read the lockfile independently" >&2
  exit 2
fi
if [ -z "$PYTHON" ]; then
  for candidate in python3 python; do
    if "$candidate" -c "import sys" >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
  done
fi
[ -n "$PYTHON" ] || { echo "FAIL: no working python3/python on PATH; cannot read the lockfile independently" >&2; exit 2; }
[ -f "$HOOK" ] || { echo "FAIL: cannot find $HOOK"; exit 2; }

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
# A real repo, because `git rev-parse --show-toplevel` walks for a `.git` it can
# actually read -- a bare directory of that name is not one, and the hook's
# error then names git rather than the lockfile.
( cd "$ROOT" && git init -q . )

run() {
  # Executed DIRECTLY so the shebang decides the interpreter, which is what
  # `language: script` in `.pre-commit-config.yaml` does. `sh "$HOOK"` was an
  # override, and it made this gate answer a different question than the one it
  # is named for.
  #
  # It passed on Windows for the reason overrides usually pass: Git Bash's `sh`
  # IS bash. On an Ubuntu runner `sh` is dash, the hook's `set -euo pipefail`
  # is rejected, and the whole gate came back
  # `exit 2, 'set: Illegal option -o pipefail'` -- caught on this gate's FIRST
  # CI run, after #318 wired it into a workflow. It had been in the repo,
  # invoked by nothing, since #168.
  ( cd "$ROOT" && "$HOOK" --print-version 2>&1 )
}

expect_ok() {
  want="$1"; label="$2"
  set +e
  out="$(run)"; code=$?
  set -e
  if [ "$code" -ne 0 ] || [ "$out" != "$want" ]; then
    echo "FAIL [$label]: exit $code, output '$out', wanted '$want'"
    exit 1
  fi
  echo "ok   [$label] -> $out"
}

expect_refusal() {
  want_text="$1"; label="$2"
  set +e
  out="$(run)"; code=$?
  set -e
  if [ "$code" -eq 0 ]; then
    echo "FAIL [$label]: exited 0. A hook that shrugs and runs an unpinned"
    echo "  prettier restarts the divergence silently -- that is #168."
    exit 1
  fi
  case "$out" in
    *"$want_text"*) echo "ok   [$label]" ;;
    *) echo "FAIL [$label]: refusal does not mention '$want_text'"; echo "$out"; exit 1 ;;
  esac
}

# A lockfile with `version` under the root importer, which is what the hook
# reads and what pnpm installs for the workspace `pnpm format:check` runs in.
write_lock() {  # $1 = importer version, $2... = extra `packages:` lines
  ver="$1"; shift
  {
    printf 'lockfileVersion: 9.0\n'
    printf 'importers:\n  .:\n    devDependencies:\n      prettier:\n'
    printf '        specifier: ^%s\n        version: %s\n' "$ver" "$ver"
    printf 'packages:\n'
    for line in "$@"; do printf '  %s\n' "$line"; done
  } > "$ROOT/pnpm-lock.yaml"
}

# --- THE READ. Without this the refusals could all be one broken pattern. ----
write_lock 3.9.6 'prettier@3.9.6:'
expect_ok "3.9.6" "reads the resolved version"

# --- A VERSION THAT IS NOT THE REPO'S OWN. ----------------------------------
# Every success case used to expect 3.9.6, which was also this repo's real pin when written (2026-08-30) --
# so `VERSION=3.9.6` hardcoded, or a `${VERSION:-3.9.6}` fallback, passed them.
# A fixture pinning something else is what makes the read load-bearing (#318).
write_lock 3.1.0 'prettier@3.1.0:'
expect_ok "3.1.0" "reads a version that is NOT the repo's own"

# --- A TRANSITIVE entry must not win. ---------------------------------------
# `eslint-plugin-prettier` and friends are real dependencies whose names
# CONTAIN `prettier`, so any derivation matching the bare word picks one of
# them and runs some other package's version number as prettier's.
#
# The rationale here used to say "an unanchored grep picks whichever comes
# first". THERE IS NO GREP. The hook parses with awk, and even its predecessor
# grep was anchored to two leading spaces -- so that sentence pointed a reader
# at a mechanism this file has never contained.
#
# SUBSUMED, and kept anyway: cases below cover this and strictly more -- the
# LOWER-second-entry case and the packages-only case each go red on a full
# revert to `packages:` + `head -1`, which is the only mutation this one
# catches. It stays as the cheapest statement of the property; it is not
# load-bearing, and it should not be cited as though it were.
write_lock 3.9.6 'eslint-plugin-prettier@5.0.0:' 'prettier@3.9.6:'
expect_ok "3.9.6" "a transitive prettier-ish entry does not win"

# --- THE #311 DEFECT: a LOWER second entry must not win. --------------------
# `packages:` is flat and ALPHABETICALLY SORTED, so a second prettier does not
# append -- `prettier@2.8.8` sorts BEFORE `prettier@3.9.6`, and the old
# `head -1` took it. Any transitive dependency pulling an older prettier would
# have silently rolled the hook back to reformatting every commit with a version
# CI rejects: #168's defect, arriving through the fix for #168.
#
# This is the case the old derivation FAILS. Measured before the fix: the
# `head -1` grep returns 2.8.8 for this lockfile.
write_lock 3.9.6 'prettier@2.8.8:' 'prettier@3.9.6:'
expect_ok "3.9.6" "a LOWER second packages entry does not win (#311)"

# --- A peer suffix is stripped. ---------------------------------------------
# pnpm writes `version: 3.9.6(typescript@5.x)` for packages with peers.
# Prettier has none today, so this is a ratchet rather than a live case -- and
# an unstripped suffix would be passed to `npx prettier@...` verbatim.
write_lock '3.9.6(typescript@5.4.0)' 'prettier@3.9.6:'
expect_ok "3.9.6" "a (peer) suffix is stripped"

# --- No lockfile. -----------------------------------------------------------
rm -f "$ROOT/pnpm-lock.yaml"
expect_refusal "not found" "no lockfile -> refuse"

# --- Lockfile with no prettier in the root importer. ------------------------
printf 'lockfileVersion: 9.0\nimporters:\n  .:\n    devDependencies:\n      react:\n        specifier: ^19\n        version: 19.0.0\npackages:\n  react@19.0.0:\n' \
  > "$ROOT/pnpm-lock.yaml"
expect_refusal "could not read prettier" "no entry -> refuse"

# --- A prettier in `packages:` but NOT in the importer must REFUSE. ---------
# Reading `packages:` was the old defect's home. A prettier that is only a
# transitive dependency is not what the workspace installs, so the honest answer
# is the refusal -- not that version.
printf 'lockfileVersion: 9.0\nimporters:\n  .:\n    devDependencies:\n      react:\n        specifier: ^19\n        version: 19.0.0\npackages:\n  prettier@2.8.8:\n' \
  > "$ROOT/pnpm-lock.yaml"
expect_refusal "could not read prettier" "a packages-only prettier is not the workspace's"

# --- STATE MUST NOT LEAK ACROSS IMPORTERS. ----------------------------------
# The case the first version of this gate missed, and the reviewer traced by
# reading the awk rather than running it: a root importer with dependencies but
# NO prettier, followed by an importer that has one. `in_deps` and `want` were
# set inside the root and never cleared on the importer-key line, so the six-
# space `prettier:` of the NEXT importer set `want` and the hook returned that
# version -- zero exit, indistinguishable from a correct read, and #168 restored
# through the fix for #168.
#
# The honest answer is the REFUSAL: the root workspace does not install prettier,
# so there is no version for `npx prettier@X` to be right about.
#
# Measured before the fix: returns 2.0.0. After: exit 1.
printf 'lockfileVersion: 9.0
importers:
  .:
    devDependencies:
      react:
        specifier: ^19
        version: 19.0.0
  apps/web:
    devDependencies:
      prettier:
        specifier: ^2.0.0
        version: 2.0.0
packages:
  react@19.0.0:
'   > "$ROOT/pnpm-lock.yaml"
expect_refusal "could not read prettier" "state does not leak into the NEXT importer"

# --- The root importer LAST still parses. -----------------------------------
# The inverse, because a reset that is too eager breaks this: an importer named
# `.` that is not first must still be read normally.
printf 'lockfileVersion: 9.0
importers:
  apps/web:
    devDependencies:
      prettier:
        specifier: ^2.0.0
        version: 2.0.0
  .:
    devDependencies:
      prettier:
        specifier: ^3.9.6
        version: 3.9.6
packages:
  prettier@3.9.6:
'   > "$ROOT/pnpm-lock.yaml"
expect_ok "3.9.6" "the root importer is read even when it is not first"

# --- Another importer's prettier must not win. ------------------------------
# `apps/web` can pin its own. The hook runs `npx prettier@X` from the repo root
# over the whole tree, so the ROOT importer is the one CI agrees with.
printf 'lockfileVersion: 9.0\nimporters:\n  .:\n    devDependencies:\n      prettier:\n        specifier: ^3.9.6\n        version: 3.9.6\n  apps/web:\n    devDependencies:\n      prettier:\n        specifier: ^2.0.0\n        version: 2.0.0\npackages:\n  prettier@3.9.6:\n' \
  > "$ROOT/pnpm-lock.yaml"
expect_ok "3.9.6" "another importer's prettier does not win"

# --- The hook must still WRITE. ---------------------------------------------
# Every case above passes `--print-version`, which returns before the exec. Drop
# `--write` from that line and the hook becomes a formatting no-op with this
# whole gate green (#318). Asserted against the source because running prettier
# needs the network.
# Anchored to the EXEC LINE, not to the file: `--write` also appears twice in
# the comments above it, so a file-wide grep passes with the flag deleted from
# the only line that runs. Measured -- that is exactly what the first version
# of this check did.
# THE WHOLE LINE, not just the flag, and there must be exactly ONE of it.
#
# `^exec npx .*--write` was satisfied by `exec npx -y "prettier@3.1.0" --write
# "$@"` -- a one-token mutation that reinstates #168 exactly, with every
# version case above still green, because they all return at
# `--print-version` before the exec. The derivation stayed correct, stayed
# tested, and nothing used it.
#
# The COUNT closes the other half: `grep -q` stops at its first match, so a
# shadowing `exec npx -y prettier --write "$@"` inserted ABOVE the pinned line
# leaves the strict pattern satisfied by the line below while the unpinned one
# is what actually runs. An unpinned `npx` is named in this hook's own header
# as how the divergence started.
exec_lines="$(grep -cE '^exec npx' "$HOOK")"
if [ "$exec_lines" != "1" ]; then
  echo "FAIL: expected exactly ONE '^exec npx' line in the hook, found $exec_lines."
  echo "      \`grep -q\` stops at the first match, so a second exec line above"
  echo "      the pinned one would run instead while this check still passed."
  exit 1
fi
if ! grep -qE '^exec npx -y "prettier@\$\{VERSION\}" --write "\$@"' "$HOOK"; then
  echo "FAIL: the exec line is no longer the pinned form"
  echo "      exec npx -y \"prettier@\${VERSION}\" --write \"\$@\""
  echo "      A literal version there reinstates #168 with every version case"
  echo "      above still green -- they all return at --print-version, which is"
  echo "      NOT the code path that runs prettier."
  exit 1
fi
echo "ok   [the exec line is pinned to \$VERSION and passes --write]"

# --- The version it reads must be the one CI resolves. ----------------------
# Read from the REAL lockfile, and compared against an INDEPENDENT read of the
# same file rather than a literal -- a literal here would be the fourth home for
# one fact, which is the defect this hook exists to end.
#
# The oracle is the root importer, NOT the old `packages:` + `head -1` grep.
# That grep was the defect: it is what this gate used to compare against, so it
# agreed with the bug and would have certified #311 forever.
REPO="$(cd "$(dirname "$HOOK")/.." && pwd)"
# Directly, for the same reason as `run()` above: the shebang decides.
real="$( cd "$REPO" && "$HOOK" --print-version )"

# THE ORACLE, and the merge that produced it is worth recording, because both
# sides of it were wrong in opposite directions.
#
# `main` compared against `grep -oE '^  prettier@...' | head -1` over the
# `packages:` section. That is INDEPENDENT of the hook's parser and it is the
# PRE-#311 derivation -- the exact logic #311 is about. It returns the LOWEST
# entry, so the moment a transitive dependency pins an older prettier it
# reports the wrong version and this gate goes red over a CORRECT hook.
#
# This branch replaced it with a verbatim copy of the hook's own awk. That
# removes the false positive and removes the oracle with it: two identical
# programs over one input cannot disagree, so the comparison was unfalsifiable
# on its stated subject and the comment calling it INDEPENDENT was false.
#
# A third form was proposed in review -- assert the resolved version exists as
# a key under `packages:` -- and it does not work. MEASURED, on a synthetic
# lockfile carrying `prettier@2.8.8` and `prettier@3.9.6`:
#
#     head -1 returns 2.8.8, and 2.8.8 IS a packages key.
#
# `head -1` selects FROM those keys, so its answer is always one of them by
# construction. The check passes on precisely the #311 answer it was proposed
# to catch. A correct diagnosis with a remedy that certifies the defect.
#
# So the oracle below reads the lockfile with a REAL YAML PARSER instead. That
# is a genuinely different mechanism -- a spec-compliant parser against a
# hand-rolled line matcher -- so the two sides can only agree if the awk is
# actually right, which is the property `CLAUDE.md` asks for. The awk copy is
# kept BELOW it as a frozen-copy drift detector, labelled as what it is.
#
# PyYAML is NOT a declared dependency; it arrives transitively and is present
# on the host and in the api container (6.0.3, measured). So its absence is
# "I could not look" -- exit 2, never a pass.
PYORACLE="$(cd "$REPO" && "$PYTHON" - "$REPO/pnpm-lock.yaml" <<'PYEOF' 2>&1
import sys
try:
    import yaml
except ImportError:
    print("NOYAML")
    raise SystemExit(0)
with open(sys.argv[1], encoding="utf-8") as fh:
    doc = yaml.safe_load(fh)
root = (doc.get("importers") or {}).get(".") or {}
for section in ("devDependencies", "dependencies"):
    entry = (root.get(section) or {}).get("prettier")
    if entry:
        # pnpm writes `1.2.3(peer@4.5.6)` for anything with peers.
        print(str(entry.get("version", "")).split("(")[0])
        break
else:
    print("ABSENT")
PYEOF
)"

if [ "$PYORACLE" = "NOYAML" ]; then
  echo "FAIL: no PyYAML for the independent lockfile read -- could not look" >&2
  exit 2
fi
if [ "$PYORACLE" = "ABSENT" ]; then
  echo "FAIL: the root importer declares no prettier -- could not look" >&2
  exit 2
fi

# The frozen copy of the hook's awk. NOT independent -- it is the same program
# -- and kept only as a drift detector between the hook and this file. When it
# disagrees, the question is WHICH IS RIGHT, decided against $PYORACLE above.
# Do not resolve a disagreement by pasting the hook's parser in here; that is
# the `check_plan_totals` shape, where the cheapest green reinstates the
# defect the gate exists to catch.
pinned="$(
  awk '
    /^importers:/            { in_imp = 1; next }
    in_imp && /^[^ ]/        { in_imp = 0 }
    in_imp && /^  [^ ]/      { in_root = ($0 ~ /^  \.:[[:space:]]*$/); next }
    in_root && /^    [^ ]/   { in_deps = ($0 ~ /^    (dev)?[Dd]ependencies:[[:space:]]*$/); next }
    in_deps && /^      [^ ]/ { want = ($0 ~ /^      prettier:[[:space:]]*$/); next }
    want && /^        version:/ { sub(/^        version:[[:space:]]*/, ""); sub(/\(.*/, ""); print; exit }
  ' "$REPO/pnpm-lock.yaml"
)"

if [ "$real" != "$PYORACLE" ]; then
  echo "FAIL: the hook resolved '$real'; a real YAML parser reads '$PYORACLE' from the root importer" >&2
  exit 1
fi
if [ "$pinned" != "$PYORACLE" ]; then
  echo "FAIL: the frozen awk copy in this gate reads '$pinned'; the YAML parser reads '$PYORACLE'." >&2
  echo "      The gate's copy has DRIFTED from the hook, or one of them is wrong." >&2
  echo "      Decide which against the YAML read. Do NOT paste the hook's parser in here." >&2
  exit 1
fi
echo "ok   [lockfile reads back as $real -- YAML parser agrees, frozen copy agrees]"

echo
echo "prettier-hook: version derived from the root importer, lower and transitive"
echo "entries ignored, peer suffix stripped, both refusals fire, --write intact."