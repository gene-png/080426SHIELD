# SHIELD e2e — Playwright smoke harness

Host-run Playwright suite that drives the composed Docker stack's web app. The
specs share **one seeded database** and run **serialized** (`fullyParallel:
false`, `workers: 1`) so DB-mutating flows stay deterministic. This README is
the canonical fresh-stack bring-up sequence and the script the CI `e2e` job
(`.github/workflows/ci.yml`, added in Sprint 2 T3) reproduces.

## Layout

- `smoke/` — the numbered smoke specs (`s0`–`s21` today; sections mirror
  `SMOKE_TEST.md`).
- `helpers/baseUrl.ts` — resolves the web base URL (see [Ports](#ports)).
- `helpers/ids.ts` — resolves seeded Atlas client/service ids **at runtime**
  (S2 T1). Never hardcode seeded UUIDs in a spec; use these helpers.
- `helpers/auth.ts` — login helpers for the admin/client personas.
- `playwright.config.ts` — chromium only, 90 s per-test timeout (Next dev
  cold-compile headroom), `retries: 1` under `CI`.

## Prerequisites

- Docker Desktop running. The Docker CLI is **not** on Git Bash PATH by
  default — export it first in every shell:
  `export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"`.
- Node.js + the e2e deps installed on the **host** (Playwright runs on the
  host, not in a container): `cd e2e && npm ci && npx playwright install --with-deps chromium`.

## Canonical fresh-stack bring-up

Run from the repo root. **`down -v` destroys all local demo data** (Postgres,
MinIO, Keycloak volumes) — this is the point: it reproduces the pristine
database CI creates.

```bash
export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"

# 1. Tear down and recreate the stack (destroys volumes)
docker compose down -v
docker compose up -d

# 2. Wait for the API to be healthy (Keycloak cold start is the slow gate;
#    the api container only serves once migrations + deps are ready)
until curl -sf http://localhost:8000/health >/dev/null; do sleep 3; done

# 3. Seed the demo tenant (idempotent; applies migrations first)
docker compose exec -T api python scripts/seed_demo.py

# 4. Recreate web so it comes up clean against the freshly seeded DB.
#    REQUIRED on Windows: next-dev hot-reload does not fire through the bind
#    mount, so any prior state / source edit needs a force-recreate.
docker compose up -d --force-recreate web
until curl -sf http://localhost:${WEB_PORT:-3000} >/dev/null; do sleep 3; done

# 5. Run the full suite (~17 min)
cd e2e && npx playwright test
```

Sign-in credentials created by the seed:

- admin (Kentro consultant): `admin@kentro.example` / `DemoPass!2026`
- client (Atlas tenant): `client@atlas.example` / `DemoPass!2026`

Specs that create their own users must use unique timestamped emails.

## Ports

`helpers/baseUrl.ts` resolves the web base URL in priority order:

1. `E2E_BASE_URL` env var (explicit override)
2. `WEB_PORT=<n>` in the repo-root `.env` (the same machine-local file
   docker-compose reads to publish web on a non-default host port)
3. `http://localhost:3000` (canonical / CI default)

CI composes the stack with **no `.env`**, so it stays on `:3000`. A dev box
whose `:3000` is taken sets `WEB_PORT=` (and a matching `NEXTAUTH_URL=`) in
`.env`; the helper then picks it up automatically — never hardcode a port in a
spec.

## Running

```bash
cd e2e
npx playwright test                       # full suite
npx playwright test smoke/s7-csf-playbook.spec.ts   # one file
npx playwright test -g "renders"          # by title substring
npx playwright show-report                # open the last HTML report
```

Reports land in `playwright-report/`; traces/screenshots for failures in
`test-results/` (both gitignored).

## Notes & gotchas

- **Serialized, shared DB.** Specs run in array order on one worker. A spec
  that mutates state must leave the DB usable for the next; prefer
  find-or-create over assuming absence.
- **Runtime ids, not hardcoded UUIDs.** After S2 T1, resolve seeded Atlas ids
  via `helpers/ids.ts` (`atlasClientId`, `atlasServiceId`). A re-seeded DB
  mints new UUIDs.
- **Force-recreate web after any `apps/web` edit** before re-running specs —
  the bind-mount hot-reload does not fire on Windows.
- **Known flake:** Next dev cold-compile timeouts under back-to-back load. A
  re-run clears it; don't "fix" a spec for it (`retries: 1` absorbs it in CI).
- **AI is fixture mode** (offline, deterministic — D-017), so Run-AI flows are
  reproducible per assessment.
