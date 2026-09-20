#!/usr/bin/env bash
# Start the Next.js dev server inside the `web` container.
# Usage (from inside the `web` container or via `docker compose exec web ...`):
#     bash scripts/dev-web.sh
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

if [[ ! -d node_modules ]]; then
    echo "[dev-web] First run - installing dependencies (this can take a few minutes)..."
    pnpm install
fi

echo "[dev-web] Starting Next.js on port 3000..."
exec pnpm -F web dev
