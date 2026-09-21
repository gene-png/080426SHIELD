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

# Install JS deps THROUGH THE SHARED GUARD, never with a second install of our
# own (#318).
#
# This ran `pnpm install --prefer-offline`, with its failure swallowed by
# `|| echo "... non-fatal"`. Two defects, both of which this repo has already
# paid for elsewhere:
#
#   * no `--frozen-lockfile`, so it resolved `package.json` RANGES. CI runs
#     `pnpm install --frozen-lockfile` and installs what the LOCKFILE pins, so
#     the container could run a different tree from the one CI tested with
#     nothing saying so -- the silent drift `web-install-if-stale.sh` exists to
#     end. `devcontainer.json` runs this file as `postCreateCommand`, so
#     Quick-start Option A took the unguarded path before `dev-web.sh` was ever
#     reached: "both documented Quick-start paths now go through the guard" was
#     false while this line stood.
#   * the failure was SWALLOWED. A container that comes up with a failed
#     install and an encouraging message is the silent-success shape, and the
#     next thing the developer sees is a dev server running against whatever
#     happens to be in the volume.
#
# It CALLS the guard rather than copying it, for the reason `CLAUDE.md` gives:
# "uses the same X as the Y path" is a claim to enforce by calling X.
# `SHIELD_WEB_APP_DIR` is on that script for exactly this, and `dev-web.sh`
# invokes it the same way.
#
# NOT `|| true`. A refusal fails container creation, loudly, which is the right
# trade: the alternative is a container whose dependency tree nobody can
# describe.
if [[ -f "${REPO}/package.json" ]]; then
    if ! command -v pnpm >/dev/null 2>&1; then
        corepack enable
        corepack prepare pnpm@9.12.0 --activate
    fi
    GUARD="${REPO}/scripts/web-install-if-stale.sh"
    if [[ ! -f "${GUARD}" ]]; then
        echo "[post-create] ${GUARD} not found, and this script will not install without it." >&2
        echo "[post-create]   It is the one place that knows to install with" >&2
        echo "[post-create]   --frozen-lockfile and to key on the lockfile's hash rather" >&2
        echo "[post-create]   than on node_modules existing (#226). An unguarded install" >&2
        echo "[post-create]   here is the defect, not a fallback." >&2
        exit 1
    fi
    SHIELD_WEB_APP_DIR="${REPO}" sh "${GUARD}"
fi

# Install pre-commit hooks
if [[ -f "${REPO}/.pre-commit-config.yaml" ]]; then
    (cd "${REPO}" && pre-commit install) || echo "[post-create] pre-commit install skipped (non-fatal)"
fi

echo "[post-create] Done."
