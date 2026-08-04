# SHIELD by Kentro v2.0 - API runtime image.
#
# Per Master Spec §2 + AI Prompt §3.10 production note: least-privilege user,
# no sudo, no shell. The development container (.devcontainer/Dockerfile) is
# separate and runs as appuser with passwordless sudo.

FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        # WeasyPrint runtime (PDF rendering, used in Phase 3)
        libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
        libffi8 shared-mime-info fonts-liberation \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- Builder stage: install deps into a virtualenv we copy forward ----
FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install --prefix=/install ".[dev]"

# ---- Runtime stage ----
FROM base AS runtime
ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd --system --gid ${APP_GID} shield \
    && useradd --system --uid ${APP_UID} --gid ${APP_GID} --no-create-home --shell /usr/sbin/nologin shield \
    && install -d -o shield -g shield /app

COPY --from=builder /install /usr/local
COPY --chown=shield:shield . /app
USER shield

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
