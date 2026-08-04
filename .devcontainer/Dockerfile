# SHIELD by Kentro v2.0 - Development container image.
#
# Per AI Prompt §3.10 / §3.11: this image is for DEVELOPMENT only. It runs as
# a non-root `appuser` with passwordless sudo so the autonomous build agent
# never stalls on a permission prompt. Production runtime images live under
# infra/docker/ and follow least-privilege (no sudo, no shell user).

FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

ARG USERNAME=appuser
ARG USER_UID=1000
ARG USER_GID=$USER_UID

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    NODE_VERSION=20 \
    PNPM_VERSION=9.12.0

# OS deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        sudo curl ca-certificates gnupg lsb-release git make \
        build-essential libpq-dev \
        # WeasyPrint deps (PDF rendering)
        libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
        libffi-dev shared-mime-info fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# appuser may not exist (the python image already creates `vscode`); reuse if uid matches, else add.
RUN if id -u $USER_UID >/dev/null 2>&1; then \
        existing=$(getent passwd $USER_UID | cut -d: -f1); \
        echo "Re-using existing user $existing for uid $USER_UID"; \
        usermod -l $USERNAME -d /home/$USERNAME -m $existing || true; \
        groupmod -n $USERNAME $(id -gn $existing) || true; \
    else \
        groupadd --gid $USER_GID $USERNAME && \
        useradd --uid $USER_UID --gid $USER_GID -m -s /bin/bash $USERNAME; \
    fi \
    && echo "$USERNAME ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Node + pnpm
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && corepack enable \
    && corepack prepare pnpm@${PNPM_VERSION} --activate

# Poetry + Python tooling
RUN pip install --no-cache-dir poetry==1.8.3 ruff black mypy bandit pre-commit

# Docker CLI + compose plugin (devcontainer mounts host socket; no daemon inside)
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

USER $USERNAME
WORKDIR /workspaces/SHIELDV2-051826v2
