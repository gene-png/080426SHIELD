# Production Docker images

- **API:** `apps/api/Dockerfile` (FastAPI + uvicorn).
- **Web:** `apps/web/Dockerfile` (Next.js standalone output). Build from the repo
  root so the pnpm workspace + `packages/*` are in context:
  `docker build -f apps/web/Dockerfile -t shield-web .`

`docker-compose.yml` runs the dev stack (hot-reload, dev command). AI runs are
synchronous, so there is no worker/queue service (see DECISIONS.md D-015).

Validate image builds in a Linux Docker environment — Next's standalone copy
uses symlinks that fail on Windows (EPERM) but work in Docker/Linux.
