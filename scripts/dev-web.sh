#!/usr/bin/env bash
# Start the Next.js dev server, installing dependencies the way the compose
# service does -- by CALLING the shared guard, never by reimplementing it.
#
# Usage, from inside a dev container that has the repo mounted:
#     bash scripts/dev-web.sh
#
# ## What this used to do, and why it was worse than nothing (#318)
#
#     if [[ ! -d node_modules ]]; then
#         pnpm install
#     fi
#
# Two defects, and the second is the one that costs:
#
#   * `node_modules` is a NAMED VOLUME, so it exists from the first boot
#     onward. The guard was therefore false forever after, and a lockfile
#     change installed nothing. That is #226 exactly -- keyed on a directory
#     EXISTING rather than on the dependencies being CURRENT -- in a script
#     that survived the fix for it.
#   * the install had no `--frozen-lockfile`, so on the one run it did fire it
#     resolved `package.json` RANGES. CI runs `pnpm install --frozen-lockfile`
#     and installs what the lockfile pins. The two could differ at any time
#     with nothing saying so, which is the silent drift `web-install-if-stale.sh`
#     was written to end.
#
# `README.md` documents this script as a Quick-start path, so the guard that
# decides whether a security patch is applied ran on neither documented route.
#
# ## Why it CALLS rather than copies
#
# `CLAUDE.md`: "uses the same X as the Y path" is a claim to enforce by CALLING
# X, never by reimplementing it -- recorded after a docstring claimed to use
# "the SAME redactor the egress path uses" while calling one rule out of ten.
# This file was the same shape: the compose `command:` runs
# `web-install-if-stale.sh`, and this ran a weaker copy of the idea.
#
# `SHIELD_WEB_APP_DIR` exists on that script for exactly this: it defaults to
# `/app` for the container and is pointed at the repo root here, so ONE
# implementation serves both and they cannot drift.
set -euo pipefail

cd "$(dirname "$0")/.."

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


if ! command -v pnpm >/dev/null 2>&1; then
    corepack enable
    corepack prepare pnpm@9.12.0 --activate
fi

GUARD="scripts/web-install-if-stale.sh"
if [ ! -f "$GUARD" ]; then
    # FAIL CLOSED. Falling through to `pnpm -F web dev` here would start a dev
    # server against whatever is in the volume, which is the behaviour the
    # guard exists to stop -- and it would do it silently.
    echo "[dev-web] $GUARD not found, and this script will not install without it." >&2
    echo "[dev-web]   It is the one place that knows to install with" >&2
    echo "[dev-web]   --frozen-lockfile and to key on the lockfile's hash rather" >&2
    echo "[dev-web]   than on node_modules existing (#226). Running an unguarded" >&2
    echo "[dev-web]   install instead is the defect, not a fallback." >&2
    exit 1
fi

# The guard installs, skips or REFUSES, and prints which and why. Its non-zero
# exit is fatal here for the same reason it is fatal in the compose command: a
# failed install followed by a dev server is a half-success, and this repo does
# not have those.
SHIELD_WEB_APP_DIR="$PWD" sh "$GUARD"

echo "[dev-web] Starting Next.js on port 3000..."
exec pnpm -F web dev
