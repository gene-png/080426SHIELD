#!/usr/bin/env bash
# Runs every time the dev container starts.
# Cheap permission-drift correction only - heavy work belongs in post-create.sh.
set -euo pipefail

REPO="${REPO:-/workspaces/SHIELDV2-051826v2}"
USER_NAME="$(id -un)"
USER_GROUP="$(id -gn)"

if [[ -d "${REPO}" ]]; then
    sudo chown -R "${USER_NAME}:${USER_GROUP}" "${REPO}" 2>/dev/null || true
fi

for d in ~/.npm ~/.cache; do
    sudo chown -R "${USER_NAME}:${USER_GROUP}" "${d}" 2>/dev/null || true
done

git config --global --add safe.directory "${REPO}" 2>/dev/null || true

echo "[post-start] Ready."
