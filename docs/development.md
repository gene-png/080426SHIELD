# Development guide

> Zero-to-loop machine setup lives in `ONBOARDING.md`; durable environment
> gotchas in `CLAUDE.md`. This file is the day-to-day command reference.

## Prerequisites

- Docker Desktop (or Docker Engine) with Compose v2.
- Node LTS on the host (for the host-run Playwright e2e suite).
- A GitHub account with push access to `github.com/gene-png/SHIELD062626`.

## First-time setup

1. `cp .env.example .env`, then edit `.env`:
   - `ANTHROPIC_API_KEY` only if you want live LLM calls — the default
     `SHIELD_LLM_MODE=fixture` is fully offline (DECISIONS D-017).
   - Generate `NEXTAUTH_SECRET` with `openssl rand -hex 32`.
   - If `:3000` is taken on your machine, set `WEB_PORT` — the e2e suite
     resolves it via `e2e/helpers/baseUrl.ts`.
2. `docker compose up -d` (db, redis, minio, keycloak, mailhog, api, web —
   there is no worker service).
3. Seed the demo: `docker compose exec -T api python scripts/seed_demo.py`
   (idempotent). Demo logins: `admin@kentro.example` / `client@atlas.example`,
   password `DemoPass!2026`.
4. `cd e2e && npm install` for the host-run Playwright harness.

(The `.devcontainer/` config is available for VS Code Dev Containers, but the
current two-developer workflow runs plain Docker Compose on the host.)

## Daily workflow

```bash
# Watch api logs
docker compose logs -f api

# Run the real test matrix (the six sprint gates; CI runs the same + bandit/gitleaks)
docker compose exec -T api pytest -m unit -q
docker compose exec -T web sh -lc "cd /app && pnpm -F web exec tsc --noEmit"
docker compose exec -T web sh -lc "cd /app && pnpm -F web test"
docker compose exec -T web sh -lc "cd /app && pnpm -F web lint"
docker compose exec -T api sh -lc "cd /app && ruff check --no-cache . && black --check ."
npx -y prettier@3.9.5 --check "**/*.{ts,tsx,js,jsx,json,md,yml,yaml}"
cd e2e && npx playwright test          # host-run, stack must be up + seeded
```

There is no `pytest -m integration` suite (the marker is declared but unused);
web unit tests run in-container via vitest (`pnpm -F web test`, a loop gate
since Sprint 5) and the Playwright suite covers the integrated stack.

Environment gotchas that will bite you (full list in `CLAUDE.md`):

- On Windows, next-dev hot reload does **not** fire through the bind mount —
  after any `apps/web` edit run `docker compose up -d --force-recreate web`
  before e2e.
- A **new** python module under `app/` needs `docker compose restart api`
  (uvicorn --reload can miss new files).
- After editing `apps/web/package.json`, reinstall inside the web container.

## Commit discipline

1. Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`,
   `refactor:`, `ci:`); body explains the why.
2. Never commit directly to `main` — branch + PR (see `CLAUDE.md`
   collaboration rules).
3. Pre-commit hooks must pass (no `--no-verify`); prettier is CI-enforced
   repo-wide.

## Adding a route

1. Create the SQLAlchemy model under `apps/api/app/models/`.
2. Write the Alembic migration under `apps/api/alembic/versions/` — keep it
   SQLite-safe (`batch_alter_table`; tests run SQLite, prod runs Postgres) and
   make new persisted fields additive/optional (the C0 pattern).
3. Add the Pydantic schema under `apps/api/app/schemas/`.
4. Add the route under `apps/api/app/routes/`; resolve the tenant with the
   `current_client` dependency and check id ownership via `app/tenant.py`
   helpers (404 on mismatch). Errors use the typed `{reason, message}`
   envelope (D-016).
5. Write the audit-log call (`app.audit.spine.audit()`) inside every
   state-changing route.
6. Unit tests under `apps/api/tests/unit/` — test first (TDD).
7. If the web needs it: add a `/api/proxy/*` route handler and client call
   under `apps/web/src/lib/`. (Shared TS types in `packages/shared-types` are
   maintained by hand — there is no codegen step.)

## Adding a page

1. Add the route under `apps/web/src/app/`.
2. Compose from `packages/design-system/` primitives (Round 6 design
   language).
3. Write/extend a Playwright spec under `e2e/smoke/`; resolve seeded ids via
   `e2e/helpers/ids.ts`, never hardcode UUIDs.
4. Accessibility: the runtime axe sweep (`s16-axe.spec.ts`) must stay green;
   static `jsx-a11y` rules run in the eslint CI step.

## Debugging

- API docs: http://localhost:8000/docs.
- DB shell: `docker compose exec db psql -U shield -d shield`.
- Redis shell: `docker compose exec redis redis-cli` (rate-limit keys are
  `rl:*`).
- MinIO console: http://localhost:9001; MailHog: http://localhost:8025.
