#!/usr/bin/env bash
# Start the Next.js dev server inside the `web` container.
# Usage (from inside the `web` container or via `docker compose exec web ...`):
#     bash scripts/dev-web.sh
set -euo pipefail

cd "$(dirname "$0")/.."

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
