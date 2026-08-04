# apps/web

Next.js 14 (App Router) frontend for SHIELD by Kentro v2.0. TypeScript strict, Tailwind for styling, NextAuth for sessions, shadcn primitives copied into `packages/design-system` (stage 6).

## Run inside the dev container

```bash
docker compose exec web bash scripts/dev-web.sh
```

Or directly with pnpm if you're already in the `web` container:

```bash
pnpm install
pnpm dev
```

The server starts on http://localhost:3000.

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
