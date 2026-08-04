#!/usr/bin/env bash
# SHIELD one-command demo reset (Sprint 6 T8; --demo overlay added Sprint 9 T8).
#
# Tears the stack down INCLUDING volumes (a clean slate), rebuilds, waits for the
# full-matrix /ready probe (T3) to go all-green, reseeds the coherent Atlas demo
# story (4 services + a synthesized Risk Register, all released + downloadable),
# waits for the web app to answer, and prints the URLs + logins.
#
#   bash scripts/demo-reset.sh            # base compose (web under `next dev`)
#   bash scripts/demo-reset.sh --demo     # + docker-compose.demo.yml (prod web)
#
# --demo overlays docker-compose.demo.yml on EVERY compose call, so the web
# service is the production Next.js standalone image (shield-web:demo) rather than
# the dev server — the same stack the hosted-demo CI job and the demo-journey e2e
# spec (SHIELD_DEMO_SMOKE=1) assert against. Plain invocation drives the base
# compose only.
#
# WARNING: `docker compose down -v` DELETES all demo data (Postgres, MinIO,
# Redis, Keycloak). That is the point of a reset — do not run against data you
# want to keep. Live AI is optional: put ANTHROPIC_API_KEY in .env first.
set -euo pipefail

# Docker CLI is not on the Git Bash PATH by default on Windows dev machines.
export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# --- Parse flags -------------------------------------------------------------
DEMO=false
for arg in "$@"; do
  case "$arg" in
    --demo) DEMO=true ;;
    -h | --help)
      echo "Usage: bash scripts/demo-reset.sh [--demo]"
      echo "  --demo   overlay docker-compose.demo.yml (production web build)"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg (supported: --demo)" >&2
      exit 2
      ;;
  esac
done

# Compose file selection. Base uses docker-compose.yml only — identical to the
# bare `docker compose` default (there is no override file in this repo); --demo
# appends the hosted-demo override so every call targets the production web image.
COMPOSE_ARGS=(-f docker-compose.yml)
if [ "$DEMO" = true ]; then
  COMPOSE_ARGS+=(-f docker-compose.demo.yml)
fi
dc() { docker compose "${COMPOSE_ARGS[@]}" "$@"; }

# Resolve the web host port (WEB_PORT env > repo-root .env > 3000) so the web
# readiness wait probes the port the stack actually publishes on — the same
# resolution order e2e/helpers/baseUrl.ts uses. The api mapping is fixed at 8000.
web_port="${WEB_PORT:-}"
if [ -z "$web_port" ] && [ -f .env ]; then
  web_port="$(sed -n 's/^[[:space:]]*WEB_PORT[[:space:]]*=[[:space:]]*\([0-9][0-9]*\)[[:space:]]*$/\1/p' .env | head -1)"
fi
web_port="${web_port:-3000}"

step() { printf '\n>> %s\n' "$1"; }

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon not running. Start Docker, then re-run." >&2
  exit 1
fi

mode="base compose (web: next dev)"
[ "$DEMO" = true ] && mode="hosted-demo overlay (web: production standalone build)"

echo "============================================================"
echo "  SHIELD by Kentro - resetting the demo stack (down -v)"
echo "  Mode: $mode"
echo "============================================================"

# 1) Full teardown INCLUDING volumes (clean slate).
step "Tearing down (docker compose down -v)..."
dc down -v

# 2) Rebuild + start the full stack.
step "Building + starting containers (docker compose up -d --build)..."
dc up -d --build

# 3) Wait for the FULL-MATRIX readiness probe to go all-green (T3): every
#    required dependency (db, redis, minio) must report ok.
step "Waiting for /ready (full dependency matrix) to be all-green..."
ready=false
offenders=""
for _ in $(seq 1 80); do
  body="$(curl -fsS --max-time 3 http://localhost:8000/ready 2>/dev/null || true)"
  if [ -n "$body" ]; then
    case "$body" in
      *'"ready":true'*)
        ready=true
        break
        ;;
    esac
    # Best-effort offender extraction for the failure message.
    offenders="$(printf '%s' "$body" | sed -n 's/.*"offenders":\[\([^]]*\)\].*/\1/p')"
  fi
  sleep 3
done
if [ "$ready" != true ]; then
  echo "Stack not ready in time. Offenders: ${offenders}" >&2
  echo "---- docker compose logs api ----" >&2
  dc logs api >&2 || true
  exit 1
fi
echo "All dependencies ready."

# 4) Seed the coherent Atlas demo (idempotent, but the DB is fresh here).
step "Seeding the Atlas demo story..."
dc exec -T api python scripts/seed_demo.py

# 5) Wait for the web app to answer — FAIL LOUDLY on timeout (Sprint 9 T8, Codex
#    finding): the old poll gave up after 120s and printed the success banner
#    anyway, so a failed prod-image build looked like a clean reset until
#    Playwright died opaquely. A non-zero exit + a web log dump surfaces it here.
step "Waiting for the web app on http://localhost:${web_port} ..."
web_ready=false
for _ in $(seq 1 40); do
  if curl -fsS --max-time 3 "http://localhost:${web_port}" >/dev/null 2>&1; then
    web_ready=true
    break
  fi
  sleep 3
done
if [ "$web_ready" != true ]; then
  echo "Web app never became reachable on http://localhost:${web_port} within 120s." >&2
  echo "A failed web build/start would otherwise masquerade as a successful reset." >&2
  echo "---- docker compose logs web ----" >&2
  dc logs web >&2 || true
  exit 1
fi
echo "Web app reachable."

# 6) Print the banner.
cat <<EOF

============================================================
  SHIELD by Kentro - demo reset complete
============================================================
  Web app:     http://localhost:${web_port}
  API + docs:  http://localhost:8000/docs
  Readiness:   http://localhost:8000/ready
  MailHog:     http://localhost:8025

  ADMIN  login: admin@kentro.example   /  DemoPass!2026
  CLIENT login: client@atlas.example   /  DemoPass!2026
============================================================
  Demo story: 4 services + Risk Register, released + downloadable
  See it on:  /home and /documents (client) - reports download
  Live AI (optional): put ANTHROPIC_API_KEY in .env, then re-run.

EOF
