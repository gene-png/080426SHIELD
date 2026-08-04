#!/usr/bin/env bash
# Runs ONCE after the dev container is first created.
# Per AI Prompt §3.11 - pre-flight permissions setup.
set -euo pipefail

REPO="${REPO:-/workspaces/SHIELDV2-051826v2}"
USER_NAME="$(id -un)"
USER_GROUP="$(id -gn)"

echo "[post-create] Repo path: ${REPO}"
echo "[post-create] User: ${USER_NAME}:${USER_GROUP}"

# Ownership
if [[ -d "${REPO}" ]]; then
    sudo chown -R "${USER_NAME}:${USER_GROUP}" "${REPO}" || true
    sudo chmod -R u+rwX "${REPO}" || true
fi

# Caches commonly owned by root after first install
for d in ~/.npm ~/.cache ~/.local ~/.config ~/.cache/pnpm ~/.cache/pip ~/.cache/poetry; do
    sudo chown -R "${USER_NAME}:${USER_GROUP}" "${d}" 2>/dev/null || true
done

# Trust this repo path inside the container
git config --global --add safe.directory "${REPO}" || true

# .env from example if missing
if [[ -f "${REPO}/.env.example" && ! -f "${REPO}/.env" ]]; then
    cp "${REPO}/.env.example" "${REPO}/.env"
    echo "[post-create] Created .env from .env.example. Edit it before running the stack."
fi

# Install JS deps if package.json exists
if [[ -f "${REPO}/package.json" ]]; then
    (cd "${REPO}" && pnpm install --prefer-offline) || echo "[post-create] pnpm install skipped or failed (non-fatal at this stage)"
fi

# Install pre-commit hooks
if [[ -f "${REPO}/.pre-commit-config.yaml" ]]; then
    (cd "${REPO}" && pre-commit install) || echo "[post-create] pre-commit install skipped (non-fatal)"
fi

echo "[post-create] Done."
