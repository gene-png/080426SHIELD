# SPRINT 6 — Make it real (all-real demo hardening)

_Branch: `feat/real-demo-sprint-6` (cut from `main` post-#31). Queue:
`.claude/sprint-queue.sprint-6.json` (copy to `.claude/sprint-queue.json` to
launch). Driver: `/loop-sprint-cron` (or execute tasks by hand — this plan is
written to be runnable either way). Created 2026-07-12 after Sprint 5 (PR #31,
`v3.2.0`) merged. **NOT YET LAUNCHED — intended for handoff to another dev.**_

## Why this sprint exists

Sprint 5 shipped the client value loop, but a demo where **every part is real
and nothing is mocked** still has concrete gaps. On 2026-07-12 we ran a live
Anthropic smoke (SMOKE_TEST §14) with a real key and learned exactly where the
distance is:

- **The live LLM path itself WORKS.** `claude-sonnet-5` returned a real drafted
  narrative in ~2.6s; the redactor stripped 6 PII items
  (`{client_org: 2, name: 2, email: 2}`) **before** egress so the model only saw
  `[CLIENT]`; the `llm_calls` row recorded `provider=anthropic / model / mode=live
  / status=completed / tokens / client_id` with no error and stored no PII. The
  "AI suggests, code computes" seam and redaction are real and correct.
- **But three independent things block a naive "flip to live":** (1) the
  `anthropic` SDK is not a declared dependency (`apps/api/pyproject.toml` has no
  `anthropic`; the adapter lazy-imports it → `ImportError` on first call); (2)
  the default model is the stale, invalid id `claude-opus-4-7`
  (`app/config.py:53`, `docker-compose.yml:17`) which would 404 at the provider;
  (3) there is no boot-time preflight, so all three fail only on the first
  Run-AI request, never at startup.
- **Seeded deliverables can't be downloaded.** The seed writes artifact bytes to
  `LocalFilesystemStorage` (`scripts/seed_demo.py:746`) while the API reads via
  `get_storage()` → S3/MinIO under compose (`routes/artifacts.py:238`), so every
  seeded deliverable download returns **410 GONE**. Only artifacts finalized
  through the API at runtime download today.
- **Auth is demo-shaped, not real.** MFA and email-verification are D-020
  fail-loud stubs (`config.py:60-62`, `assert_safe_for_runtime` refuses to boot
  if either flag is on — `config.py:115-124`). The `User` model already carries
  `mfa_enrolled` / `email_verified_at` (`models/user.py:52-53`) but no TOTP
  secret column and no flows exist. SMTP is stubbed (`config.py:94-96`, MailHog).
- **Health is DB-only.** `/ready` (`routes/health.py:47`) checks Postgres only —
  not redis/minio/keycloak/LLM — so no single endpoint proves "all real, all
  green" for a demo operator.

## Sprint goal

Close as much of that distance as possible: make the LLM path, deliverable
downloads, auth (MFA + email verification/reset), health visibility, and demo
bring-up all **real**. Cloud/terraform deploy stays out of scope (gated on
Dave's cloud/account/region decisions — see Out of scope).

Version at close: **`3.3.0`** (additive real-auth + live-AI enablement).

## Prerequisites / launch checklist (the receiving dev)

1. Merge this planning PR.
2. `git checkout -b feat/real-demo-sprint-6 main` BEFORE the first fire.
3. Archive the old runtime queue, COPY `.claude/sprint-queue.sprint-6.json` to
   `.claude/sprint-queue.json`; **set `working_dir` + `expected_gh_user` for
   YOUR box** (they are placeholders in the staged file). **Also confirm the
   `gates` array matches YOUR environment** — the copied gates encode Dave's box
   (Docker CLI at `/c/Program Files/Docker/...`, the winget Node path in the
   prettier gate, web on `:3001`). On a different OS / Docker / Node layout,
   adapt those command strings; the five gates themselves (pytest -m unit, web
   tsc, prettier 3.9.5, in-container ruff/black, web vitest) are the invariant.
4. `/loop-sprint-cron` (or run tasks by hand following the per-task notes).
5. **Anthropic API key** (recommended provider): the live-AI tasks (T1, T7) are
   **opt-in** — their integration tests skip without `SHIELD_LLM_MODE=live` +
   `ANTHROPIC_API_KEY`, so the loop and CI stay green without a key. To actually
   validate live paths, put a key in the gitignored root `.env`
   (`SHIELD_LLM_MODE=live`, `SHIELD_LLM_PROVIDER=anthropic`,
   `SHIELD_LLM_MODEL=claude-sonnet-5`, `ANTHROPIC_API_KEY=...`), run the task's
   smoke, then **revert `.env` to fixture** and never commit the key.

## Environment facts the loop must know

All CLAUDE.md gotchas hold, plus Sprint 4/5 additions: api compose-mounts the
root `pyproject.toml` so in-container ruff/black equal CI; **ruff/black are
pinned exactly** (`ruff==0.15.20`, `black==26.5.1` in `apps/api/pyproject.toml`)
and `[tool.ruff.lint.isort] known-first-party = ["app"]` in the ROOT pyproject
makes import classification layout-independent (do not remove — that was the
PR #31 gate divergence). Web stack: Next 15 / React 19 / Tailwind 4 / ESLint 9
flat (14 react-hooks v6 rules ON) / Node 22; web has a vitest gate
(`pnpm -F web test`) that is the 5th runtime-queue gate. This box: web on :3001;
e2e via winget node.exe + `e2e/node_modules/@playwright/test/cli.js`; Docker CLI
needs the PATH export per shell; `gh auth switch --user <yours>` before gh writes
(the active account silently flips to an EMU read-only account — PR #31 hit
this). Loop lessons that bite here: poll long gates in the FOREGROUND to the end
of the iteration (dispatched agents park on background monitors — nudge them);
never restart api mid-pytest (SIGKILL 137); new python module under `app/` needs
`docker compose restart api`; after ANY web/packages edit `docker compose up -d
--force-recreate web` before e2e. New migrations MUST be additive + SQLite-safe
(`batch_alter_table`, C0): expected `0030` (MFA TOTP secret + recovery codes),
`0031` (email-verification / reset tokens). **After editing
`apps/api/pyproject.toml` deps (T0 adds `anthropic`), rebuild the api image**
(`docker compose build api && docker compose up -d api`) — a plain restart won't
install a new dependency.

## Tasks

### T0 — Live-AI enablement: declare `anthropic`, fix the model default, boot preflight (D-026)

The single highest-value task; the 2026-07-12 smoke proved the path works once
these are fixed.

- Add `anthropic>=0.40,<1` to `apps/api/pyproject.toml` dependencies
  (`:6-30`); rebuild the api image so it's installed (the adapter lazy-imports
  `from anthropic import Anthropic` at `app/ai/llm.py:121`).
- Replace the stale default model `claude-opus-4-7` with a valid current id at
  `app/config.py:53` AND `docker-compose.yml:17` (use `claude-sonnet-5` — the
  smoke-validated id — or make the model required in live mode with no default).
- Add a **live-mode boot preflight**: extend `Settings.assert_safe_for_runtime()`
  (`app/config.py:101`, called from the lifespan at `app/main.py:41`) so that
  when `shield_llm_mode == "live"` it fails LOUDLY unless the selected provider's
  key is present AND its SDK is importable (mirror the `_build_provider` branch
  logic at `app/ai/llm.py:265`) AND the model id is not a known-placeholder.
  Fixture mode unaffected.
- Consider extending `GET /admin/ai-status` (`routes/admin.py:490`) to also
  report SDK-importable + model-set (today it checks the key only, `:513`).
- DECISIONS: append **D-026** (live-AI enablement + preflight; records that
  `anthropic` is a real runtime dep and the redaction/`llm_calls` contract was
  live-verified on 2026-07-12).
- TDD: live + missing key → loud raise at boot; live + valid config → boots;
  fixture → unaffected. (SDK-missing is hard to unit-test post-install; assert
  the preflight logic path instead.)
- Verify: `pytest -m unit` green; `docker compose build api` succeeds with
  `anthropic` importable in the container.

### T1 — Live-AI integration test + SMOKE_TEST §14 codification (opt-in)

- Add an opt-in integration test marked `@pytest.mark.live` (a new marker,
  registered in pyproject; **excluded from the default `-m unit` gate and CI**)
  that, when `SHIELD_LLM_MODE=live` + a key are present, runs ONE real CSF
  Run-AI and asserts the contract: real non-empty response, `llm_calls` row with
  `provider`/`model`/`mode=live`/`status=completed`/tokens set, `redacted_counts`
  populated when PII is present, `error_message` null, and NO PII in the response.
- Add `apps/api/scripts/smoke_live_ai.py` reproducing the 2026-07-12 manual
  smoke (build a CSF-narrative payload with deliberate PII → `LLMClient.invoke`
  → print response + row) so any dev can validate a key in one command.
- SMOKE_TEST.md §14: annotate as validated by this opt-in spec + documented
  procedure (note CI skips it without a key — do NOT falsely check it as a
  CI-green box; check it referencing the opt-in spec and the manual-run note).
- Depends: T0.

### T2 — Seed → storage parity (fix seeded-deliverable 410)

- In `scripts/seed_demo.py`, replace the direct
  `LocalFilesystemStorage(STORAGE_ROOT)` construction (`:746`, import `:89`,
  override `:120`) with `from app.storage import get_storage; storage =
  get_storage()` so the seed writes to the SAME backend the API reads (MinIO
  under compose). The `StorageBackend` protocol is identical, so `_write_artifact`
  / release paths need no signature change; `createbuckets`
  (`docker-compose.yml:91`) guarantees the bucket first.
- Fix the parallel local-path assumption in tech-debt extraction
  (`app/tech_debt/extract.py:88`, `_load_artifact_bytes`) to use the storage
  protocol uniformly (or document why the shortcut is safe).
- e2e: after a clean `down -v` + reseed, sign in as `client@atlas.example` and
  download a SEEDED released deliverable → 200 with the §15.5 filename (today it
  410s; the s17 spec currently works around this by finalizing fresh — after the
  fix, extend/relax that workaround).
- Verify: seeded deliverable download 200 from MinIO; existing e2e still green.

### T3 — Full dependency-health readiness endpoint + operator view

- Expand `GET /ready` (`routes/health.py:47`) from DB-only to a per-dependency
  matrix: db, redis, minio (bucket reachable), keycloak (optional/dormant — mark
  as such), and LLM readiness (mode + provider key/SDK, reuse the T0 preflight
  logic). Any down dependency flips `ready=false` and names the offender. Keep
  `/health` liveness cheap and dependency-free.
- Web: a small `/admin/health` view (or extend the existing admin surface /
  `/admin/ai-status` proxy) rendering the matrix so a demo operator sees
  "all green" at a glance.
- Unit: readiness returns each check; a simulated-down dependency flips
  `ready=false` with the offender named.

### T4 — Real TOTP MFA (D-027)

- Migration `0030` (additive, C0): `users.mfa_totp_secret` (nullable, encrypted
  at rest) + a `user_recovery_codes` table (hashed codes, used-at). `User`
  already has `mfa_enrolled` (`models/user.py:52`).
- Routes in `routes/auth.py`: `POST /auth/mfa/enroll` (returns otpauth
  provisioning URI + secret for a QR), `POST /auth/mfa/verify` (confirms a code,
  sets `mfa_enrolled=true`, issues recovery codes once), and a login challenge:
  when `user.mfa_enrolled`, `login` (`:294`) issues a short-lived `mfa_pending`
  token INSTEAD of the full pair (before `_issue_pair` at `:338`), completed by
  `POST /auth/mfa/verify-login`. Recovery-code path. Rate-limit the verify
  endpoints.
- Remove the boot-refusal at `config.py:115`; `shield_auth_require_mfa`
  (`config.py:60`) now GATES enforcement (require enrollment) rather than
  refusing to boot.
- Web: an MFA step on `sign-in` and an account MFA-enrollment page (net-new —
  only `sign-in`/`sign-up` exist today).
- DECISIONS: **D-027** (TOTP MFA, single custom-JWT flow; not Keycloak yet).
- TDD: enroll → verify → login-with-TOTP happy path; wrong/expired code
  rejected; recovery-code login; flag-off = no challenge (back-compat).

### T5 — Real email verification + password reset via SMTP/MailHog (D-028)

- Implement the SMTP sender gated by `shield_email_delivery_enabled`
  (`config.py:62`, SMTP settings `:94-96`; MailHog in dev,
  `docker-compose.yml:135`). Fail loudly if enabled without host config.
- Migration `0031` (additive, C0): email-verification + password-reset token
  table (token hash, purpose, expiry, used-at).
- Routes in `routes/auth.py`: on `register` (`:263`) send a verification email;
  `POST /auth/verify-email` consumes the token → sets `email_verified_at`
  (`models/user.py:53`); resend; `POST /auth/forgot-password` +
  `POST /auth/reset-password`. Token expiry + single-use; avoid account
  enumeration (uniform responses). Remove the boot-refusal at `config.py:120`;
  `shield_auth_require_email_verify` now gates login enforcement.
- Web: net-new `verify-email`, `forgot-password`, `reset-password` pages.
- DECISIONS: **D-028** (email verification + reset).
- e2e via the MailHog API (fetch the message, extract the token, complete the
  flow).
- Depends: sequence AFTER T4 (both edit `routes/auth.py` — avoid churn).

### T6 — OpenAI reasoning-model param fix

- The live OpenAI adapter sends the legacy `max_tokens`
  (`app/ai/llm.py:184`, constant `:150`); newer OpenAI reasoning models reject
  it in favor of `max_completion_tokens`. Send the correct key per model (detect
  by model id, or send `max_completion_tokens` for the `responses`/reasoning
  families). Update the unit assertion at
  `tests/unit/test_llm_providers.py:164`.
- Low risk; unit-only (no live key needed — httpx is monkeypatched).

### T7 — Live-AI parity sweep across all five purposes (opt-in)

- With a key, run each purpose once live and confirm redaction + `llm_calls` +
  response parse: `csf_score` (`routes/csf.py:1330`), `zt_score`
  (`routes/zt.py:406`), `mitre_map` (`routes/attack.py:517`), `risk_synthesize`
  (`routes/risk.py:192`), `tech_debt_extract` (`routes/tech_debt.py:150`, the
  artifact-based one). Fix any real-response parse issues per adapter.
- Extend the T1 opt-in harness to cover all five (skipped without a key).
- Document per-purpose results in SMOKE_TEST.
- Depends: T0, T1, T6.

### T8 — Demo data realism + reset script

- Make the Atlas tenant a coherent end-to-end story: all four services carried
  to completion + a synthesized risk register + released deliverables that
  actually download (needs T2). Replace obviously-placeholder seed content with
  a believable narrative.
- Add `scripts/demo-reset.ps1` (+ a bash sibling): `docker compose down -v` →
  `up -d --build` → wait `/ready` (now full-matrix, T3) → seed → print URLs +
  creds. Document in ONBOARDING/README.
- Verify: after reset, the demo journey renders on `/home` + `/documents` with
  real, downloadable reports; `/ready` all-green.
- Depends: T2 (downloads), ideally T3 (ready gate).

### T9 — Hosted-demo compose (NO cloud/terraform)

- Add a `docker-compose.demo.yml` override (or a documented profile) that runs
  web as a production build (not `next dev`), pins live-safe env placeholders
  (fixture by default; live only when a key is supplied), and gives a
  one-command bring-up for a shared demo host. Cloud provisioning
  (terraform/account/region/DR) stays OUT of scope — gated on Dave.
- Verify: the demo compose builds and serves web + api against the real
  services locally.

### T10 — Security + audit pass

- `pnpm audit` (root) + `npm audit` (e2e/) + `pip-audit` + `bandit` + gitleaks;
  confirm NO key or secret was committed anywhere this sprint (the live tasks
  use the gitignored `.env` only). Review the net-new auth surfaces (MFA enroll/
  verify, email verify, password reset) for OWASP: rate-limiting, token expiry +
  single-use, no account enumeration, no secret in logs/`llm_calls`. Fix or
  document.

### T11 — Wrap-up

- SMOKE_TEST.md: check §14 (via T1's opt-in spec + documented run) and add
  sections for MFA, email verification/reset, the full-matrix health endpoint,
  and the live-purpose sweep — each box checked ONLY where a green committed
  spec proves it (opt-in live specs annotated as CI-skipped-without-key).
- CHANGELOG `[3.3.0]` per-task entries with commits.
- DECISIONS: verify D-026/D-027/D-028 landed; append any others.
- Full exit gate set: full e2e, `pytest -m unit`, web `tsc`, web vitest,
  prettier 3.9.5, in-container ruff/black.
- CONTEXT.md overwritten with the end-of-sprint snapshot (Sprint-5 format).

## Definition of done

- A dev with an Anthropic key can set live mode and every one of the five AI
  purposes egresses a real, redacted call recorded in `llm_calls`; a misconfigured
  live deploy fails LOUDLY at boot, not on first request.
- Seeded deliverables download (200, correct filename) from a clean seed.
- Real TOTP MFA and real email verification + password reset work end to end
  (MailHog in dev); the D-020 boot-refusals are gone and the flags now gate
  enforcement.
- `/ready` reports the full dependency matrix; an operator page shows it green.
- A one-command demo reset produces a coherent, downloadable Atlas story.
- Migrations 0030/0031 additive + SQLite-safe (C0); every commit conventional
  and task-scoped; no secret committed; CONTEXT.md snapshot written.

## Explicitly out of scope (Sprint 7+ / needs-Dave)

- **Cloud/terraform/deploy/DR** — `infra/terraform` stays a stub; gated on
  Dave's cloud/account/region decisions. T9 delivers only a local hosted-demo
  compose, not cloud provisioning.
- **Keycloak SSO cutover** — the Credentials→OIDC swap seam exists
  (`web/src/lib/auth/options.ts:6`) but stays dormant; T4/T5 harden the custom
  JWT flow, not a Keycloak migration.
- **`azure_openai` / `bedrock` / `local` LLM adapters** — stay loud
  not-implemented until a deployment needs one.
- **FedRAMP POA&M artifact export** — Sprint 5's POA&M is the working fields;
  the FedRAMP template stays future scope.
