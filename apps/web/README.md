# apps/web

Next.js 14 (App Router) frontend for SHIELD by Kentro v2.0. TypeScript strict, Tailwind for styling, NextAuth for sessions, shadcn primitives copied into `packages/design-system` (stage 6).

## Run the web dev server

```bash
docker compose up -d web
docker compose logs -f web    # the install guard, then Next.js boot
```

The server starts on http://localhost:3000.

### Two commands that used to be here, and why neither is

```bash
docker compose exec web bash scripts/dev-web.sh   # CANNOT RUN
```

The `web` service mounts individual paths — `apps/web`, `packages`,
`package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml`, and the install guard
as a single file at `/app/web-install-if-stale.sh`. It does **not** mount
`./scripts`. Measured 2026-09-20 against the running stack:
`ls /app/scripts` → `No such file or directory`.

```bash
pnpm install    # BYPASSES THE GUARD
pnpm dev
```

No `--frozen-lockfile`, so it resolves `package.json` RANGES while CI runs
`pnpm install --frozen-lockfile` and installs what the lockfile pins. The two
can differ at any time with nothing saying so — the drift
`scripts/web-install-if-stale.sh` exists to end (#226). `docker compose up -d
web` runs the service's own `command:`, which runs that guard, so the
Quick-start and CI install the same tree by construction.

If you are already inside a dev container with the repo mounted, use
`bash scripts/dev-web.sh` — it calls the same guard rather than installing on
its own.

## Environment variables

Loaded from the repo-root `.env` (mounted into the web container). The keys this app reads:

| Var               | Purpose                                                                                 |
| ----------------- | --------------------------------------------------------------------------------------- |
| `NEXTAUTH_URL`    | Canonical public URL (e.g. `http://localhost:3000`)                                     |
| `NEXTAUTH_SECRET` | Session signing secret (generate with `openssl rand -hex 32`)                           |
| `API_BASE_URL`    | Server-side base URL for the FastAPI backend (default `http://api:8000` inside compose) |

## Auth (v1)

NextAuth Credentials provider posts `email` + `password` to `POST /auth/login` on the API and stores the resulting access + refresh tokens in the session. The Bearer token is attached to every server-side fetch helper in `src/lib/api.ts`.

Federation to Keycloak in v1.x means swapping the provider for `KeycloakProvider` with the same audience claim. No schema migration; the API validates the same JWT shape either way.

## Tests

```bash
pnpm typecheck   # tsc --noEmit
pnpm lint        # next lint
```

End-to-end + accessibility tests land alongside Phase 1 stage 8 (CI green) and `e2e/`.
