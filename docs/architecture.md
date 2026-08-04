# Architecture

> Authoritative spec: [`reference-docs/SHIELDv2_Master_Spec.txt`](../reference-docs/SHIELDv2_Master_Spec.txt) §§ 4, 11, 16 — as amended by
> [`DECISIONS.md`](../DECISIONS.md) (notably D-015 multi-tenant and the Work
> Order Parts A–F entries). Where this document and the spec disagree, the
> decision log wins; this document describes what is actually running.

## 10,000-foot view

SHIELD is a **multi-tenant** web platform (D-015): one deployment serves many
client organizations. Every business table carries a `client_id` column and
every data route filters by the resolved tenant. One Next.js app talks to one
FastAPI service, with shared infrastructure (Postgres, Redis, MinIO/S3,
Keycloak, MailHog). There is **no worker service** — AI jobs run synchronously
inside the `api` process.

Two user roles:

- **admin** — Kentro consultant, platform-wide (`User.client_id IS NULL`);
  picks the active tenant per request via the `X-Client-Id` header (surfaced
  as a client switcher in the web nav). An earlier read-only "reviewer" role
  was folded into admin by Work Order A3 (see the DECISIONS.md supersession
  erratum for D-005/D-006).
- **client** — a customer user, pinned to their own `client_id` at
  registration; requests cannot escape it.

Four assessment services — Technical Debt Review, Zero Trust (CISA ZTMM 2.0 +
DoD ZTRA), NIST CSF 2.0 (10-step Playbook), MITRE ATT&CK coverage — plus a
Risk Register (5x5, NIST 800-30) synthesized from them.

## Components

```
┌────────────────────────────────────────────────────────────┐
│                         Browser                            │
└──────────────────┬─────────────────────────────────────────┘
                   │ TLS
                   ▼
┌────────────────────────────────────────────────────────────┐
│  apps/web — Next.js 15 (App Router, TS strict)             │
│  • Auth.js v5 (next-auth) Credentials → SHIELD-issued JWT  │
│    (Keycloak realm scaffolded for later OIDC federation)   │
│  • Tailwind + shadcn (Round 6 design language)             │
│  • /api/proxy/* server routes forward to the API with the  │
│    session bearer + X-Client-Id; API host never reaches    │
│    the browser                                             │
└──────────────────┬─────────────────────────────────────────┘
                   │ HTTP (server-side calls)
                   ▼
┌────────────────────────────────────────────────────────────┐
│  apps/api — FastAPI (Python 3.12)                          │
│  • Pydantic v2 schemas; SQLAlchemy 2 + Alembic             │
│  • Tenant resolution (current_client) + app/tenant.py      │
│    ownership checks on every data route                    │
│  • Deterministic scoring engines (csf/risk/zt)             │
│  • Synchronous AI jobs via app/ai/engine.run_job           │
│  • PII redactor on every LLM egress (app/ai/redact.py)     │
│  • Typed error envelope {reason, message} (D-016)          │
│  • JSON structured logs (structlog) + correlation IDs      │
└──────┬──────────────┬──────────────┬──────────────┬────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
   Postgres 16    Redis 7        MinIO (S3)    Keycloak 25
   (data model)  (rate          (artifact      (realm export;
                  limiting)      storage)       future OIDC)
```

Dev stack also runs MailHog (SMTP capture, `:8025`). There is no Celery, no
queue, and no `apps/worker` — the orphaned worker service was removed in Work
Order Part F (see DECISIONS.md D-021). Redis's real job
today is the fixed-window **rate limiting** on auth and run-AI routes
(`app/security/rate_limit.py`, Sprint 3 T3); the limiter fails open with a
loud warning if Redis is down.

## Tech stack

| Layer          | Choice                                                                             | Notes                                                                                                                                    |
| -------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Frontend       | Next.js 15 App Router + React 19 + TypeScript strict + Tailwind 4 + shadcn         | Round 6 design language; `@shield/design-system` package (framework majors bumped Sprint 4)                                              |
| Backend        | FastAPI on Python 3.12                                                             | OpenAPI at `:8000/docs`                                                                                                                  |
| Database       | PostgreSQL 16 (prod/dev), SQLite (unit tests)                                      | Alembic migrations, `batch_alter_table` for SQLite safety                                                                                |
| Cache          | Redis 7                                                                            | Rate limiting only — no queue, no Celery                                                                                                 |
| Object storage | S3-compatible (MinIO in dev)                                                       | Artifact uploads + generated deliverables                                                                                                |
| IdP            | SHIELD-issued JWT (HS256) via Auth.js v5 (next-auth) Credentials                   | Migrated from next-auth v4 to Auth.js v5 in Sprint 7 (T5); Keycloak realm scaffolded under `infra/keycloak/` for later                   |
| AI             | Single egress client `app/ai/llm.py`; Anthropic/OpenAI/Gemini/Vertex or fixtures   | `SHIELD_LLM_MODE=fixture` is the offline default (D-017); provider via `SHIELD_LLM_PROVIDER` (D-024); Vertex via ADC, no API key (D-029) |
| Tests          | pytest (unit, SQLite) + web vitest (jsdom) + Playwright e2e (host-run) + axe sweep | Web unit harness added Sprint 5 T8; see `docs/development.md` for the real command matrix                                                |

## Data isolation (multi-tenant, D-015)

- Every business table carries `client_id`; reads filter by it, writes set it
  at row creation.
- `current_client` (in `app/dependencies.py`) resolves the active tenant:
  client-role users are pinned to `user.client_id`; platform admins name a
  tenant with `X-Client-Id`.
- Id-based fetches go through `app/tenant.py` `require_*_in_tenant` helpers,
  which return **404 on tenant mismatch** — no existence oracle.
- Cross-tenant isolation is unit-tested (`test_new_surface_authz.py` and the
  tenant/draft-guard suites) under `pytest -m unit`.

## Audit log

Every state-changing route writes one row to **`audit_entries`** via the only
blessed write surface, `app/audit/spine.py::audit()`. Append-only at two
layers: a Postgres `BEFORE UPDATE/DELETE` trigger in production, plus a
SQLAlchemy `before_flush` guard that raises `AuditEntryImmutableError` on any
dialect (so SQLite tests catch violations too). Rows carry actor user id,
action verb, target type + id, JSON details, and the request correlation id.

Sprint 5 T7 added the first **read** surface over the two append-only stores
(`audit_entries` and `llm_calls`): admin-only `GET /admin/audit-entries` and
`GET /admin/llm-calls`, keyset-cursor paginated on `(at/requested_at desc, id
desc)` (no OFFSET) with filters (action prefix, target type, actor,
correlation id, date range / client id, purpose, provider, status). The
`/admin/audit` viewer is a strictly read-only two-tab UI (Activity / AI calls)
with correlation-id click-through — no mutation affordance, so the append-only
guarantee is upheld by construction. The `llm_calls` projection exposes only
audit-safe fields (counts, tokens, duration, status, error message) — never an
api key or payload content.

## Client portal & deliverable release (Sprint 5, D-025)

Consultant output reaches the **client** role only through an explicit release
(Master Spec §12): a deliverable is invisible until an admin releases the
finalized version. `deliverables` carries nullable `released_at`/`released_by`
(migration 0028); the shared `app/deliverable_release.py` helper backs four
per-service `POST /{service}/deliverables/{id}/release` routes (typed 409
`not_finalized`, idempotent, `*.deliverable.released` audit). Client-facing
reads live in `app/routes/clients.py`:

- `GET /clients/{cid}/deliverables` — released-only, tenant-enforced (404 on
  mismatch), feeding the `/documents` page (§6.7).
- `GET /clients/{cid}/value-summary` — the cross-service value loop (§2.5) on
  `/home` (§6.4). **Deterministic aggregation, no LLM**: it sums already-computed
  engine outputs and gates every number on the §12 release rule — a service
  contributes only when it has a released deliverable, and the recompute is
  pinned to the FINALIZED (approved/released) assessment version so a
  post-release draft can never leak (a service with no released data renders
  "Pending", never a fabricated 0).

The artifact download path (`app/routes/artifacts.py`) admits a client to a
released own-tenant deliverable's artifacts and nothing else. The CSF Playbook
gained a POA&M / action-plan step (migration 0029 `csf_gap_actions`; per-gap
characterization/priority-override/owner/deadline/resources/success-criteria/
POA&M-ref, exported into the playbook XLSX Action Plan sheet).

A pre-egress **redaction preview** (`POST /ai/preview`, `app/routes/ai_preview.py`)
shows exactly what a Run-AI would send AFTER redaction — reusing each service's
run-ai payload builder so it cannot diverge — WITHOUT egressing or writing an
`llm_calls` row.

## AI integration boundary

"**AI suggests, code computes.**" The LLM only drafts values and narrative;
every score, tier, roll-up and roadmap is computed by deterministic Python
engines (`app/csf/playbook.py`, `app/risk/engine.py`, `app/zt/scoring.py`).

```
route → engine.run_job(purpose, payload, client_id)
          → redact_payload(payload)            # app/ai/redact.py, counts only
          → llm_calls row opened (status=running, client_id, service_id)
          → provider call (Anthropic | OpenAI | Gemini | Vertex | runtime fixtures)
          → llm_calls row finalized (tokens, duration, redacted_counts)
          → route parses the draft and writes rows; engines compute totals
```

- The redactor is one-way. There is **no `unredact`** — redacted content
  never needs to come back, because the LLM's draft references stable codes
  (technique ids, subcategory codes), not the redacted prose.
- `llm_calls` records **counts only, never payload content** (§12.1), and is
  attributed to the tenant via `client_id` (Sprint 3 T5) plus `service_id`
  where a service is in play.
- Five job purposes: `extract.capabilities`, `mitre_map`, `zt_score`,
  `csf_score`, `risk_synthesize`. In fixture mode (the offline default,
  D-017) each has a deterministic, payload-aware canned response; live mode
  needs `SHIELD_LLM_MODE=live` plus the selected provider's credential (an API
  key for most providers; `vertex` uses gcloud Application Default Credentials
  — no static key).
- **Provider seam (D-024).** `SHIELD_LLM_PROVIDER` selects the live adapter;
  every adapter lives below the egress seam and only translates prompt +
  redacted payload → provider REST API → text back. Redaction, the
  `llm_calls` audit row, and "AI suggests, code computes" all sit _above_ the
  seam and are provider-independent. Thin `httpx` adapters (no SDK) for
  OpenAI (chat/completions), Gemini (`generateContent`), and Vertex
  (regional `{region}-aiplatform.googleapis.com` `generateContent`); Anthropic
  lazy-imports its SDK. `gemini` and `vertex` share the `generateContent`
  request-build/response-parse helpers (`_generate_content_body` /
  `_parse_generate_content`) but differ in auth: `gemini` sends an
  `AIza…` API key, `vertex` exchanges gcloud ADC for a short-lived
  `Authorization: Bearer` token (D-029, Sprint 7 T0). The bearer rides the
  header, never the URL, so an `HTTPStatusError` cannot leak it into logs or
  `llm_calls.error_message`. A non-`STOP` `finishReason` (e.g. a
  thinking-model output truncation) raises loudly rather than persisting a
  half-JSON draft as "completed".

  | Provider              | Status          | Credential                                                |
  | --------------------- | --------------- | --------------------------------------------------------- |
  | `anthropic` (default) | Implemented     | `ANTHROPIC_API_KEY`                                       |
  | `openai`              | Implemented     | `OPENAI_API_KEY`                                          |
  | `gemini`              | Implemented     | `GEMINI_API_KEY`                                          |
  | `vertex`              | Implemented     | gcloud ADC (no API key) — `GCP_PROJECT_ID` + `GCP_REGION` |
  | `azure_openai`        | Not implemented | —                                                         |
  | `bedrock`             | Not implemented | —                                                         |
  | `local`               | Not implemented | —                                                         |

  A missing credential for the selected provider (a missing API key, or —
  for `vertex` — an unset `gcp_project_id`, a missing `google-auth`, or
  unresolvable ADC), or a not-implemented provider, raises a loud
  `RuntimeError` at construction / boot preflight (`live_llm_readiness`,
  D-026).

- Run-AI endpoints are rate-limited per client (T3).

## Auth

- **Web session layer: Auth.js v5 (next-auth).** The browser talks to a
  Credentials provider (`apps/web/src/lib/auth/options.ts`) that forwards to the
  API and stores the SHIELD-issued JWT pair in the session; `apps/web` migrated
  from next-auth v4 to Auth.js v5 in Sprint 7 (T5), swapping
  `getServerSession(authOptions)` for `auth()` at every server call site. The
  MFA challenge surfaces via a `CredentialsSignin` subclass whose
  `code = "mfa_required"` reaches the client as `signIn(...).code` (v5
  normalizes every credentials failure to `CredentialsSignin`), not `.error`.
  The credentials-provider seam stays a dormant hook for a later OIDC / Keycloak
  cutover. Behaviour is identical to v4; the bump cleared the `uuid@8.3.2`
  moderate advisory.
- SHIELD-issued HS256 JWTs: 15-minute access tokens, 30-minute refresh tokens
  (the refresh TTL **is** the idle timeout).
- Refresh rotation: single active refresh jti per user; a replayed token is
  rejected (`reason=refresh_reused`). Forced re-auth ceiling: `auth_time`
  claim, 24h default (`reason=reauth_required`). See D-020.
- Account lockout (10 failures / 15 min) and per-IP + per-account rate limits
  on login/register, checked before Argon2 work (T3). Second-factor failures
  (MFA verify / verify-login) feed the SAME lockout counter as password
  failures; counters reset only on a fully successful login (Sprint 6 T10).
- **TOTP MFA (Sprint 6, D-027).** RFC 6238 implemented in `app/security/totp.py`
  (stdlib HMAC, no OTP dependency). The per-user secret is Fernet-encrypted at
  rest (key derived from `JWT_SIGNING_SECRET`); recovery codes are Argon2id-hashed
  (`user_recovery_codes`, migration 0030). `/auth/mfa/enroll` returns an
  otpauth:// provisioning URI; `/auth/mfa/verify` confirms a code, flips
  `mfa_enrolled`, and issues one-time recovery codes. When an enrolled user
  logs in, `/auth/login` returns a short-lived `mfa_pending` token INSTEAD of the
  pair; `/auth/mfa/verify-login` exchanges it plus a current TOTP or single-use
  recovery code for the real pair.
- **Email verification + password reset (Sprint 6, D-028).** `app/email/`
  (SMTP sender gated by `shield_email_delivery_enabled`, + SHA-256-hashed
  single-use tokens in `email_tokens`, migration 0031). Register mints a
  verification token; `/auth/verify-email`, `/auth/resend-verification`,
  `/auth/forgot-password`, `/auth/reset-password` complete the flows. Tokens are
  single-use (stamped only on success) with expiry; resend/forgot/reset return a
  uniform message so no account enumeration. Dev delivery is MailHog.
- The D-020 boot-refusals are GONE. `SHIELD_AUTH_REQUIRE_MFA` and
  `SHIELD_AUTH_REQUIRE_EMAIL_VERIFY` now GATE ENFORCEMENT (an enrolled user is
  always challenged; the flag decides what happens to a not-yet-enrolled /
  unverified user), rather than refusing to boot for a flow that didn't exist.

## Failure model

- API errors use the typed `{reason, message}` dict-detail envelope (D-016);
  the web maps reasons to friendly copy. Never a raw validation dump, never a
  silent success-lie.
- 5xx responses carry the correlation ID only — no stack traces.
- AI jobs are synchronous: the run-AI request returns the outcome directly
  (typed 4xx/5xx on failure — e.g. 502 on an unparseable LLM response, 503 on
  a missing runtime fixture).
