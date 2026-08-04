# Production image for the SHIELD web app (Next.js standalone output).
#
# Build from the REPO ROOT (the pnpm workspace + packages/* are needed):
#   docker build -f apps/web/Dockerfile -t shield-web .
# or via the demo override:
#   docker compose -f docker-compose.yml -f docker-compose.demo.yml build web
#
# A root .dockerignore keeps the host's node_modules (pnpm's symlink farm) and
# .next out of the build context, so the install below produces a clean,
# correct workspace symlink tree inside the image. Without it BuildKit rejects
# the dangling host symlinks and `next` is missing from apps/web/node_modules.
#
# Note: validate this build in a Linux Docker environment — Next's standalone
# copy step uses symlinks that fail on Windows (EPERM) but work in Docker.

FROM node:22-bookworm-slim AS build
RUN corepack enable
WORKDIR /repo
# Source only (node_modules/.next excluded via .dockerignore). Install the whole
# workspace so pnpm links both the root store and the per-package node_modules
# (apps/web/node_modules, packages/*/node_modules) the build needs.
COPY . .
RUN pnpm install --frozen-lockfile
RUN pnpm -F web build

FROM node:22-bookworm-slim AS run
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
# Standalone bundle + static assets. (No apps/web/public dir today; add a COPY
# for it here if one is introduced.)
COPY --from=build /repo/apps/web/.next/standalone ./
COPY --from=build /repo/apps/web/.next/static ./apps/web/.next/static
USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
