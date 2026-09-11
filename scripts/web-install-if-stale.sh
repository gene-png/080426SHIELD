#!/bin/sh
# Install web dependencies when the LOCKFILE has changed, not when a binary is
# missing (#226).
#
# ## The defect
#
# `docker-compose.yml`'s web service guarded the install on the next binary
# EXISTING:
#
#     [ -f apps/web/node_modules/next/dist/bin/next ] || pnpm install;
#
# `node_modules` lives in named volumes, so once populated no later `up`,
# `--force-recreate` or `restart` ever installed anything again. A remediation
# procedure therefore reported success while leaving a vulnerable binary
# running: on the branch shipping fixes for two unauthenticated RCE advisories,
# `package.json` and the lockfile both read 15.5.24 and the container reported
# **15.5.23**. The confirmation step -- the one line whose job is to say whether
# you are still unpatched -- is where it landed.
#
# ## A second defect, found while fixing the first
#
# **The lockfile was never mounted into the container.** Measured 2026-09-11
# against the running stack: `/app` held `package.json`, `pnpm-workspace.yaml`,
# `apps`, `packages` and `node_modules`, and no `pnpm-lock.yaml`. So the
# container's `pnpm install` resolved from package.json RANGES while CI runs
# `pnpm install --frozen-lockfile` and installs what the lockfile pins. The two
# could differ at any time and nothing would say so.
#
# That is also why the obvious version of this fix is impossible: you cannot
# key an install on a lockfile the container cannot see. The compose file now
# mounts it read-only, and this script installs with `--frozen-lockfile` so the
# container and CI resolve the same tree.
#
# ## What it keys on, and why a stamp rather than a comparison
#
# A hash of the lockfile, written into the node_modules volume ONLY after an
# install that succeeded. The stamp lives with the thing it describes, so it
# cannot disagree with the volume it stamps -- a stamp kept anywhere else is a
# synchronisation, and `CLAUDE.md` prefers a derivation to one of those.
#
# Writing it only on success is the other half. `CLAUDE.md`: a success record
# must be written where the success is. A stamp written before the install
# would say "these dependencies are current" about a run that failed, and the
# next boot would skip the retry.
#
# ## Every branch that exits 0 without installing, enumerated first
#
#   * the stamp matches the lockfile's hash AND the binary is present -- the
#     ordinary case, and the only one.
#
# Everything else installs or refuses:
#
#   * no stamp -- an existing volume nobody stamped. We do not know what is in
#     it, and "probably fine" is not an answer this repo accepts about a
#     dependency tree. Install.
#   * stamp differs -- the lockfile moved. Install. This is #226.
#   * binary missing -- a fresh or damaged volume. Install.
#   * lockfile missing -- REFUSE, exit 1. It means the mount was dropped, and
#     falling back to a range-resolved install is the silent drift this script
#     exists to end. Failing loudly costs a developer one error message;
#     failing open costs the thing #226 measured.
#   * install fails -- REFUSE, exit 1, and leave the stamp alone so the next
#     boot retries. The old command ran `pnpm install; exec pnpm -F web dev`,
#     so a failed install still started the dev server against whatever was in
#     the volume. `restart: unless-stopped` turns the refusal into a retry
#     loop with the error visible in `docker compose logs web`, which is the
#     behaviour you want from a step that cannot be allowed to half-succeed.
#
# `--check` prints the decision and the reason without acting, so both states
# can be exercised. Used by `tests/gates/web_install_guard.sh`.

set -eu

APP="${SHIELD_WEB_APP_DIR:-/app}"
LOCK="$APP/pnpm-lock.yaml"
BIN="$APP/apps/web/node_modules/next/dist/bin/next"
STAMP="$APP/node_modules/.shield-installed-lock"

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

decide() {
  if [ ! -f "$LOCK" ]; then
    echo "refuse: $LOCK is not present."
    echo "  The web container mounts it read-only so the install resolves what"
    echo "  the lockfile pins, exactly as CI does. Without it \`pnpm install\`"
    echo "  resolves package.json RANGES instead, and the container can run a"
    echo "  different tree from the one CI tested with nothing saying so."
    echo "  Restore the \`./pnpm-lock.yaml:/app/pnpm-lock.yaml:ro\` mount."
    return 2
  fi

  want="$(sha256sum "$LOCK" | cut -d' ' -f1)"
  have=""
  [ -f "$STAMP" ] && have="$(cat "$STAMP")"

  if [ ! -f "$BIN" ]; then
    echo "install: $BIN is missing (fresh or damaged volume)."
    return 1
  fi
  if [ -z "$have" ]; then
    echo "install: no stamp in the volume, so nothing records what is in it."
    return 1
  fi
  if [ "$want" != "$have" ]; then
    echo "install: the lockfile changed."
    echo "  lockfile : $want"
    echo "  installed: $have"
    return 1
  fi
  echo "skip: the installed tree matches the lockfile ($want)."
  return 0
}

set +e
reason="$(decide)"
verdict=$?
set -e
echo "$reason"

[ "$CHECK_ONLY" -eq 1 ] && exit "$verdict"

case "$verdict" in
  0) exit 0 ;;
  2) exit 1 ;;
esac

cd "$APP"
# `--frozen-lockfile` is what makes the container agree with CI, and it also
# turns a package.json that has drifted from the lockfile into a loud failure
# rather than a silent re-resolve.
pnpm install --frozen-lockfile
# ONLY here. See the header: a stamp written any earlier claims currency for a
# run that may not have finished.
sha256sum "$LOCK" | cut -d' ' -f1 > "$STAMP"
echo "installed, and stamped $(cat "$STAMP")"
