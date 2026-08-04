# Operations

> Honest split: **"Running today"** is what actually exists (the Docker
> Compose dev/demo stack). **"Planned production posture"** is direction, not
> implemented detail — nothing in that section exists in this repo yet.

## Running today (dev/demo stack)

`docker-compose.yml` at the repo root runs the whole platform:

| Service                 | Image / build                 | Notes                                                                                                                                                  |
| ----------------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| db                      | postgres:16                   | Alembic migrations at `api` start                                                                                                                      |
| redis                   | redis:7                       | **Rate limiting only** (auth + run-AI, `app/security/rate_limit.py`); fails open with a loud warning on outage. No queue, no Celery                    |
| minio (+ createbuckets) | minio                         | S3-compatible artifact/deliverable storage; console `:9001`                                                                                            |
| keycloak                | keycloak 25                   | Realm imported from `infra/keycloak/`; scaffolding for future OIDC — the active login path is SHIELD-issued JWT via Auth.js v5 (next-auth) Credentials |
| mailhog                 | mailhog                       | SMTP capture UI `:8025`                                                                                                                                |
| api                     | `apps/api` (uvicorn --reload) | FastAPI; **AI jobs run synchronously in-process** — there is no worker service                                                                         |
| web                     | `apps/web` (next dev)         | `:3000` (override with `WEB_PORT` in the root `.env`)                                                                                                  |

- Seed the demo data: `docker compose exec -T api python scripts/seed_demo.py`
  (idempotent).
- LLM defaults to `SHIELD_LLM_MODE=fixture` — deterministic offline responses
  for all five AI purposes (DECISIONS D-017); live mode needs
  `SHIELD_LLM_MODE=live` + `SHIELD_LLM_PROVIDER` and that provider's
  credential — an API key for `anthropic`/`openai`/`gemini`, gcloud ADC (no
  key) for `vertex` (D-024/D-029). A misconfigured live boot fails loudly at
  startup (D-026).
- Logs: structured JSON (structlog) to stdout with request correlation IDs —
  `docker compose logs -f api`. There is no metrics/Prometheus endpoint.
- Production-shaped Dockerfiles exist (`apps/api/Dockerfile`, least-privilege
  user; `apps/web/Dockerfile`, Next standalone output) but no deployment
  automation consumes them yet.

## Backup / restore today

Dev data lives in named Docker volumes (`postgres-data`, `minio-data`, …).
There is no automated backup. `docker compose down -v` destroys everything;
re-run migrations + seed to rebuild the demo.

## Planned production posture (not implemented)

None of the following exists in this repo today — `infra/terraform/` is an
empty placeholder and `docs/runbooks/` is empty. Decisions on cloud, account,
region, and network are pending (needs-David; see `DELIVERY_PLAN.md`).

- Terraform IaC for AWS GovCloud and/or Azure Government.
- Managed Postgres (PITR + snapshots), managed Redis, S3/Blob + KMS with
  versioning and tight bucket policy.
- Secrets manager with rotation; JWT signing-key rotation.
- Log aggregation (CloudWatch / Log Analytics) and alerting; a metrics
  exposition endpoint would have to be added to the API first.
- Runbooks: incident response, backup/restore, key rotation, DR,
  redactor-failure.
- FedRAMP package artifacts (SSP / SAR / POA&M).

When any of these land, move them up into "Running today" with the command or
path that proves them.
