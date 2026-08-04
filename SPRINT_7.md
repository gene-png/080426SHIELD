# SPRINT 7 — GCP live path + close the client loop

_Branch: `feat/gcp-vertex-sprint-7` (cut from `main` post-#33). Queue:
`.claude/sprint-queue.sprint-7.json` (copy to `.claude/sprint-queue.json` to
launch). Driver: `/loop-sprint-cron` (or execute tasks by hand). Created
2026-07-13 after Sprint 6 (PR #33, `v3.3.0`) merged._

## Why this sprint exists

Sprint 6 made every core path real, but live-AI validation still assumes an
**Anthropic API key** that Dave does not intend to provision. Dave's GCP posture
(established in kentro-cloud-modernization) is **Vertex AI via Application
Default Credentials** — no static `AIza…` API keys anywhere, `LLM_PROVIDER=stub`
committed, real model flipped on by an operator. SHIELD's existing `gemini`
provider (D-024) only speaks the `generativelanguage.googleapis.com` API-key
path, so it cannot use this machine's credentials.

**Feasibility was proven 2026-07-13 on Dave's box:** a direct
`generateContent` call to
`us-central1-aiplatform.googleapis.com/v1/projects/kentro-cloudmod-dev/.../gemini-2.5-flash`
authenticated with local gcloud ADC returned HTTP 200 and a correct response
(10 prompt / 6 output tokens, modelVersion `gemini-2.5-flash`). The only
missing piece is a SHIELD provider adapter that exchanges ADC for bearer
tokens.

Also carried in: the client loop still ends silently (release sends no
notification even though Sprint 6 shipped a real SMTP sender), dev email
delivery is default-off so the s21 e2e always self-skips, the reqSeq sweep
remainder is still open from Sprint 5, and the `uuid` moderate advisory still
waits on the Auth.js v5 migration.

**Infra decision (Dave, 2026-07-13): SHIELD continues to run on local
containers for now.** No terraform/cloud deploy this sprint — the GCP work here
is the *LLM egress path only*.

## Sprint goal

A dev with gcloud ADC (no API key) can flip SHIELD to live AI on Vertex and
watch all five AI purposes egress real, redacted calls; a released deliverable
notifies the client by email; the email loop runs in dev/CI instead of
self-skipping; the reqSeq and Auth.js debts are paid.

Version at close: **`3.4.0`**.

## Prerequisites / launch checklist

1. Merge this planning PR.
2. `git checkout -b feat/gcp-vertex-sprint-7 main` BEFORE the first fire.
3. Archive the old runtime queue, COPY `.claude/sprint-queue.sprint-7.json` to
   `.claude/sprint-queue.json`; set `working_dir` + `expected_gh_user` for YOUR
   box; confirm the `gates` array matches your environment (six gates: pytest
   -m unit, web tsc, prettier 3.9.5, in-container ruff/black, web vitest, web
   eslint — the 6th was added mid-Sprint-6 after a latent lint error slipped
   the five-gate set).
4. `/loop-sprint-cron`.
5. **GCP live validation (T1) needs gcloud ADC on the host** — verify with
   `gcloud auth application-default print-access-token` before launching.
   Project `kentro-cloudmod-dev`, region `us-central1` (Dave's box already has
   both). Live tasks stay opt-in: they self-skip without
   `SHIELD_LLM_MODE=live`, so loop/CI stay green credential-free.

## Environment facts the loop must know

All CLAUDE.md gotchas hold, plus Sprints 4–6 additions: ruff/black pinned
exactly (`ruff==0.15.20`, `black==26.5.1`); `known-first-party=["app"]` in the
ROOT pyproject (do not remove); rebuild the api image after ANY
`apps/api/pyproject.toml` dep change (`docker compose build api && docker
compose up -d api` — plain restart does not install deps; T0 adds
`google-auth`); new python module under `app/` needs `docker compose restart
api` (never mid-pytest, SIGKILL 137); after ANY web/packages edit
`docker compose up -d --force-recreate web` before e2e; poll long gates in the
FOREGROUND in sub-9-minute bursts (never park on background monitors — bit us
4 times in Sprint 6); e2e on the HOST via winget node + Playwright cli, port
from `e2e/helpers/baseUrl.ts`; `gh auth switch --user <yours>` before gh
writes (active account silently flips to the EMU read-only account).

Live-AI env vars (root `.env`, gitignored, revert to fixture after each
validation): `SHIELD_LLM_MODE=live`, `SHIELD_LLM_PROVIDER=vertex`,
`SHIELD_LLM_MODEL=gemini-2.5-flash` (the ADC-validated id), `GCP_PROJECT_ID`,
`GCP_REGION`. Never commit credentials; ADC json is bind-mounted read-only,
never copied into the repo or image.

## Tasks

### T0 — Vertex AI provider adapter (D-029)

The core task; everything GCP hangs off it.

- Add `vertex` to the `LLMProvider` literal (`app/config.py:16`) and settings
  `gcp_project_id: str = ""` + `gcp_region: str = "us-central1"`.
- New `VertexProvider` in `app/ai/llm.py` beside `GeminiProvider`, same seam
  contract (payload already redacted; adapter only shapes request and parses
  text + token counts). Endpoint:
  `https://{region}-aiplatform.googleapis.com/v1/projects/{project}/locations/{region}/publishers/google/models/{model}:generateContent`.
  Request/response schema is identical to `GeminiProvider` (generateContent),
  so factor the shared body-build/parse out rather than duplicating it.
- Auth: `google-auth` dependency (`google-auth>=2,<3` in
  `apps/api/pyproject.toml`; REBUILD the api image) — obtain ADC via
  `google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])`,
  refresh lazily, send `Authorization: Bearer`. The token must NEVER appear in
  logs, `llm_calls.error_message`, or exception text (mirror the Gemini
  key-in-header lesson at `llm.py:231-234`).
- Compose: bind-mount the host gcloud config dir read-only into api
  (`~/.config/gcloud` linux-style / `%APPDATA%\gcloud` on this box — compose
  var with a sensible default) and set `GOOGLE_APPLICATION_CREDENTIALS` to the
  mounted ADC file. Document the Windows path quirk in the compose comment.
- Preflight parity (D-026 pattern): `live_llm_readiness()` for `vertex`
  requires `gcp_project_id` set, `google-auth` importable, AND ADC resolvable
  (`google.auth.default()` succeeds) — fail LOUDLY at boot otherwise; fixture
  unaffected. `/admin/ai-status` and the `/ready` LLM check inherit
  automatically.
- DECISIONS: append **D-029** (Vertex via ADC as the GCP path; records the
  2026-07-13 feasibility call, the no-API-key posture inherited from
  kentro-cloud-modernization, and that `gemini` [API-key] and `vertex` [ADC]
  remain distinct providers).
- TDD: adapter unit tests with mocked credentials + httpx (parse, token
  counts, error paths, no-token-in-error); preflight tests (vertex + missing
  project / missing ADC raises at boot; valid config boots; fixture
  unaffected).

### T1 — GCP live validation sweep (opt-in) + SMOKE_TEST §14 GCP note

- Extend `apps/api/tests/live/test_live_ai.py` and
  `scripts/smoke_live_ai.py` to be provider-agnostic where they aren't already
  (they read settings; verify no anthropic-specific assertions block vertex).
- With `.env` flipped to `vertex`/`gemini-2.5-flash`: run the one-command smoke
  and the full `pytest -m live` five-purpose sweep. Assert the same contract as
  Sprint 6 T7: complete `llm_calls` row (`provider=vertex`, `mode=live`,
  `status=completed`, tokens), exact `redacted_counts`, no raw PII in the
  response, response parses into the route-layer container.
- SMOKE_TEST §14/§14.1: annotate as **GCP-validated** with the run date and
  provider/model; boxes checked only per the honesty convention (the opt-in
  spec is the proof, CI-skip noted).
- Revert `.env` to fixture afterward. Depends: T0.

### T2 — Client release notification email (D-030)

- Sprint 5 deferred this pending a real sender; Sprint 6 shipped one
  (`app/email/sender.py`). On deliverable release (the shared
  `deliverable_release.py` helper), when `shield_email_delivery_enabled` is on,
  email every active client-role user of that tenant: service, deliverable
  title/version, link to `{web_base_url}/documents`. No email → no crash: with
  delivery off the release proceeds exactly as today (loud log either way —
  "notification sent to N recipients" / "delivery disabled, skipped").
- Failure semantics: SMTP failure logs loudly and does NOT roll back the
  release (the release is the source of truth; the email is best-effort
  notify) — document this in D-030.
- DECISIONS: append **D-030**.
- TDD: unit tests for recipient selection (client users of the right tenant
  only), content fields, delivery-off no-op, SMTP-failure-doesn't-block.
  Extend the s21 MailHog e2e (or a new s22) to see the release notification
  land after T3 turns delivery on in dev.

### T3 — Enable email delivery in dev/CI compose (MailHog on by default)

- Set `SHIELD_EMAIL_DELIVERY_ENABLED=true` (SMTP → mailhog) in
  `docker-compose.yml` for the dev stack so the email loop is REAL in every
  dev/e2e run — the s21 spec stops self-skipping and §25 gets a green committed
  box. `SHIELD_AUTH_REQUIRE_EMAIL_VERIFY` stays **false** (flipping it would
  break every existing e2e sign-in; enforcement remains a deploy-time choice).
- Sweep existing e2e for assumptions that registration sends nothing; MailHog
  is per-run disposable so cross-spec mail pollution needs checking (s21
  already isolates by unique timestamped emails — keep that pattern).
- CI: confirm the e2e job's compose brings up MailHog (it does today) and s21
  now runs there. Full-suite runtime impact should be minutes at most.

### T4 — reqSeq guard sweep remainder (Sprint 5 carry-over)

- Sprint 5 T9 fixed only what the 14 react-hooks rules flagged. Sweep the
  remaining mount-fetch-then-mutate components (the known list lives in the
  Sprint 5 notes: the admin workspaces and panels not covered by
  MessageThread/CsfPlaybookPanel-style guards), apply the reqSeq pattern where
  a stale response can clobber newer state, and add vitest guards for the two
  highest-traffic ones (T8-style deferred-promise tests).
- No speculative guards where no race exists — justify each edit in the commit
  body.

### T5 — Auth.js (next-auth) v5 migration

- `next-auth@4.24.x` → `@auth/core`-based v5: `auth.ts` config export,
  middleware/route-handler updates, `getServerSession` → `auth()` call sites,
  credentials providers (password + the Sprint 6 `totp` exchange) re-wired.
  Behavior-identical: every existing auth e2e (s0/s1, MFA sign-in flow) must
  pass unchanged.
- Clears the documented `uuid@8.3.2` moderate advisory (via next-auth) — after
  the bump, `pnpm audit` should show only the `postcss` moderate. Update the
  BUILD_REPORT audit posture.
- Riskiest task of the sprint (auth touches everything); do it LAST of the
  feature tasks, full e2e before commit. After `apps/web/package.json` changes:
  reinstall INSIDE the web container, then force-recreate.

### T6 — Wrap-up

- SMOKE_TEST: §14 GCP annotation (T1), §25 now CI-green (T3), new §29 release
  notification (T2); boxes only with committed green specs, honesty convention.
- CHANGELOG `[3.4.0]` per-task entries with commits; BUILD_REPORT sync (audit
  posture post-T5, gate results, Vertex in the provider matrix).
- DECISIONS: verify D-029/D-030 landed.
- Full exit gate set (all six gates) + full e2e; CONTEXT.md overwritten with
  the end-of-sprint snapshot; `context/dave.md` refreshed.

## Definition of done

- With gcloud ADC only (no API key anywhere), flipping `.env` to
  `vertex`/live sends all five AI purposes through real, redacted Vertex calls
  recorded in `llm_calls`; misconfigured vertex-live fails loudly at boot.
- A released deliverable emails the tenant's client users (visible in MailHog);
  delivery-off releases behave exactly as v3.3.0.
- s21 runs (not skips) in dev and CI; SMOKE_TEST §25 checked with the spec.
- Remaining stale-fetch races guarded; next-auth v5 with `uuid` advisory
  cleared and all auth e2e green.
- No credential, token, or ADC file committed or baked into an image; every
  commit conventional and task-scoped; CONTEXT.md snapshot written.

## Explicitly out of scope (needs-Dave / later)

- **Cloud deploy / terraform / DR runbooks** — Dave's 2026-07-13 decision:
  local containers for now. The `infra/terraform` stubs stay stubs.
- Keycloak integration (auth remains the custom JWT flow per D-027).
- `azure_openai` / `bedrock` / `local` adapters (loud not-implemented).
- MFA manual UI walkthrough — Dave is doing this by hand.
- ESLint 10 (still blocked upstream).
- `postcss` moderate (clears on next upstream Next bump).
